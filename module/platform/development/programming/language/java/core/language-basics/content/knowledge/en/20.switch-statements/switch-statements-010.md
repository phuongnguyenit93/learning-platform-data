# Choosing `if` or `switch` Based on the Nature of the Condition — Java 17+

## 1. Decision Principle

Both `if/else if/else` and `switch` control execution flow, but they express **two different kinds of problems**:

- **`if`**: answers arbitrary **true/false** questions, such as "score is 70 or higher", "user is at least 18 years old **and** verified", or "emergency priority".
- **`switch`**: selects handling based on **a single discrete value** with fixed cases, such as status codes `1/2/3`, commands `"start"/"stop"`, or an `enum` constant.

~~~java
int score = 85;
if (score >= 90) {
    System.out.println("A");
} else if (score >= 70) {
    System.out.println("B");
} else {
    System.out.println("C");
}

String command = "start";
switch (command) {
    case "start" -> System.out.println("START");
    case "stop" -> System.out.println("STOP");
    default -> System.out.println("UNKNOWN");
}
~~~

**Exact stdout:**

~~~text
B
START
~~~

**Do not choose based on feelings like "switch looks shorter" or "if runs faster".** Choose based on the **kind of condition to express**, data domain rules, and maintainability.

## 2. Quick Selection Table

| Need | Usually choose | Reason |
|---|---|---|
| Checking `age >= 18` | `if` | Relational condition, not a fixed single value |
| Checking `0 <= score <= 100` | `if` | Combines multiple boolean conditions |
| Classifying scores into intervals 0–49, 50–69, 70–89, 90–100 | `if/else if` | Thresholds and bounds are meaningful |
| Rule `isAdmin || (verified && !blocked)` | `if` | Logic with `&&`, `||`, `!` |
| Handling `code == 1`, `code == 2`, `code == 3` | `switch` | Discrete cases of the same selector |
| Handling commands `"start"`, `"stop"` | `switch(String)` | Readable String value labels |
| Handling `Status.NEW/RUNNING/DONE` | `switch(enum)` | Finite set of clearly named values |
| A high-priority condition must be checked before others | `if/else if` | Order is part of the rule |
| Two actions must both run if two conditions are true | Two independent `if` statements | An `else if` chain selects only the first branch |
| Classifying `double` by thresholds | `if` | `double` is not a stable Java 17 switch selector |

A single problem can use **both**: `if` validates input, then `switch` handles valid command codes.

## 3. `if` Fits Continuous Ranges and Combined Conditions

Suppose valid scores are `[0,100]` with the rules:

| Score range | Result |
|---|---|
| Outside `[0,100]` | INVALID |
| `[90,100]` | A |
| `[70,90)` | B |
| `[50,70)` | C |
| `[0,50)` | D |

~~~java
static String grade(int score) {
    if (score < 0 || score > 100) {
        return "INVALID";
    }
    if (score >= 90) {
        return "A";
    } else if (score >= 70) {
        return "B";
    } else if (score >= 50) {
        return "C";
    }
    return "D";
}
~~~

This approach clearly exposes **thresholds** and **inclusive bounds**:

- 90 belongs to A, 70 belongs to B, 50 belongs to C.
- 100 is still valid, 101 is rejected.
- Check thresholds from highest to lowest; if `score >= 50` were placed first, grades A/B would be **shadowed** by the broader branch.

**Do not replace with:**

~~~java
// switch (score) {
//     case 90 -> "A";
//     case 70 -> "B";
//     default -> "C";
// }
~~~

The expression above matches **only the exact numbers 90 or 70**, not "90 or above" or "70 or above". Standard Java 17 switch **does not allow labels like `case score >= 90`**.

## 4. `if` Fits Multi-Variable Conditions and Priorities

~~~java
boolean eligible = age >= 18
        && verified
        && !banned;
~~~

The three checks above use **three inputs**, with AND and NOT relationships. `switch` cannot naturally replace this boolean expression.

With multiple priority rules:

~~~java
static String priority(int risk, boolean emergency) {
    if (risk < 0 || risk > 100) {
        return "INVALID";
    }
    if (emergency) {
        return "P0";
    } else if (risk >= 80) {
        return "P1";
    } else if (risk >= 50) {
        return "P2";
    }
    return "P3";
}
~~~

