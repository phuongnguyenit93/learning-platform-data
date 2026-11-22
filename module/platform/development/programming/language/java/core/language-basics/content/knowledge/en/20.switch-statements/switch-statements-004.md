# `break` to Terminate a Switch Statement — Java 17+

## 1. What Does `break` Do in a `switch`?

In a **switch statement** using the traditional `case ...:` syntax, the `break;` statement **immediately terminates the innermost enclosing switch**. Execution continues at the statement **after** the switch, not after the next `case` label.

~~~java
int choice = 2;
switch (choice) {
    case 1:
        System.out.println("One");
        break;
    case 2:
        System.out.println("Two");
        break;
    default:
        System.out.println("Other");
}
System.out.println("After switch");
~~~

**Exact expected stdout:**

~~~text
Two
After switch
~~~

Without `break;` after `case 2`, execution can **fall into the `default` branch**, even though `choice` does not match `default`. This is *fall-through*, a common source of bugs in colon-style switches.

After this lesson, you should be able to distinguish `break` from `return` and `continue`, know which switch `break` exits when nested, when `break` can be omitted, and how to use `case ... ->` in Java 17 to avoid fall-through.

## 2. Execution Flow of Colon-Style Switch

~~~mermaid
flowchart TD
    A["Evaluate selector"] --> B{"Case label matches?"}
    B -- "Yes" --> C["Start executing from matching case"]
    B -- "No" --> D{"Has default?"}
    D -- "No" --> H["After switch"]
    D -- "Yes" --> E["Start executing from default"]
    C --> F{"Hit break exiting switch?"}
    E --> F
    F -- "Yes" --> H
    F -- "No" --> G["Continue statements and possibly fall through"]
    G --> F
~~~

Key steps:

1. The selector is evaluated.
2. Java identifies the matching `case` label, or `default` if no `case` matches.
3. With the `case:` form, execution starts at the selected label and **proceeds sequentially through statements**, without stopping automatically at the end of that label's group.
4. Encountering an unlabeled `break;` exits the **innermost enclosing switch or loop**.
5. If execution reaches the end of the switch without encountering `break`, control also exits the switch normally.

`break` **is not syntactically required in every `case`**. It matters when you need to prevent continuing into subsequent labels.

## 3. Example Without `break`

~~~java
switch (2) {
    case 2: System.out.println("Two");
    case 3: System.out.println("Three"); break;
    default: System.out.println("Other");
}
~~~

The output is `Two` followed by `Three`: after selecting case 2, Java executes through until `break` without re-checking the case 3 label. The focus here is exit placement; the colon-style lesson describes all fall-through paths in detail.

## 4. Placing `break` in the Right Position

If you only want to handle one code, place `break` after that code's statements:

~~~java
switch (code) {
    case 1:
        handleOne();
        break;
    case 2:
        handleTwo();
        break;
    default:
        handleOther();
}
~~~

In the snippet above, `handleOne`, `handleTwo`, and `handleOther` are domain methods you define yourself; this excerpt illustrates **`break` placement**, not a standalone program.

You can write a block to keep local variables scoped:

~~~java
switch (code) {
    case 1: {
        String message = "one";
        System.out.println(message);
        break;
    }
    case 2: {
        String message = "two";
        System.out.println(message);
        break;
    }
    default:
        System.out.println("other");
}
~~~

Braces `{ ... }` **do not make `break` exit only the brace block**: `break;` still terminates the enclosing switch.

**Note:** if a `case` already ends with `return` or `throw`, do not place another `break` afterward — that `break` line can become an *unreachable statement* and cause a compile error.

## 5. Stopping After a Shared Body of Multiple Labels

~~~java
switch (day) {
    case 6:
    case 7:
        System.out.println("Weekend");
        break;
    default:
        System.out.println("Weekday");
}
~~~

Two consecutive labels intentionally share one statement body; `break` sits **after the shared body**. If one branch performs its own action and then falls through into another branch, verify that it is intentional and document it clearly.

## 6. Does `default` Need `break`?

If `default` is the last label and the switch ends immediately after its body, `break` is unnecessary. When `default` sits between `case:` labels, omitting `break` still causes fall-through. Decide based on the **execution path**, not the label name. The `case/default` labels lesson includes examples comparing placement.

## 7. `break` vs. `return` and `continue`

