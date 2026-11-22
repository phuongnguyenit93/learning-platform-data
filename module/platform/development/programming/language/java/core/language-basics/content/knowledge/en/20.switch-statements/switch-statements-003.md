# Colon-Style `switch` and Fall-Through Behavior — Java 17+

In Java, a **colon-style `switch` statement** (*colon-style switch statement*) places `case ...:` and `default:` labels before the statements to execute. The key point to remember is that **a `case` label does not automatically end a branch**: once execution starts from a matching label, Java continues running the statements below it, even across other `case` labels, until it encounters `break`, `return`, `throw`, or the end of the `switch` block.

This behavior is called **fall-through** (*falling through to the next branch*).

~~~java
int code = 1;
switch (code) {
    case 1:
        System.out.println("one");
    case 2:
        System.out.println("two");
        break;
    default:
        System.out.println("other");
}
~~~

With `code = 1`, the program prints **both `one` and `two`**. The reason: there is no `break` after `case 1:`, so after printing `one`, control continues to the statement under `case 2:` without **re-checking the case 2 condition**.

## 1. Colon-Style `switch` Syntax

~~~java
switch (expression) {
    case CONSTANT_1:
        // Statements for the first label
        break;
    case CONSTANT_2:
        // Statements for the second label
        break;
    default:
        // When no case label matches
}
~~~

Execution rules:

1. Java evaluates the **selector expression** `expression` exactly once for that `switch` execution.
2. Finds the **matching `case` label** for the value, or jumps to `default` if no label matches.
3. Starts executing **from the selected label's position**.
4. Continues sequentially through the statements below; subsequent labels **are not automatic barriers**.
5. A standard `break;` exits the innermost enclosing `switch`; execution continues with the statement after the `switch` block.

**`default` is optional.** If no `case` matches and there is no `default`, Java skips the entire `switch` body.

### Typical Behavior Table

~~~java
switch (n) {
    case 1:
        System.out.println("A");
    case 2:
        System.out.println("B");
    case 3:
        System.out.println("C");
        break;
    default:
        System.out.println("D");
}
~~~

| Value of `n` | Lines printed from `switch` | Explanation |
| --- | --- | --- |
| 1 | A, B, C | Falls through case 2 and case 3 before hitting `break` |
| 2 | B, C | Falls through case 3 |
| 3 | C | Stops at `break` |
| 9 | D | No case matches; runs `default` |

Do not assume that just because the selector expression equals 1, "only the statements of case 1 will run." In colon style, **`break` is what creates the execution boundary**.

## 2. Complete Java 17+ Program

Create a UTF-8 file named **`SwitchColonDemo.java`**:

~~~java
public class SwitchColonDemo {
    static void fallThrough(int value) {
        System.out.println("input=" + value);
        switch (value) {
            case 1:
                System.out.println("one");
            case 2:
                System.out.println("two");
            case 3:
                System.out.println("three");
                break;
            default:
                System.out.println("other");
        }
        System.out.println("after");
    }

    static void withBreak(int value) {
        System.out.println("break-input=" + value);
        switch (value) {
            case 1:
                System.out.println("break=one");
                break;
            case 2:
                System.out.println("break=two");
                break;
            default:
                System.out.println("break=other");
        }
        System.out.println("break-after");
    }

    static String season(int month) {
        switch (month) {
            case 12:
            case 1:
            case 2:
                return "winter";
            case 3:
            case 4:
            case 5:
                return "spring";
            case 6:
            case 7:
            case 8:
                return "summer";
            case 9:
            case 10:
            case 11:
                return "autumn";
            default:
                return "invalid";
        }
    }

    static void defaultInMiddle(int value) {
        System.out.println("middle-input=" + value);
        switch (value) {
            case 1:
                System.out.println("case-one");
                break;
            default:
                System.out.println("default");
            case 2:
                System.out.println("case-two");
                break;
            case 3:
                System.out.println("case-three");
                break;
        }
    }

    static void continueInLoop() {
        for (int i = 0; i < 3; i++) {
            switch (i) {
                case 0:
                    System.out.println("loop-zero");
                    continue;
                case 1:
                    System.out.println("loop-one");
                    break;
                default:
                    System.out.println("loop-two");
            }
            System.out.println("loop-after=" + i);
        }
    }

    static void localScopes(int option) {
        switch (option) {
            case 1: {
                int local = 10;
                System.out.println("scope=" + local);
                break;
            }
            case 2: {
                int local = 20;
                System.out.println("scope=" + local);
                break;
            }
            default:
                System.out.println("scope=other");
        }
    }

    static String state(String code) {
        if (code == null) {
            return "null";
        }
        switch (code) {
            case "ON":
                return "enabled";
            case "OFF":
                return "disabled";
            default:
                return "unknown";
        }
    }