- **Emergency** overrides normal risk thresholds.
- When not an emergency, higher risk levels are evaluated first.
- Out-of-range data is rejected before classification.

**Branch order carries business meaning.** Do not reorder branches just because a condition looks shorter to put first.

If you need to print/flag **both properties** when both are true:

~~~java
if (score >= 50) {
    System.out.println("PASS");
}
if (score >= 90) {
    System.out.println("EXCELLENT");
}
~~~

With score 95, **both** are printed. With `else if`, only one branch runs. `switch` is also not a direct replacement for evaluating multiple independent properties.

## 5. `switch` Fits Selecting One of Many Discrete Values

~~~java
static String status(int code) {
    return switch (code) {
        case 1 -> "NEW";
        case 2 -> "RUNNING";
        case 3 -> "DONE";
        default -> "UNKNOWN";
    };
}
~~~

This is a **switch expression**, returning a `String`. It is natural because:

- It inspects only **one selector** `code`.
- Each `case` label is a discrete constant value.
- Arrow `->` branches do not fall through.
- `default` handles undeclared codes.

If you only want to log or perform actions without **producing a value**, use a switch **statement**:

~~~java
switch (code) {
    case 1 -> System.out.println("created");
    case 2 -> System.out.println("running");
    case 3 -> System.out.println("done");
    default -> System.out.println("unknown");
}
~~~

**Distinction:** `case ->` does not automatically make a switch an expression; **the usage context** determines whether it is a statement or an expression.

## 6. Check Selector Type Before Choosing Switch

Stable Java 17 (without preview) supports selectors of type `byte`, `short`, `char`, `int`, their four corresponding wrappers, `String`, or a specific enum. `long`, `float`, `double`, `boolean`, `Object`, and the remaining wrappers cannot be used directly.

If a business ID is `long`, do not cast it to `int` just to use switch, as doing so can lose information. Choose `if` or redesign the data model if appropriate. The first lesson in this chapter presents the full selector table and version scope.

## 7. Choosing `switch(String)`: Command Codes, Not Arbitrary Text

A command with a small, well-defined set of values fits switch very well:

~~~java
static String command(String input) {
    if (input == null) {
        return "MISSING";
    }
    String normalized = input.strip().toLowerCase(java.util.Locale.ROOT);

    return switch (normalized) {
        case "start", "run" -> "START";
        case "stop" -> "STOP";
        default -> "UNKNOWN";
    };
}
~~~

`switch(String)` matches by **content** and is case-sensitive. The example intentionally normalizes ASCII inputs such as `"RUN"` or `" Start "` before selecting the command.

**Important:**

- `null` must be checked first; a null String selector can throw `NullPointerException` in stable Java 17 switch, and `default` **does not catch null**.
- Do not assume lowercasing every string suits all business domains; IDs, tokens, or passwords may be case-sensitive.
- `case` must be a valid constant; you cannot use a runtime String variable as a case constant just because its current value is `"start"`.

## 8. `switch(enum)`: Clearly Named States

~~~java
enum Channel { WEB, MOBILE, API }

static String channelName(Channel channel) {
    if (channel == null) {
        return "MISSING";
    }
    return switch (channel) {
        case WEB -> "BROWSER";
        case MOBILE -> "PHONE";
        case API -> "SERVICE";
    };
}
~~~

Because all `Channel` constants are listed, the switch expression **does not need `default`**. This is advantageous when you want the compiler to help catch missing cases if the enum is extended.

Conversely, adding `default` is reasonable when there is truly a policy for unlisted values; do not add a default casually such that a new state is silently treated like an old one.

In a stable Java 17 enum switch, labels are written `case WEB`, **not** `case Channel.WEB`.

With nullable enums, you still must guard against null before the switch.

## 9. Choosing Statement or Expression

When you need to perform actions, use a switch statement; when you need to produce a value, use a switch expression. In Java 17, `->` branches do not fall through. `case:` code remains valid, though you must check whether `break` is needed to stop before the next branch. In a switch expression with a multi-statement block, use `yield` to produce the result. This choice comes **after** confirming the problem fits a discrete selector.

## 10. Requirement-Based Selection Questions

Before deciding, try answering in order:

