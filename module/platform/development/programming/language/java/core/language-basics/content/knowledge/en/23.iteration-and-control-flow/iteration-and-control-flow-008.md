# Distinguishing `break`, `continue`, `return`, and `yield` — Java 17+

These four keywords all **alter execution flow**, yet they **differ in where they transfer control**. You cannot substitute them for one another just because all of them can end a block of statements.

| Statement | Primary Effect | Typical Context | Where Does the Program Go Afterward? |
| --- | --- | --- | --- |
| `break;` | Exits the **nearest loop or `switch`** | `for`, `while`, `do-while`, switch statement | Statement following the exited construct |
| `continue;` | Skips the rest of the **current loop iteration** | Inside a loop | Preparation step for the next iteration of the nearest loop |
| `return value;` / `return;` | Terminates the **current method** | Inside a method, when the `return` form matches the return type | Back to the call site, without executing the rest of the method |
| `yield value;` | Produces a value and ends the enclosing **switch expression** | Branch or block inside a switch expression | Continues in the expression/statement consuming the `switch` result |

**Quick rule of thumb:** `break` exits a construct, `continue` goes to the next loop iteration, `return` exits a method, and `yield` returns a value **for a `switch` expression**, without exiting the method on its own.

## 1. `break`: Stops the Nearest Loop or `switch`

~~~java
for (int i = 0; i < 5; i++) {
    if (i == 3) {
        break;
    }
    System.out.println(i);
}
System.out.println("after-loop");
~~~

Prints `0`, `1`, `2`, and then `after-loop`. When `i == 3`, `break` skips the remainder of the body, does **not** run the `i++` update one more time, and completely exits the loop.

In a `switch` inside a loop, `break;` exits **`switch`**, not the outer loop by default:

~~~java
for (int i = 0; i < 2; i++) {
    switch (i) {
        case 0:
            System.out.println("zero");
            break; // Only exits switch.
        default:
            System.out.println("other");
    }
    System.out.println("after-switch=" + i);
}
~~~

Even with `break` in `case 0`, the line `after-switch=0` is still printed and the `for` loop continues. With nested loops, unlabeled `break;` only exits the **nearest loop**. Exiting multiple levels via labels or method extraction is a separate topic, not the default behavior.

## 2. `continue`: Skips the Remainder of the Current Iteration

~~~java
for (int i = 0; i < 4; i++) {
    if (i % 2 == 0) {
        continue;
    }
    System.out.println(i);
}
// Prints 1 then 3.
~~~

`continue` does not end the entire loop. In a basic `for`, it transfers to the **update clause** before checking the condition:

~~~java
for (int i = 0; i < 3; i++) {
    if (i == 1) {
        continue; // Still runs i++ before the next iteration.
    }
    System.out.println("i=" + i);
}
~~~

With `while`, `continue` transfers to the **condition check**; with `do-while`, it transfers to **the check at the end of the body**. If updating the counter variable is placed after `continue` inside `while`, the loop can **fail to make progress** and loop infinitely.

`continue;` does not jump to the next `case` label of a `switch`. If a `switch` is inside a loop, `continue;` inside the `switch` continues the **enclosing loop**. If the `switch` is not inside a loop, `continue;` is invalid.

## 3. `return`: Exits the Entire Method

~~~java
static String find(int wanted) {
    for (int i = 0; i < 3; i++) {
        if (i == wanted) {
            return "found:" + i;
        }
    }
    return "missing";
}
~~~

`return` terminates **the entire method invocation**, even when executed inside a `for` loop or `switch`. If the element is found, Java does not run further loop iterations or normal statements following `return`.

- Value-returning methods, such as `String find(...)`, use `return expression;` with a compatible type.
- `void` methods can use `return;` to leave the method early.
- `return;` cannot be used to return from a method requiring a value; conversely, `return 5;` is invalid in a `void` method.
- A method's `return` does not terminate the whole program: the **caller** receives the result and continues executing.

## 4. `yield`: Produces a Value Out of a `switch expression`

Since Java 14, `switch` can be an **expression returning a value**. When a block-bodied branch needs to run multiple statements, use `yield`:

