# Distinguishing Multiple Independent `if` Statements from an Exclusive Chain in Java

> **Java core — language-basics / if branching**  
> **Requirements:** Java 17+, single standalone Java file, standard library only.  
> **Goal:** Distinguish **multiple independent `if` statements** from an **`if / else if / else` chain**; predict how many branches execute, the order of condition checks, and choose the right syntax for the business logic.

## 1. Two structures that look similar but behave differently

**Multiple independent `if` statements** are separate statements:

~~~java
int score = 95;

if (score >= 60) {
    System.out.println("PASS");
}
if (score >= 80) {
    System.out.println("MERIT");
}
if (score >= 90) {
    System.out.println("HONOR");
}
// Prints all three lines: PASS, MERIT, HONOR.
~~~

Because all three conditions are true, **all three blocks run**. During normal execution flow, Java still checks the next `if` statement after finishing the previous one.

**An exclusive chain** uses `if / else if / else`:

~~~java
int score = 95;

if (score >= 90) {
    System.out.println("A");
} else if (score >= 80) {
    System.out.println("B");
} else if (score >= 60) {
    System.out.println("C");
} else {
    System.out.println("F");
}
// Prints only: A.
~~~

As soon as `score >= 90` is true, Java selects the `"A"` branch and **skips all subsequent `else if` conditions/branches** in the same chain. It does not run all three checks first and then pick a result.

## 2. Behavior comparison table

| Aspect | Multiple independent `if` statements | `if / else if / else` |
| --- | --- | --- |
| Number of branches that can run | **0, 1, or many** | **At most 1** |
| When the first condition is true | Still proceeds to subsequent `if` statements if flow is uninterrupted | Does not evaluate subsequent `else if` conditions |
| Overlapping conditions | Can trigger multiple actions | Selects the **first** true condition |
| When no condition is true | Runs no branch (unless other code follows) | Runs `else` if present |
| Typical purpose | **Non-mutually-exclusive** rules/actions | **Single-choice** outcomes/categories |

**Subtle point:** Do not claim that every independent `if` is *guaranteed* to be evaluated: an earlier branch might `return`, throw an exception, `break`, or `continue`, preventing control flow from reaching the next statement. The table describes normal continuing flow.

An `else if` chain may **omit `else`**; when every condition is false, the chain runs no branch.

## 3. When to use independent `if` statements?

Use independent `if` statements when multiple rules **can be true simultaneously** and each rule requires its own action.

~~~java
boolean sendEmail = true;
boolean saveLog = true;

if (sendEmail) {
    System.out.println("SEND_EMAIL");
}
if (saveLog) {
    System.out.println("SAVE_LOG");
}
// Prints both SEND_EMAIL and SAVE_LOG.
~~~

If changed to `if (sendEmail) ... else if (saveLog) ...`, saving the log will be **skipped** when sending email is chosen, even though `saveLog` is also true. That is a logic change, not just a formatting change.

Practical examples: applying multiple independent alerts, enabling multiple features, running multiple quality checks, or collecting multiple validation errors instead of stopping at the first error.

Conversely, if you only need to pick **one severity label** or **one priority processing route**, an exclusive chain is more appropriate.

## 4. When to use an `if / else if / else` chain?

When branches together determine **a single outcome**, an exclusive chain guarantees that only one branch is chosen.

Example classifying grades from highest to lowest:

~~~java
static String grade(int score) {
    if (score >= 90) {
        return "A";
    } else if (score >= 80) {
        return "B";
    } else if (score >= 60) {
        return "C";
    } else {
        return "F";
    }
}
~~~

**Condition order matters.** The misordered version below still compiles:

~~~java
static String wrongGrade(int score) {
    if (score >= 60) {
        return "C";
    } else if (score >= 80) {
        return "B"; // Unreachable for score >= 80.
    } else if (score >= 90) {
        return "A"; // Unreachable for score >= 90.
    }
    return "F";
}
~~~

Because a score of `95` satisfies `score >= 60` in the very first branch, the result is `"C"`, not `"A"`. To handle priority levels, check **higher thresholds before lower ones** or design genuinely disjoint conditions.

## 5. Overlapping conditions and the default branch

Consider `int score = 85` with three conditions `score >= 60`, `score >= 80`, `score >= 90`:

| Condition | With `score = 85` | Independent `if` | Exclusive chain ordered 90 → 80 → 60 |
| --- | --- | --- | --- |
| `score >= 90` | false | Does not run | Checked and skipped |
| `score >= 80` | true | Runs | **Selected and stops checking later branches** |
| `score >= 60` | true | Runs | **Not evaluated** |