    public static void main(String[] args) {
        System.out.println("== fall-through ==");
        fallThrough(1);
        fallThrough(2);
        fallThrough(3);
        fallThrough(9);

        System.out.println("== break ==");
        withBreak(1);
        withBreak(2);
        withBreak(9);

        System.out.println("== grouped labels ==");
        System.out.println("season1=" + season(1));
        System.out.println("season4=" + season(4));
        System.out.println("season8=" + season(8));
        System.out.println("season10=" + season(10));
        System.out.println("season13=" + season(13));

        System.out.println("== default in middle ==");
        defaultInMiddle(9);
        defaultInMiddle(2);
        defaultInMiddle(1);
        defaultInMiddle(3);

        System.out.println("== switch inside loop ==");
        continueInLoop();

        System.out.println("== scoped cases ==");
        localScopes(1);
        localScopes(2);
        localScopes(7);

        System.out.println("== String selectors ==");
        System.out.println("stateON=" + state("ON"));
        System.out.println("stateNull=" + state(null));
        System.out.println("stateOther=" + state("UNKNOWN"));

        System.out.println("== switch expression with colon ==");
        String result = switch (2) {
            case 1:
                yield "one";
            case 2:
                yield "two";
            default:
                yield "other";
        };
        System.out.println("yieldResult=" + result);
    }
}
~~~

Use **JDK 17 or higher**. Open PowerShell (Windows) or Bash (Linux/macOS) in the directory containing the file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 SwitchColonDemo.java
java SwitchColonDemo
~~~

**Exact expected stdout** of `java SwitchColonDemo` alone:

~~~text
== fall-through ==
input=1
one
two
three
after
input=2
two
three
after
input=3
three
after
input=9
other
after
== break ==
break-input=1
break=one
break-after
break-input=2
break=two
break-after
break-input=9
break=other
break-after
== grouped labels ==
season1=winter
season4=spring
season8=summer
season10=autumn
season13=invalid
== default in middle ==
middle-input=9
default
case-two
middle-input=2
case-two
middle-input=1
case-one
middle-input=3
case-three
== switch inside loop ==
loop-zero
loop-one
loop-after=1
loop-two
loop-after=2
== scoped cases ==
scope=10
scope=20
scope=other
== String selectors ==
stateON=enabled
stateNull=null
stateOther=unknown
== switch expression with colon ==
yieldResult=two
~~~

The two commands `java -version` and `javac -version` output information depending on the installed JDK version and are not part of the fixed expected stdout.

## 3. Stopping Points of Fall-Through Flow

A `case:` label does not create a stopping boundary; `break;` exits the innermost switch. `return` exits the method, while `throw` transfers control to exception handling. When a switch is inside a loop, `continue` affects the enclosing loop. Differences among exit statements, nested switches, and loops are practiced in detail in the next lesson.

## 4. Intentional Fall-Through: Grouping Multiple `case` Labels

A clear use of fall-through is **multiple labels sharing one statement body**:

~~~java
switch (month) {
    case 12:
    case 1:
    case 2:
        System.out.println("winter");
        break;
    case 3:
    case 4:
    case 5:
        System.out.println("spring");
        break;
    default:
        System.out.println("other");
}
~~~

With `month == 12`, Java enters `case 12:`, passes through `case 1:` and `case 2:` with no statements in between, and prints `winter`. This is **intentional fall-through**, without the risk of running different actions.

In Java 17, labels with the same body can also be written as a comma-separated list:

~~~java
switch (month) {
    case 12, 1, 2:
        System.out.println("winter");
        break;
    default:
        System.out.println("other");
}
~~~

The colon form still needs `break` if you want to stop after the group. When the task is simply selecting one value and fall-through is not needed, `case ... ->` usually expresses intent more clearly.

## 5. `default` Does Not Have to Be Last

`default:` is the entry point when **no `case` label matches**, yet its written position inside the `switch` block does not have to be at the end.

~~~java
switch (value) {
    case 1:
        System.out.println("one");
        break;
    default:
        System.out.println("default");
    case 2:
        System.out.println("two");
        break;
}
~~~

If `value == 9`, Java starts at `default`, prints `default`, and then **falls through** into `case 2:` to print `two` before hitting `break`. If `value == 2`, Java starts **directly at `case 2:`** and prints only `two`.

| `value` | Result |
| --- | --- |
| 1 | `one` |
| 2 | `two` |
| 9 | `default`, then `two` |

**Recommendation:** placing `default` last and ending each branch explicitly helps avoid confusion; placing `default` in the middle is valid, but requires considering fall-through.

## 6. Local Variable Scope Across `case` Labels

A `case` label **does not automatically create a new scope**. Local variable declarations in different cases within the same `switch` block can collide in name, and using one before assignment can cause a **definite assignment** error.