| Statement | Primary effect | After execution |
|---|---|---|
| `break;` | Exits the innermost switch or loop | Continues after the exited construct |
| `return;` / `return value;` | Exits the **entire method** | Does not run statements after the switch in the same method |
| `continue;` | Skips the remainder of the **iteration**, valid only inside a loop | Advances to the loop's update/condition step |
| `throw ...;` | Throws an exception | Transfers control via the exception mechanism |

Example where `break` terminates only the switch:

~~~java
static void printChoice(int choice) {
    switch (choice) {
        case 1:
            System.out.println("one");
            break;
        default:
            System.out.println("other");
    }
    System.out.println("method continues");
}
~~~

Example where `return` terminates the method:

~~~java
static String label(int choice) {
    switch (choice) {
        case 1:
            return "ONE";
        default:
            return "OTHER";
    }
}
~~~

**Do not mechanically replace `break` with `return`**: if the method still has processing after the switch, `return` will skip that processing.

`continue;` **cannot replace `break;` in a standalone switch**; it requires an enclosing loop. When a switch is inside a loop, `continue;` applies to that loop.

## 8. Switch Inside a Loop: `break` Does Not Exit the Loop

~~~java
for (int i = 0; i < 3; i++) {
    switch (i) {
        case 1:
            System.out.println("case one");
            break; // Exits switch, NOT for.
        default:
            System.out.println("other " + i);
    }
    System.out.println("after switch " + i);
}
~~~

**Exact expected stdout:**

~~~text
other 0
after switch 0
case one
after switch 1
other 2
after switch 2
~~~

When `i == 1`, `break;` terminates the switch, after which `System.out.println("after switch " + i)` still executes and the `for` loop continues.

If you need to exit the loop itself, place a `break` condition **outside the switch**, or use a **labeled break** intentionally:

~~~java
outer:
for (int i = 0; i < 5; i++) {
    switch (i) {
        case 2:
            break outer; // Exits the outer labeled loop completely.
        default:
            System.out.println(i);
    }
}
~~~

**Exact expected stdout:**

~~~text
0
1
~~~

Use labels when you genuinely need to exit an outer construct; do not overuse them as a substitute for clear loop design.

## 9. Nested Switches: `break` Exits the Innermost Switch

~~~java
int outer = 1;
int inner = 7;

switch (outer) {
    case 1:
        switch (inner) {
            case 7:
                System.out.println("inner seven");
                break; // Only exits switch(inner).
            default:
                System.out.println("inner other");
        }
        System.out.println("after inner");
        break; // Exits switch(outer).
    default:
        System.out.println("outer other");
}
~~~

**Exact expected stdout:**

~~~text
inner seven
after inner
~~~

If you omit the `break` of the outer switch, execution can continue falling through into later labels of the outer switch. **Each switch has its own control flow**.

## 10. Comparison with Arrow Branches

In a Java 17 switch statement, `case 1 -> action();` does not need `break` to prevent fall-through. If a branch needs multiple statements, use a `{ ... }` block. When refactoring old `case:` switches, remove `break` only when intentionally converting the syntax to arrow rules.

## 11. `break` vs. `yield`

`break;` exits a switch statement or an appropriate loop without producing a value. A switch **expression** with a block `case 2 -> { ... }` needs `yield value;` on normal completion paths. Do not replace `yield` with `break` or `break value`. Conditional paths, results, and exceptions are covered in the `yield` lesson.

## 12. Complete Java 17 Example, Runnable via CLI

Create a file named **`SwitchBreakDemo.java`**:

~~~java
public final class SwitchBreakDemo {
    private SwitchBreakDemo() {}

    static String classify(int code) {
        String result;
        switch (code) {
            case 1:
                result = "ONE";
                break;
            case 2:
            case 3:
                result = "TWO_OR_THREE";
                break;
            default:
                result = "OTHER";
        }
        return result;
    }

    static void fallThrough(int code) {
        switch (code) {
            case 1:
                System.out.println("fall:one");
                // Fall through intentionally.
            case 2:
                System.out.println("fall:two");
                break;
            default:
                System.out.println("fall:other");
        }
        System.out.println("fall:after-switch");
    }

    static void arrow(int code) {
        switch (code) {
            case 1 -> System.out.println("arrow:one");
            case 2, 3 -> System.out.println("arrow:two-or-three");
            default -> System.out.println("arrow:other");
        }
    }