~~~mermaid
flowchart TD
    A["Branching requirement"] --> B{"Condition is a range, comparison, multiple variables, or priority?"}
    B -- "Yes" --> C["Use if / else if"]
    B -- "No" --> D{"Select by a single selector of a type supported by switch?"}
    D -- "No" --> E["Use if or redesign the model"]
    D -- "Yes" --> F{"Discrete cases, case constants/enum?"}
    F -- "Yes" --> G["Use switch"]
    F -- "No" --> C
    G --> H{"Need to produce a value?"}
    H -- "Yes" --> I["Switch expression, -> and yield when needed"]
    H -- "No" --> J["Switch statement, prefer -> when fall-through is not wanted"]
~~~

This is a **practical guideline**, not a mandatory rule. Writing `if (code == 1) ... else if (code == 2)` is still valid; when there are many options on the same selector, switch is often easier to scan.

Do not decide purely on performance claims: the JVM/JIT and data characteristics affect optimizations, while **semantic accuracy and readability** come first. If performance truly matters, measure with proper benchmarks using representative data.

## 11. Combining `if` and `switch` When Needed

An application can both validate input and dispatch commands:

~~~java
static String execute(String command, boolean authenticated) {
    if (!authenticated) {
        return "DENIED";
    }
    if (command == null) {
        return "MISSING";
    }
    return switch (command) {
        case "start" -> "STARTED";
        case "stop" -> "STOPPED";
        default -> "UNKNOWN";
    };
}
~~~

In the example:

1. `if` enforces the **authentication rule** first.
2. `if` filters out a `null` selector.
3. `switch` dispatches based on the **command value**.

Order can matter: if unauthenticated, you should not reveal which command handlers exist to the caller. This is only a control-flow example; real access control also requires trusted-side authentication and verification.

## 12. Complete Java 17 Program

Create a file named **`IfOrSwitchDecisionDemo.java`**:

~~~java
import java.util.Locale;

public final class IfOrSwitchDecisionDemo {
    private IfOrSwitchDecisionDemo() {}

    enum Channel { WEB, MOBILE, API }

    static String grade(int score) {
        if (score < 0 || score > 100) return "INVALID";
        if (score >= 90) return "A";
        if (score >= 70) return "B";
        if (score >= 50) return "C";
        return "D";
    }

    static String ageGroup(int age) {
        if (age < 0) return "INVALID";
        if (age >= 65) return "SENIOR";
        if (age >= 18) return "ADULT";
        return "MINOR";
    }

    static String wrongAgeGroup(int age) {
        if (age >= 18) return "ADULT";
        if (age >= 65) return "SENIOR";
        return "MINOR";
    }

    static boolean eligible(int age, boolean verified, boolean banned) {
        return age >= 18 && verified && !banned;
    }

    static String priority(int risk, boolean emergency) {
        if (risk < 0 || risk > 100) return "INVALID";
        if (emergency) return "P0";
        if (risk >= 80) return "P1";
        if (risk >= 50) return "P2";
        return "P3";
    }

    static String status(int code) {
        return switch (code) {
            case 1 -> "NEW";
            case 2 -> "RUNNING";
            case 3 -> "DONE";
            default -> "UNKNOWN";
        };
    }

    static String command(String input) {
        if (input == null) return "MISSING";
        String normalized = input.strip().toLowerCase(Locale.ROOT);
        return switch (normalized) {
            case "start", "run" -> "START";
            case "stop" -> "STOP";
            default -> "UNKNOWN";
        };
    }

    static String channelName(Channel channel) {
        if (channel == null) return "MISSING";
        return switch (channel) {
            case WEB -> "BROWSER";
            case MOBILE -> "PHONE";
            case API -> "SERVICE";
        };
    }

    static String traditionalStatement(int code) {
        String result;
        switch (code) {
            case 1:
                result = "ONE";
                break;
            case 2:
                result = "TWO";
                break;
            default:
                result = "OTHER";
        }
        return result;
    }

    static String execute(String command, boolean authenticated) {
        if (!authenticated) return "DENIED";
        if (command == null) return "MISSING";
        return switch (command) {
            case "start" -> "STARTED";
            case "stop" -> "STOPPED";
            default -> "UNKNOWN";
        };
    }