Use multiple `if` statements to **attach multiple cumulative attributes** (PASS, MERIT). Use `else if` to **pick exactly one category** (A, B, C, F).

Even when conditions do not overlap, such as `x < 0` and `x > 0`, independent `if` statements *happen* to run at most one branch due to the mutually exclusive conditions themselves; **independent `if` syntax does not enforce that guarantee**.

When conditions do not cover all possibilities (for example `x < 0` and `x > 0` omit 0), use `else` when you want an explicit default result.

## 6. Are subsequent conditions evaluated?

The difference is not only **which block executes** but also **which conditional expressions are actually evaluated**.

~~~java
StringBuilder independentTrace = new StringBuilder();

if (check(independentTrace, "A", true)) {
    independentTrace.append("1");
}
if (check(independentTrace, "B", true)) {
    independentTrace.append("2");
}
// Trace: A1B2 — both A and B are checked and executed.
~~~

Whereas in an exclusive chain:

~~~java
StringBuilder exclusiveTrace = new StringBuilder();

if (check(exclusiveTrace, "A", true)) {
    exclusiveTrace.append("1");
} else if (check(exclusiveTrace, "B", true)) {
    exclusiveTrace.append("2");
}
// Trace: A1 — B is not called, no side effect from B.
~~~

In both snippets above, `check(log, label, value)` is a helper method defined in the runnable program below.

This matters if a condition contains method calls, data access, variable increments, or can throw an exception. **Do not convert independent `if` statements into `else if` merely to “optimize” the number of checks** if the business logic actually needs every rule evaluated.

## 7. Notes on `else` and dependent conditions

`else` always binds to the **nearest `if` without an `else`** when there are no braces changing the structure.

~~~java
if (isMember) {
    System.out.println("Member");
}
if (isActive) {
    System.out.println("Active");
} else {
    System.out.println("Inactive");
}
~~~

Here `else` belongs to **`if (isActive)`**, not to `if (isMember)` or “both `if` statements”. The two `if` statements remain independent.

Case with dependent conditions:

~~~java
String name = null;

// WRONG if assuming the first if blocks the second if:
// if (name == null) System.out.println("Missing");
// if (name.isBlank()) System.out.println("Blank"); // Potential NPE.

// RIGHT: mutually exclusive cases with a guard.
if (name == null) {
    System.out.println("Missing");
} else if (name.isBlank()) {
    System.out.println("Blank");
} else {
    System.out.println("Present");
}
~~~

With this chain, when `name == null`, Java does not evaluate `name.isBlank()`. When using independent `if` statements, you can replace it with `name != null && name.isBlank()` to guard the dependent side if each check still needs to run independently.

**Always use braces `{}`** to make branches explicit, especially when editing conditions or adding actions.

## 8. Standalone runnable Java 17+ program

Create the file **IndependentIfVsElseIfDemo.java**:

~~~java
public final class IndependentIfVsElseIfDemo {
    private static String tags(int score) {
        StringBuilder result = new StringBuilder();
        if (score >= 60) {
            result.append("PASS");
        }
        if (score >= 80) {
            result.append("+MERIT");
        }
        if (score >= 90) {
            result.append("+HONOR");
        }
        return result.length() == 0 ? "NONE" : result.toString();
    }

    private static String grade(int score) {
        if (score >= 90) {
            return "A";
        } else if (score >= 80) {
            return "B";
        } else if (score >= 60) {
            return "C";
        } else {
            return "F";
        }
    }

    private static String wrongGrade(int score) {
        if (score >= 60) {
            return "C";
        } else if (score >= 80) {
            return "B";
        } else if (score >= 90) {
            return "A";
        }
        return "F";
    }

    private static boolean check(
            StringBuilder log, String label, boolean value) {
        log.append(label);
        return value;
    }

    private static String nameStatus(String name) {
        if (name == null) {
            return "MISSING";
        } else if (name.isBlank()) {
            return "BLANK";
        }
        return "PRESENT";
    }