    static String withReturn(int code) {
        switch (code) {
            case 0:
                return "ZERO";
            default:
                return "NONZERO";
        }
    }

    static String nested(int outer, int inner) {
        String result;
        switch (outer) {
            case 1:
                result = "outer-one";
                switch (inner) {
                    case 7:
                        result = "inner-seven";
                        break; // Only exits the inner switch.
                    default:
                        result = "inner-other";
                }
                result += "-after-inner";
                break; // Exits the outer switch.
            case 2:
                result = "outer-two";
                break;
            default:
                result = "outer-other";
        }
        return result;
    }

    static void loopWithSwitch() {
        for (int i = 0; i < 3; i++) {
            switch (i) {
                case 1:
                    System.out.println("loop:case-one");
                    break;
                default:
                    System.out.println("loop:other-" + i);
            }
            System.out.println("loop:after-switch-" + i);
        }
    }

    static void labeledBreak() {
        outer:
        for (int i = 0; i < 5; i++) {
            switch (i) {
                case 2:
                    break outer;
                default:
                    System.out.println("labeled:" + i);
            }
        }
        System.out.println("labeled:after-loop");
    }

    static void blockBreak(int code) {
        switch (code) {
            case 1: {
                String message = "block:one";
                System.out.println(message);
                break;
            }
            default:
                System.out.println("block:other");
        }
        System.out.println("block:after-switch");
    }

    public static void main(String[] args) {
        System.out.println("classify 1=" + classify(1));
        System.out.println("classify 2=" + classify(2));
        System.out.println("classify 3=" + classify(3));
        System.out.println("classify 9=" + classify(9));

        fallThrough(1);
        fallThrough(2);
        arrow(1);
        arrow(3);
        arrow(9);

        System.out.println("return 0=" + withReturn(0));
        System.out.println("return 8=" + withReturn(8));

        System.out.println("nested 1/7=" + nested(1, 7));
        System.out.println("nested 1/8=" + nested(1, 8));
        System.out.println("nested 2/7=" + nested(2, 7));

        loopWithSwitch();
        labeledBreak();
        blockBreak(1);

        int code = 2;
        String expression = switch (code) {
            case 1 -> "ONE";
            case 2 -> {
                String value = "TWO";
                yield value;
            }
            default -> "OTHER";
        };
        System.out.println("expression=" + expression);
    }
}
~~~

**Requirements:** JDK 17 or higher, terminal in the directory containing `SwitchBreakDemo.java`; no Maven/Gradle needed, no preview features or external libraries beyond the JDK used.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 SwitchBreakDemo.java
java -cp . SwitchBreakDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\SwitchBreakDemo.java
java -cp . SwitchBreakDemo
~~~

**Exact expected stdout:**

~~~text
classify 1=ONE
classify 2=TWO_OR_THREE
classify 3=TWO_OR_THREE
classify 9=OTHER
fall:one
fall:two
fall:after-switch
fall:two
fall:after-switch
arrow:one
arrow:two-or-three
arrow:other
return 0=ZERO
return 8=NONZERO
nested 1/7=inner-seven-after-inner
nested 1/8=inner-other-after-inner
nested 2/7=outer-two
loop:other-0
loop:after-switch-0
loop:case-one
loop:after-switch-1
loop:other-2
loop:after-switch-2
labeled:0
labeled:1
labeled:after-loop
block:one
block:after-switch
expression=TWO
~~~

### Reading the Output

- `classify` uses `break` to ensure each code is assigned only one result.
- `fallThrough(1)` prints both `fall:one` and `fall:two` by **intentionally** omitting `break`; `fallThrough(2)` prints only `fall:two`.
- `arrow` does not fall through, even without `break;`.
- `withReturn` returns directly from the method, running no further statements in the method.
- `nested` shows that an inner switch's `break` does not automatically exit the outer switch.
- `loopWithSwitch` continues running `for` after the switch executes `break;`.
- `labeledBreak` exits the `for` loop labeled `outer`.
- `blockBreak` confirms `break` exits the switch even when inside a `case` with `{ ... }`.
- `yield` supplies `"TWO"` for the switch expression.

## 13. Common Mistakes Table