~~~java
static String classify(int n) {
    String label = switch (n) {
        case 0 -> "zero";
        case 1 -> {
            System.out.println("preparing");
            yield "one";
        }
        default -> "other";
    };
    System.out.println("after-expression");
    return label;
}
~~~

With `n == 1`, Java prints `preparing` then **`after-expression`**, and the method only finishes at `return label`. Thus `yield "one";` ends the switch expression branch, **not** `classify`.

### Colon syntax can also use `yield`

~~~java
int score = switch (level) {
    case 1:
        yield 10;
    case 2:
        yield 20;
    default:
        yield -1;
};
~~~

This is a **switch expression** with `case:` labels, not a traditional switch statement. `yield` supplies the result for the entire expression. Do not write `break 20;` to produce a result: Java 17 uses `yield 20;`.

### `switch statement` vs. `switch expression`

~~~java
// SWITCH STATEMENT: performs an action, does not produce a value.
switch (status) {
    case "ON":
        System.out.println("enabled");
        break;
    default:
        System.out.println("unknown");
}

// SWITCH EXPRESSION: produces a value.
String result = switch (status) {
    case "ON" -> "enabled";
    default -> "unknown";
};
~~~

- `yield` belongs to **switch expressions**, and is not used as a replacement for `break` in a switch statement.
- `return` is not allowed **inside a switch expression** as a substitute for yielding a branch's value; use an expression after `->` or `yield`.
- `case ->` does not automatically mean a switch expression: Java 17 also allows **switch statements** with arrow labels.
- Not every branch needs `yield`: a `case X -> expression` branch supplies its result directly.
- A switch expression must be **exhaustive** over the selector values according to Java's rules; `default` is often used when needed.

## 5. Complete Java 17+ Program

Create a UTF-8 file **`FlowTransferDemo.java`**:

~~~java
public class FlowTransferDemo {
    static void breakLoop() {
        for (int i = 0; i < 5; i++) {
            if (i == 3) {
                System.out.println("break=" + i);
                break;
            }
            System.out.println("seen=" + i);
        }
        System.out.println("afterBreak");
    }

    static void continueLoop() {
        for (int i = 0; i < 4; i++) {
            if (i % 2 == 0) {
                System.out.println("skip=" + i);
                continue;
            }
            System.out.println("keep=" + i);
        }
        System.out.println("afterContinue");
    }

    static String find(int target) {
        for (int i = 0; i < 4; i++) {
            if (i == target) {
                return "found:" + i;
            }
        }
        return "missing";
    }

    static String expression(int n) {
        String result = switch (n) {
            case 0 -> "zero";
            case 1 -> {
                System.out.println("insideYield=" + n);
                yield "one";
            }
            default -> "other";
        };
        System.out.println("afterExpr=" + result);
        return "value:" + result;
    }

    static int colonExpression(int n) {
        int result = switch (n) {
            case 1:
                yield 10;
            case 2:
                yield 20;
            default:
                yield -1;
        };
        System.out.println("afterColon=" + result);
        return result;
    }

    static void switchInsideLoop() {
        for (int n = 0; n < 3; n++) {
            switch (n) {
                case 0:
                    System.out.println("caseZero");
                    break;
                case 1:
                    System.out.println("caseOne");
                    continue;
                default:
                    System.out.println("caseOther");
            }
            System.out.println("afterSwitch=" + n);
        }
    }

    static String returnFromSwitch(String code) {
        if (code == null) {
            return "missing";
        }
        switch (code) {
            case "GO":
                return "run";
            default:
                return "unknown";
        }
    }

    public static void main(String[] args) {
        System.out.println("== break ==");
        breakLoop();

        System.out.println("== continue ==");
        continueLoop();

        System.out.println("== return ==");
        System.out.println("return1=" + find(2));
        System.out.println("return2=" + find(9));

        System.out.println("== yield ==");
        System.out.println("expression1=" + expression(1));
        System.out.println("expression9=" + expression(9));

        System.out.println("== colon-style expression ==");
        System.out.println("colon2=" + colonExpression(2));

        System.out.println("== switch in loop ==");
        switchInsideLoop();

        System.out.println("== return in switch statement ==");
        System.out.println("codeGo=" + returnFromSwitch("GO"));
        System.out.println("codeNull=" + returnFromSwitch(null));
        System.out.println("done");
    }
}
~~~