A clean approach is to create a separate block for each case:

~~~java
switch (option) {
    case 1: {
        int result = 10;
        System.out.println(result);
        break;
    }
    case 2: {
        int result = 20; // Redeclaration is valid because it is in a different block.
        System.out.println(result);
        break;
    }
    default: {
        System.out.println("unknown");
    }
}
~~~

Do not confuse `case:` with a `{...}` block: a label is a control-flow entry point, whereas curly braces create an explicit block scope. Writing `{ }` also prevents accidentally reading a variable uninitialized on another path.

## 7. Selector and Label Constraints

In standard Java 17, switch supports `byte`, `short`, `char`, `int` and their corresponding wrappers, `String`, or enum. Constant labels must be compile-time valid, range-compatible, and non-duplicate. A `null` reference selector causes `NullPointerException`, without running `default`. Selector type tables and null policies have dedicated lessons; here we use them as preconditions for the colon mechanism.

## 8. Quick Comparison with `case ... ->`

The `case ...:` form can fall through and usually needs `break` after the body. The `case ... ->` form executes a single rule and does not fall through to the next rule; multiple values can be grouped using `case 1, 2 -> ...`. Do not mix the two forms in one switch. The arrow lesson explains blocks and scopes separately.

## 9. `switch` Inside a Loop

If a switch is inside a `for` loop, omitting `break` still causes fall-through **inside the switch**. In contrast, `continue;` jumps to the next loop iteration and skips the rest of the loop body, rather than jumping to another case label. The `break` lesson gives concrete traces of interactions among switch, loops, and nested structures.

## 10. Common Mistakes

| Misconception | Correct understanding |
| --- | --- |
| "Each `case:` ends automatically like `if/else if`." | No; omitting `break` can fall through |
| "Java re-checks the condition at each subsequent label." | No; once jumped to the matching label, execution runs sequentially |
| "`break` in a switch always exits the method." | It only exits the innermost switch |
| "A `default` in the middle always stops before the next case." | It can still fall through |
| "`case 1: case 2:` is an error." | Valid and used to group labels |
| "Two cases can declare the same variable name because case creates a scope." | A case does not create a block; `{ }` is needed when appropriate |
| "`switch(null)` automatically runs `default`." | Normally throws `NullPointerException` in Java 17 |
| "`case x ->` also falls through without `break`." | Arrow rule `->` does not fall through |
| "`continue` in a switch moves to the next case." | It advances to the next loop iteration when the switch is inside a loop |
| "In a switch expression, `break` produces the return value." | Use `yield` or an appropriate switch rule |

## 11. Self-Check Exercises

1. What can `switch(1) { case 1: print("A"); case 2: print("B"); break; }` print?  
   *Answer:* `AB` in order, because `break` is missing after case 1.
2. If you add `break;` right after `print("A")`, does it still print `B`?  
   *Answer:* No.
3. With `case 1: case 2: System.out.println("yes"); break;`, do values 1 and 2 run the same body?  
   *Answer:* Yes.
4. Does `default` have to be placed at the end of a `switch` block?  
   *Answer:* No; however, placing it in the middle requires attention to fall-through.
5. In a switch with `default: print("D"); case 2: print("B"); break;`, what does selector value 9 produce?  
   *Answer:* Prints `D` then `B`.
6. Does using `break` inside a switch nested in a `for` loop terminate the loop as well?  
   *Answer:* No; it only exits the innermost switch.
7. Why should you use `{ }` for each case that declares local variables?  
   *Answer:* To create a clear scope and avoid name/initialization conflicts.
8. Does an arrow-style `switch` `case 1 -> ...` fall through into case 2?  
   *Answer:* No.
9. If the selector is a `null` `String` in standard Java 17, does `default` handle it?  
   *Answer:* No; handle null beforehand to avoid `NullPointerException`.

## Checklist

- [ ] Distinguish `case ...:` (colon style) from `case ... ->` (arrow style).
- [ ] Understand `case` entry points and **falling through** past subsequent labels if not stopped.
- [ ] Place `break` when each branch must be independent; clearly document intent when fall-through is deliberate.
- [ ] Know how to group multiple labels sharing a body.
- [ ] Do not assume `default` creates a stopping boundary.
- [ ] Use `{ }` blocks when declaring local variables inside a case.
- [ ] Distinguish `break`, `continue`, `return`, and `yield`.
- [ ] Handle null selectors before using standard Java 17 `switch`.

**Conclusion:** The biggest distinguishing feature of colon-style `switch` is **fall-through**: once a label is entered, Java executes the statements below sequentially until interrupted or the block ends. Use `break` deliberately, group labels when shared behavior is needed, and consider `->` to reduce the risk of unintended fall-through.