| Mistake | Consequence | How to fix |
|---|---|---|
| Forgetting `break` after `case:` | Executes into the next case's statements | Add `break;` or use `->` |
| Thinking Java re-checks the next case after fall-through | Misinterpreting the output | Understand that execution simply proceeds sequentially |
| Thinking `default` always ends a switch automatically | A `default` in the middle still falls through | Add `break` if needed |
| Putting `break` right after `return` | Unreachable code, possible compile error | Choose one exit mechanism appropriate to the intent |
| Using `break` expecting to exit the entire method | The method continues after the switch | Use `return` if you want to exit the method |
| Using `break` in a switch inside `for` to end `for` | Only exits the switch | Place break outside the switch or use a label |
| Thinking `break` in an inner switch exits the outer switch | Only exits the innermost construct | Manage each level separately or use return when appropriate |
| Using `continue` in a switch without a loop | Invalid | Use `break` to exit the switch |
| Putting `break;` to return a value from a switch expression | Does not supply a result | Use `yield` for branches with blocks |
| Mixing `case:` and `case ->` syntax in the same switch | Compile error | Pick one consistent label style |
| Using fall-through across similar branches without comments | Readers think `break` was forgotten | Use consecutive empty labels or `case 1, 2 ->` |

## 14. Exercises with Solutions

### Exercise A — Predicting fall-through

~~~java
int x = 1;
switch (x) {
    case 1:
        System.out.println("A");
    case 2:
        System.out.println("B");
        break;
    default:
        System.out.println("C");
}
~~~

**Solution:**

~~~text
A
B
~~~

`case 1` matches but lacks `break`, so execution continues into `case 2`'s statement.

### Exercise B — Running only the selected case

Rewrite the example above so that `x == 1` prints only A.

**One solution:**

~~~java
switch (x) {
    case 1:
        System.out.println("A");
        break;
    case 2:
        System.out.println("B");
        break;
    default:
        System.out.println("C");
}
~~~

You can also use `case 1 -> System.out.println("A");` branches in Java 17.

### Exercise C — `break` inside a loop

~~~java
for (int i = 0; i < 2; i++) {
    switch (i) {
        case 0:
            break;
        default:
            System.out.println("default");
    }
    System.out.println("after " + i);
}
~~~

**Solution:**

~~~text
after 0
default
after 1
~~~

The `break;` statement terminates only the switch on the first iteration, not the `for` loop.

### Exercise D — Nested switches

~~~java
switch (1) {
    case 1:
        switch (7) {
            case 7:
                System.out.println("inner");
                break;
        }
        System.out.println("outer continues");
        break;
}
~~~

**Solution:**

~~~text
inner
outer continues
~~~

The inner break exits only the inner switch; the outer case's statements still execute.

### Exercise E — Switch expression

You need to produce a `String` from a switch whose branch executes multiple statements. Should you use `break` or `yield`?

**Solution:** In a switch **expression**, use `yield value;` to return a value from a block:

~~~java
String label = switch (code) {
    case 1 -> {
        String value = "ONE";
        yield value;
    }
    default -> "OTHER";
};
~~~

## 15. Checklist and Conclusion

- [ ] Understand that `break;` terminates the innermost switch and execution continues **after the switch**.
- [ ] Know that `case:` does not stop automatically; omitting `break` can fall through.
- [ ] Know when fall-through is intentional (grouping cases or deliberately designed flow).
- [ ] Do not treat `default` as an automatic stop if it is not last.
- [ ] Distinguish `break` (exiting a switch) from `return` (exiting a method).
- [ ] Distinguish `break` from loop `continue`.
- [ ] Understand that `break` in a switch nested in `for` does not exit the `for` loop.
- [ ] Understand that `break` in an inner switch does not automatically exit the outer switch.
- [ ] Know that Java 17's `case ->` **does not fall through** and needs no `break` to prevent falling through.
- [ ] Know that switch expressions use `yield` to return a value from a block.
- [ ] Do not place `break` after an unconditional `return`.
- [ ] Run `SwitchBreakDemo.java` with JDK 17+ and verify exact stdout.

**Conclusion:** For `case:`-style switch statements, `break;` is the explicit way to **prevent fall-through** and exit the switch at the desired point. It neither exits the method nor automatically exits an enclosing loop. In Java 17, `case ->` syntax is a good choice when each case should run only one branch without needing `break`.