Using **JDK 17 or higher**, open PowerShell or Bash in the directory containing the file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 FlowTransferDemo.java
java FlowTransferDemo
~~~

**Exact expected stdout** of the `java FlowTransferDemo` command alone:

~~~text
== break ==
seen=0
seen=1
seen=2
break=3
afterBreak
== continue ==
skip=0
keep=1
skip=2
keep=3
afterContinue
== return ==
return1=found:2
return2=missing
== yield ==
insideYield=1
afterExpr=one
expression1=value:one
afterExpr=other
expression9=value:other
== colon-style expression ==
afterColon=20
colon2=20
== switch in loop ==
caseZero
afterSwitch=0
caseOne
caseOther
afterSwitch=2
== return in switch statement ==
codeGo=run
codeNull=missing
done
~~~

`java -version` and `javac -version` output information depending on the installed JDK version and are not part of the fixed stdout block. The example uses only standard Java APIs.

## 6. Easy-to-Confuse Cases

| Misconception | Correct Behavior |
| --- | --- |
| "`break` exits the method." | It only exits the nearest loop or switch |
| "`continue` exits the whole loop." | It skips the rest of the **current iteration** |
| "`continue` in basic `for` skips the update part." | It still runs the update part when continuing that loop |
| "`break` in a switch inside a loop exits the outer loop." | It exits the nearest switch |
| "`continue` in a switch goes to the next case." | It targets the nearest loop, or is forbidden if there is no loop |
| "`return` and `yield` both exit the method." | Only `return` exits the method; `yield` produces a switch expression's result |
| "Switch expressions use `break value;`." | Use `yield value;` or `case -> expression` |
| "Use `return value;` instead of `yield value;` in a switch expression." | Invalid inside a switch expression |
| "Every `switch case ->` returns a value." | Switch statements can also use arrow syntax |

### Abrupt Exit and `finally`

Control-transfer statements still obey Java's `finally` mechanism. If execution exits a `try` block via `break`, `continue`, or `return`, the corresponding `finally` block still executes. Do not use these statements assuming resource cleanup can be skipped; for closeable resources, prefer `try-with-resources`. This does not change the **semantic targets** of the four keywords.

## 7. Self-Check Exercises

1. Does `break;` in `for` let `i++` of that iteration run afterward?  
   *Answer:* No.
2. With `continue;` in basic `for`, does `i++` run?  
   *Answer:* Yes, if `continue` targets that `for` loop.
3. Does `return "ok";` inside a loop run normal statements after the loop in the same method?  
   *Answer:* No; the method has terminated.
4. Does `yield "ok";` inside a switch expression also terminate the enclosing method?  
   *Answer:* No; it provides the switch expression's result.
5. When a `switch` is inside a `while`, which construct does `break;` from a `case:` branch exit?  
   *Answer:* Exits the switch; the while loop can still continue.
6. Does `continue;` inside a `switch` with no enclosing loop compile?  
   *Answer:* No.
7. Can `yield` be written inside an ordinary switch statement to return a value from the statement?  
   *Answer:* No; use a switch expression if a value is needed.

## Checklist

- [ ] Identify the exact **control target**: nearest loop/switch, next iteration, method, or switch expression.
- [ ] Use `break` to **stop** a loop/switch, and `continue` to **skip one iteration**.
- [ ] Use `return` to **terminate a method** matching its return type.
- [ ] Use `yield` when needing to **supply a value** from a block or colon branch of a switch expression.
- [ ] Do not confuse a switch statement with a switch expression.
- [ ] Verify loop updates and resource handling when changing control flow.

**Conclusion:** `break` stops the nearest enclosing construct; `continue` moves to the next loop iteration; `return` exits the method; `yield` exits a **switch expression** branch with a value. Knowing each statement's exact destination prevents exiting the wrong scope and leads to clear Java 17 code.