    public static void main(String[] args) {
        System.out.println("grade 49=" + grade(49));
        System.out.println("grade 50=" + grade(50));
        System.out.println("grade 69=" + grade(69));
        System.out.println("grade 70=" + grade(70));
        System.out.println("grade 89=" + grade(89));
        System.out.println("grade 90=" + grade(90));
        System.out.println("grade 101=" + grade(101));

        System.out.println("age 17=" + ageGroup(17));
        System.out.println("age 18=" + ageGroup(18));
        System.out.println("age 65=" + ageGroup(65));
        System.out.println("wrong age 70=" + wrongAgeGroup(70));
        System.out.println("right age 70=" + ageGroup(70));

        System.out.println("eligible yes=" + eligible(20, true, false));
        System.out.println("eligible banned=" + eligible(20, true, true));
        System.out.println("eligible minor=" + eligible(17, true, false));

        System.out.println("priority emergency=" + priority(99, true));
        System.out.println("priority high=" + priority(99, false));
        System.out.println("priority low=" + priority(49, false));
        System.out.println("priority invalid=" + priority(-1, true));

        System.out.println("status 1=" + status(1));
        System.out.println("status 2=" + status(2));
        System.out.println("status 9=" + status(9));

        System.out.println("command start=" + command(" Start "));
        System.out.println("command run=" + command("RUN"));
        System.out.println("command stop=" + command("stop"));
        System.out.println("command pause=" + command("pause"));
        System.out.println("command null=" + command(null));

        System.out.println("channel WEB=" + channelName(Channel.WEB));
        System.out.println("channel MOBILE=" + channelName(Channel.MOBILE));
        System.out.println("channel null=" + channelName(null));

        System.out.println("statement 2=" + traditionalStatement(2));
        System.out.println("statement 5=" + traditionalStatement(5));

        System.out.println("execute blocked=" + execute("start", false));
        System.out.println("execute null=" + execute(null, true));
        System.out.println("execute start=" + execute("start", true));

        int[] sample = {70, 95};
        for (int score : sample) {
            if (score >= 50) System.out.println("passed " + score);
            if (score >= 90) System.out.println("excellent " + score);
        }
    }
}
~~~

**Requirements:** JDK 17 or higher; open terminal in the directory containing the file. Uses only standard JDK APIs, no Maven, Gradle, or preview features required.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 IfOrSwitchDecisionDemo.java
java -cp . IfOrSwitchDecisionDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\IfOrSwitchDecisionDemo.java
java -cp . IfOrSwitchDecisionDemo
~~~

### Exact expected stdout

~~~text
grade 49=D
grade 50=C
grade 69=C
grade 70=B
grade 89=B
grade 90=A
grade 101=INVALID
age 17=MINOR
age 18=ADULT
age 65=SENIOR
wrong age 70=ADULT
right age 70=SENIOR
eligible yes=true
eligible banned=false
eligible minor=false
priority emergency=P0
priority high=P1
priority low=P3
priority invalid=INVALID
status 1=NEW
status 2=RUNNING
status 9=UNKNOWN
command start=START
command run=START
command stop=STOP
command pause=UNKNOWN
command null=MISSING
channel WEB=BROWSER
channel MOBILE=PHONE
channel null=MISSING
statement 2=TWO
statement 5=OTHER
execute blocked=DENIED
execute null=MISSING
execute start=STARTED
passed 70
passed 95
excellent 95
~~~

**How to read the output:**

1. The boundary points 49/50/69/70/89/90 show that `if` suits **thresholds**, and 101 is rejected before grading.
2. `wrong age 70=ADULT` is a **broad branch shadowing a narrow branch** bug; fixed by checking `age >= 65` first.
3. `eligible` uses multiple boolean variables and combined conditions; `priority` has emergency precedence.
4. `status` handles discrete codes; `command` handles normalized Strings; `channelName` handles enums.
5. `traditionalStatement` uses `break` to prevent fall-through; `execute` uses `if` guards before `switch`.
6. Two independent `if` statements allow `95` to print **both** `passed` and `excellent`.

## 13. Common Mistakes