    public static void main(String[] args) {
        for (int score : new int[] {55, 60, 79, 80, 89, 90, 95}) {
            System.out.println("score=" + score
                    + ",tags=" + tags(score)
                    + ",grade=" + grade(score));
        }

        System.out.println("wrongOrdered95=" + wrongGrade(95));

        boolean sendEmail = true;
        boolean saveLog = true;
        StringBuilder independentActions = new StringBuilder();
        if (sendEmail) {
            independentActions.append("SEND_EMAIL");
        }
        if (saveLog) {
            if (independentActions.length() > 0) {
                independentActions.append("+");
            }
            independentActions.append("SAVE_LOG");
        }
        System.out.println("independentActions=" + independentActions);

        String exclusiveAction;
        if (sendEmail) {
            exclusiveAction = "SEND_EMAIL";
        } else if (saveLog) {
            exclusiveAction = "SAVE_LOG";
        } else {
            exclusiveAction = "NONE";
        }
        System.out.println("exclusiveAction=" + exclusiveAction);

        StringBuilder independentTrace = new StringBuilder();
        if (check(independentTrace, "A", true)) {
            independentTrace.append("1");
        }
        if (check(independentTrace, "B", true)) {
            independentTrace.append("2");
        }
        System.out.println("independentTrace=" + independentTrace);

        StringBuilder exclusiveTrace = new StringBuilder();
        if (check(exclusiveTrace, "A", true)) {
            exclusiveTrace.append("1");
        } else if (check(exclusiveTrace, "B", true)) {
            exclusiveTrace.append("2");
        }
        System.out.println("exclusiveTrace=" + exclusiveTrace);

        System.out.println("guardNull=" + nameStatus(null));
        System.out.println("guardBlank=" + nameStatus("  "));
        System.out.println("guardText=" + nameStatus("Java"));

        int value = 0;
        String independentNoMatch = "NONE";
        if (value < 0) {
            independentNoMatch = "NEGATIVE";
        }
        if (value > 0) {
            independentNoMatch = "POSITIVE";
        }
        System.out.println("independentNoMatch=" + independentNoMatch);

        String exclusiveFallback;
        if (value < 0) {
            exclusiveFallback = "NEGATIVE";
        } else if (value > 0) {
            exclusiveFallback = "POSITIVE";
        } else {
            exclusiveFallback = "ZERO";
        }
        System.out.println("exclusiveFallback=" + exclusiveFallback);
    }
}
~~~

Open a terminal in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 IndependentIfVsElseIfDemo.java
java IndependentIfVsElseIfDemo
~~~

**Exact expected stdout:**

~~~text
score=55,tags=NONE,grade=F
score=60,tags=PASS,grade=C
score=79,tags=PASS,grade=C
score=80,tags=PASS+MERIT,grade=B
score=89,tags=PASS+MERIT,grade=B
score=90,tags=PASS+MERIT+HONOR,grade=A
score=95,tags=PASS+MERIT+HONOR,grade=A
wrongOrdered95=C
independentActions=SEND_EMAIL+SAVE_LOG
exclusiveAction=SEND_EMAIL
independentTrace=A1B2
exclusiveTrace=A1
guardNull=MISSING
guardBlank=BLANK
guardText=PRESENT
independentNoMatch=NONE
exclusiveFallback=ZERO
~~~

The seven score lines demonstrate that independent `if` statements accumulate multiple tags while the exclusive chain chooses one grade. `wrongOrdered95=C` exposes wrong priority ordering. The two `Trace` lines show that `else if` does not evaluate B after A is true. `exclusiveFallback=ZERO` demonstrates the role of the `else` branch.

## 9. Checklist and practice exercises

Before deciding which structure to use, ask:

- Can one subject satisfy **multiple rules that should all run**, or must **only one outcome be chosen**?
- Do the conditions overlap? If so, select **all** or prioritize the **first condition**?
- Does evaluation order change the result or side effects?
- When every condition is false, is a default `else` branch needed?
- Is there any condition that depends on a guard (null, array index, state...)?

**Exercise 1.** With `int score = 90`, predict how many independent `if` statements are true for thresholds 60, 80, 90. How many branches will a descending `if/else if/else` chain run?

**Exercise 2.** Given two flags `sendEmail=true` and `saveLog=true`. Explain why changing two independent `if` statements into `if/else if` causes one action to be skipped.

**Exercise 3.** Reorder the threshold chain `>=60`, `>=80`, `>=90` into the correct order and test with score 95.

**Exercise 4.** Write handling for `String name` with three states—null, blank, non-empty—using `if/else if/else` without throwing `NullPointerException`.

**Exercise 5.** Write two methods: one collecting **all** matching alerts, and one returning the **highest-priority alert**. Which structure fits each method?

### Key takeaway

**Multiple independent `if` statements can execute multiple branches; `if / else if / else` is a chain that selects at most one branch — the first true branch.** With multiple `if` statements, subsequent conditions are still checked if flow continues normally; with `else if`, conditions after the chosen branch are not evaluated. Choose syntax based on **business semantics**, not merely line count.