| Mistake | Consequence | Appropriate approach |
|---|---|---|
| Using switch to check `score >= 90` | `case 90` only matches the number 90 | Use `if` for thresholds |
| Choosing switch for `double` or `long` on stable Java 17 | Compile error | Use `if` or redesign the type |
| Placing `age >= 18` before `age >= 65` | The senior branch is shadowed | Check specific/higher-priority thresholds first |
| Using `else if` for two properties that must both be reported | Only the first true branch runs | Two independent `if` statements |
| Not validating scores outside `[0,100]` | Score 101 could become A | Guard the range first |
| Using `switch(String)` with null | NullPointerException | Check for null beforehand |
| Thinking String switch compares references with `==` | Wrong matching mental model | Switch compares content, case-sensitively |
| Forgetting `break` in `case:` form | Unintended fall-through | Use `break` or `case ->` |
| Thinking `case ->` exists only in switch expressions | Switch statements also support it | Look at the context |
| Omitting `default` in a switch expression on `int` | Does not cover values | Add default |
| Adding `default` to an enum hiding every change | Might miss new states that need handling | Consider enum exhaustiveness |
| Choosing solely because "switch is faster" | Performance is not guaranteed in every situation | Choose by semantics, measure if needed |
| Normalizing Strings unconditionally | May alter meaning of case-sensitive tokens | Normalize only when requirements allow |

## 14. Exercises with Solutions

### Exercise A — Interval classification

Requirement: temperature below 0 → COLD, from 0 to below 30 → NORMAL, 30 or above → HOT.

**Should choose:** `if/else if`, because it compares **ranges**:

~~~java
String label;
if (temperature < 0) {
    label = "COLD";
} else if (temperature < 30) {
    label = "NORMAL";
} else {
    label = "HOT";
}
~~~

### Exercise B — Action code selection

Code `1` → CREATE, `2` → UPDATE, `3` → DELETE, anything else → UNKNOWN.

**Should choose:** `switch`, because these are discrete values:

~~~java
String action = switch (code) {
    case 1 -> "CREATE";
    case 2 -> "UPDATE";
    case 3 -> "DELETE";
    default -> "UNKNOWN";
};
~~~

### Exercise C — Multiple conditions

Requirement: accept only when age is 18 or older, verified, and not blocked.

**Should choose:** boolean expression / `if`:

~~~java
boolean accepted = age >= 18 && verified && !blocked;
~~~

Do not use `switch` for these three independent conditions.

### Exercise D — Two actions that can both apply

With score 95, both PASS and EXCELLENT must be recorded.

**Solution:** two independent `if` statements, not `else if`:

~~~java
if (score >= 50) System.out.println("PASS");
if (score >= 90) System.out.println("EXCELLENT");
~~~

**Exact stdout:**

~~~text
PASS
EXCELLENT
~~~

### Exercise E — `switch` and `null`

~~~java
String command = null;
// switch (command) {
//     case "start" -> System.out.println("start");
//     default -> System.out.println("unknown");
// }
~~~

**Solution:** do not use `default` to replace a null guard; a null String selector causes NPE in stable Java 17. Check `if (command == null)` before switching.

## 15. Checklist and Conclusion

- [ ] Choose `if` when relational comparisons, value ranges, combined conditions, or priorities are needed.
- [ ] Choose `switch` when checking multiple **discrete values of the same valid selector**.
- [ ] Distinguish an `else if` chain from multiple independent `if` statements.
- [ ] Check lower bounds, upper bounds, and classification thresholds.
- [ ] Do not place a broad condition first and shadow specific branches.
- [ ] Know the supported selector types in non-preview Java 17.
- [ ] Know that String switch compares content and is case-sensitive.
- [ ] Check for null before switching on String, enum, and wrapper selectors.
- [ ] Know that `case:` switch statements can fall through; `case ->` does not.
- [ ] Know that switch expressions produce a result and use `yield` when a branch is a block.
- [ ] Do not overuse `default` to hide important new enum cases.
- [ ] Do not decide based on speed without appropriate measurement.
- [ ] Run `IfOrSwitchDecisionDemo.java` with Java 17+ and verify exact stdout.

**Conclusion:** Choose `if` to **express a boolean condition** (thresholds, ranges, combinations, priorities), and choose `switch` to **dispatch handling across a known set of discrete values**. The two constructs can be combined: use `if` to guard/validate, and use `switch` to select the action. What matters most is **matching the nature of the condition, having clear boundaries, and keeping the code maintainable**.