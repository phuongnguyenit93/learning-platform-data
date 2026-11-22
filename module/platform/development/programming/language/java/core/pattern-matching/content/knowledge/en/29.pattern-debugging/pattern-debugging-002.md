# Setting Breakpoints in a Guarded Switch Case (Java 21+)

## 1. Goal: Pinpoint Exactly Where the Condition Fails

Since Java 21, `switch` supports **pattern matching** and **`when` guards**. A guarded case branch involves two decision steps:

1. **Does the pattern match the selector?** For example, does `Login(User(var name, var active), var failedAttempts)` match the object's structure?
2. **Does the guard return `true`?** For example, does `when canEnter(name, active, failedAttempts)` accept the deconstructed values?

Only when **both** succeed does Java select the branch and execute the body on the right side of `->`. If the pattern does not match, the guard is **not evaluated**; if the pattern matches but the guard is false, Java continues checking subsequent matching `case` branches.

When debugging, this leads to a common misconception: **setting a breakpoint only inside the guarded case body and concluding the code does not run**. A breakpoint in the body might not be hit because the pattern failed **or** because the guard returned false. It does not distinguish between those two causes.

This lesson shows how to place breakpoints at the exact observation points to answer:

- What is the actual type and value of the selector?
- Have the nested record patterns matched yet?
- Which pattern variables are observable and in what scope?
- Was the guard called or skipped? Which value caused the guard to return false?
- When the guarded case is not selected, which fallback branch does the code fall into?
- How do you create a reliable stopping point when the IDE/JVM does not allow setting breakpoints directly on individual parts of `when`?

The examples use **JDK 21+**, with no preview features required. IDE actions are described according to general Java debugger principles; button names or the ability to place breakpoints directly on a `when` expression may vary across IDEs and compiler builds.

## 2. Understand the Evaluation Order Before Setting Breakpoints

Consider a small snippet:

~~~java
case Login(User(var name, var active), var failedAttempts)
        when canEnter(name, active, failedAttempts) -> {
    String result = "ALLOW:" + name;
    yield result;
}
~~~

This is **one branch inside a switch expression**, not a standalone program. It operates according to the following flow:

~~~text
Incoming selector
        |
        v
Matches Login(...) ?
   | no      | yes
   v         v
Other branch Matches User(...) component ?
             | no       | yes
             v          v
             Other      Bind name, active, failedAttempts
             branch     |
                        v
                 Call canEnter(...)
                    | false    | true
                    v          v
                 Other      Run -> body and yield
                 branch
~~~

Different observation points provide different information:

| Breakpoint location | When does it pause? | What can be inferred |
| --- | --- | --- |
| Before `switch` | Every time the method is entered | You can inspect the original selector; you do not yet know which pattern matches |
| Inside `canEnter` called from `when` | When the pattern has matched and the guard is evaluated | Confirms the guard ran; lets you inspect inputs and subconditions |
| On an executable statement in the guarded case body | Only when the pattern matches **and** the guard is true | The branch was selected; pattern variables are in scope |
| In the body of a fallback branch of the same `Login` type | When earlier specific `Login` branches were not selected | Identifies the failure path; helps determine which branch was rejected |
| Inside `case null` or `default` if it has an executable body | When entering the corresponding branch | Distinguishes a null selector from an unsupported type |

**Conclusion:** placing a breakpoint in the selected branch body cannot tell you **why** the branch was not selected. To inspect a false guard, place a breakpoint **inside the guard method** or in the corresponding fallback branch.

## 3. Choose a Problem with an Easily Testable Guard

Suppose an application routes login commands:

~~~java
record User(String name, boolean active) {}
record Login(User user, int failedAttempts) {}
record Logout(String userId) {}
~~~

A `Login` is allowed when:

1. The `User` record exists and is not null.
2. `name` is not null and not blank (not all whitespace).
3. `active == true`.
4. The number of failed login attempts is within `0 <= failedAttempts < 3`.

If `Login` contains a `User` but violates a rule, return `"DENY:policy"`. If `Login.user == null`, return `"DENY:no-user"`. For `Logout`, require `userId` to be non-null and non-blank.

Here, the input records **intentionally have no constructor validation**. The goal is to simulate unvalidated data to observe how patterns and guards behave. In a real application, mandatory invariants can be enforced earlier in constructors or at boundaries.

We extract the guard into a clearly named method:

~~~java
static boolean canEnter(String name, boolean active, int failedAttempts) {
    boolean validName = name != null && !name.isBlank();
    boolean validAttempts = failedAttempts >= 0 && failedAttempts < 3;
    boolean result = validName && active && validAttempts;
    return result;
}
~~~

**Why extract a method?** Because this is the most reliable place to set a breakpoint. IDEs typically create stable stopping points on statements like `boolean validName = ...` or `boolean result = ...`, allowing you to inspect each condition rather than trying to place a breakpoint on a long `when` expression where line-level debug info may lack granularity.

Note: `canEnter` must **not mutate state**. A guard is used to decide branch selection, so avoid I/O, incrementing counters, writing to a database, or mutating objects inside a guard. During debugging, re-evaluating an expression with side effects via Evaluate Expression or a logpoint can also alter the actual execution path.

## 4. Use Breakpoints Before the Selector and Inside the Guard

The routing method:

~~~java
static String route(Object input) {
    return switch (input) {
        case null -> "IGNORED:null";

        case Login(User(var name, var active), var failedAttempts)
                when canEnter(name, active, failedAttempts) -> {
            String result = "ALLOW:" + name;
            yield result;
        }

        case Login(User(var name, var active), var failedAttempts) -> {
            String result = "DENY:policy";
            yield result;
        }

        case Login(var user, var failedAttempts) -> {
            String result = "DENY:no-user";
            yield result;
        }

        case Logout(var id) when id != null && !id.isBlank() ->
                "LOGOUT:" + id;

        case Logout(var id) -> "DENY:logout-id";
        default -> "IGNORED:type";
    };
}
~~~

This is a method of the class containing the three records `User`, `Login`, and `Logout`. Section 9 provides the complete class and `main` method.

### Step 1 — Pause before `switch`

Set a breakpoint on the `return switch (input) {` line or a stable executable line immediately before it (you can add a temporary local variable while debugging if needed).

Inspect:

- Is `input == null`?
- Is the runtime type of `input` `Login`, `Logout`, or something else?
- If `input` is `Login`, what are the values of `user` and `failedAttempts`?
- If `user == null`, the nested `User(...)` pattern **does not match**, so the `canEnter` guard is not called for this branch.

Before `switch`, the pattern variables `name` and `active` are **not yet declared in the current scope**; only inspect the selector and its fields/accessors safely. Do not try to Evaluate Expression on `name` before the pattern has matched.

### Step 2 — Pause in `canEnter`

Set a breakpoint at:

~~~java
boolean validName = name != null && !name.isBlank(); // BP-GUARD-NAME
~~~

When paused here, the debugger can display the parameters `name`, `active`, and `failedAttempts`. Continue with **Step Over** to the line:

~~~java
boolean result = validName && active && validAttempts; // BP-GUARD-RESULT
~~~

At this point, you can see the computed values of `validName` and `validAttempts`, then step forward to see `result`. If the value is null, `name != null` prevents `name.isBlank()` from running thanks to short-circuit evaluation.

**Crucial point:** if `input` is `Login(null, 0)`, the breakpoint inside `canEnter` **will not pause** for that call, because `User(...)` in the nested pattern does not match. If `input` is `Login(new User(null, true), 0)`, `User` exists, the `var name` pattern binds null; `canEnter` **is still called**, and `validName` will be false.

### Step 3 — Pause inside the guarded case body

Set a breakpoint on the executable statement:

~~~java
String result = "ALLOW:" + name; // BP-ALLOW
~~~

If the breakpoint pauses here, it is guaranteed that **both the pattern and the guard for that branch succeeded**, so you can inspect `name`, `active`, and `failedAttempts` within the branch's scope. The `switch` expression body uses `yield result;` to return a value; `yield` is different from `return` of the enclosing method.

If the breakpoint does **not** pause, check whether `canEnter` was called and which fallback branch received the selector. Do not immediately conclude that Java "skipped the case".

## 5. Set Breakpoints in Fallback Branches to Trace the Fallthrough Path

The example has two important fallback branches:

~~~java
case Login(User(var name, var active), var failedAttempts) -> {
    String result = "DENY:policy";  // BP-DENY-POLICY
    yield result;
}

case Login(var user, var failedAttempts) -> {
    String result = "DENY:no-user"; // BP-DENY-USER
    yield result;
}
~~~

The `DENY:policy` branch has the same **nested record pattern** as the allowed branch, but **without a guard**. If the previous branch's guard returns false, this branch can receive the value. For example:

- `User("Lan", false)`: the pattern matches; `canEnter` runs and returns false because `active == false`.
- `User("Lan", true)` with `failedAttempts == 3`: the guard returns false because the threshold is reached.
- `User(null, true)`: the `User(var name, ...)` pattern matches, but the guard returns false because the name is null.

The `DENY:no-user` branch has `Login(var user, var failedAttempts)`, which does not require `user` to be a non-null `User` record. A `Login(null, 0)` can fall into this branch because the two earlier branches containing `User(...)` fail to match at the nested record level.

**Important warning about `var`:** the component pattern `var user` can match null. `var` performs type inference, not validation. Just because a broader pattern matches does not mean the data is domain-valid.

Setting all three breakpoints `BP-GUARD-NAME`, `BP-DENY-POLICY`, and `BP-DENY-USER` lets you build an observation table:

| Input | Was guard called? | Terminal branch | Result |
| --- | --- | --- | --- |
| `Login(User("Lan", true), 2)` | Yes, returns true | `BP-ALLOW` | `ALLOW:Lan` |
| `Login(User("Lan", true), 3)` | Yes, returns false | `BP-DENY-POLICY` | `DENY:policy` |
| `Login(User(null, true), 1)` | Yes, returns false | `BP-DENY-POLICY` | `DENY:policy` |
| `Login(null, 0)` | No | `BP-DENY-USER` | `DENY:no-user` |
| `Logout("A1")` | No, `Login` branches do not match | `Logout` branch | `LOGOUT:A1` |
| `null` | No | `case null` | `IGNORED:null` |

Thus, **breakpoints where the guard evaluates** and **breakpoints where execution falls back** complement each other, rather than trying to diagnose every cause with a single breakpoint on the `->` arrow.

## 6. Why Breakpoints Directly on `when` Are Sometimes Awkward

The snippet:

~~~java
case Login(User(var name, var active), var failedAttempts)
        when name != null && !name.isBlank()
                && active && failedAttempts < 3 -> {
    // ...
}
~~~

is structurally valid syntax when placed inside an appropriate `switch`; however, this snippet omits the `failedAttempts >= 0` rule, so it is **not completely equivalent** to the `canEnter` method above. This is an illustrative snippet, not a drop-in replacement in the main file.

Regarding debugging:

- IDEs may allow breakpoints at certain positions on the `case` or `when` line, but accuracy depends on **debug information**, how the compiler maps expressions to bytecode, and the debugger.
- A breakpoint placed on the `when` line may be **relocated by the IDE to a different executable position**; do not assume every subcondition in `&&` has its own line breakpoint.
- **Step Into** while on the guard-calling line can enter `canEnter`. When you need to observe both true and false guard outcomes, the reliable approach is to set a breakpoint directly inside the method.
- If a guard is a long inline expression without a method call, you can temporarily **Extract Method** into a pure helper with a business-meaningful name, or place a breakpoint in the fallback branch for comparison.
- If the compiler or IDE does not stop where expected, do not randomly alter business logic just to force a breakpoint. Check the **executable lines**, IDE-verified breakpoint markers, debug info, and the current stack frame.

When debugging complex cases, a small `canEnter` method also lets you write unit tests directly for the conditions instead of relying solely on pausing the program in the IDE.

## 7. Conditional Breakpoints, Logpoints, and Evaluate Expression

Once you know the right stopping points, you can reduce noise using the following techniques.

### Conditional breakpoints

If you only want to pause when the failure count reaches the threshold, set a breakpoint in `canEnter` with a condition such as:

~~~java
failedAttempts == 3
~~~

A breakpoint's condition expression is evaluated in the **paused context**. If the breakpoint is inside `canEnter`, `failedAttempts` is a method parameter; if it is before `switch`, pattern variables may not be in scope yet, so you must evaluate against `input`.

When filtering by name:

~~~java
name == null
~~~

make sure the breakpoint is inside a method that has `name` as a parameter or inside a branch where the pattern variable is in scope. An expression like `name.equals("Lan")` is **unsafe** if `name` can be null; prefer `"Lan".equals(name)` or a null-safe condition.

### Logpoints (logging breakpoints)

If your IDE supports logpoints, you can log `name`, `active`, and `failedAttempts` upon entering the guard without pausing on every call. Avoid logging personal data, credentials, or security tokens in production environments.

A logpoint should use a simple, side-effect-free expression. It does not replace checking the logical cause: a logpoint inside `BP-ALLOW` only fires when the guard is already true; to see false guards, log inside `canEnter` or in the fallback branch.

### Evaluate Expression and Watches

When paused at `BP-GUARD-RESULT`, you can inspect:

~~~java
validName
active
validAttempts
validName && active && validAttempts
~~~

The lines above are **expressions to enter individually in the Evaluate Expression/Watches window**, not complete Java statements. You do not need to modify code to print every value.

Avoid evaluating getters or methods with side effects in Watches or conditional expressions: a debugger may re-evaluate them multiple times. Keep guard methods pure so observation does not alter results.

### Exception breakpoints

If the program throws a `NullPointerException` or an unexpected exception, an **exception breakpoint** can help locate where it originates. However, an exception breakpoint **will not show every time a guard returns false**, because a false guard is normal control flow, not an exception.

## 8. A Systematic Debugging Workflow for a Guarded Case

A practical workflow you can apply in IntelliJ IDEA, Eclipse, or VS Code with a suitable Java debugger:

1. **Compile with debug information.** Use `javac -g --release 21 ...`; the `-g` flag generates debug information, including local variable tables.
2. **Pick a minimal reproducer.** Instead of running the entire system, isolate one input where the guarded case is not selected as expected.
3. **Pause before `switch`.** Inspect the runtime type and value of the selector; check whether any nested record component could be null.
4. **Set a breakpoint inside the guard method.** Confirm whether the guard is actually called. If not, check the pattern or whether an earlier case already handled the input.
5. **Step Over each condition.** Find which boolean variable turns false; pay attention to `&&` short-circuit order and nullability.
6. **Set breakpoints in both the selected branch body and fallback branches.** Determine where execution goes after the guard returns true or false.
7. **Check pattern variable scope.** Variables `name`, `active`, and `failedAttempts` are in scope after the pattern matches, not across unrelated branches or before `switch`.
8. **Check case ordering.** A broader case placed earlier can dominate a more specific case or change branch selection; `case null` is needed to handle a null selector if the API permits null.
9. **Turn the root cause into a test.** Once you understand the issue, write an assertion for that case to prevent regressions.
10. **Clean up temporary breakpoints and instrumentation.** Do not leave behind logs containing sensitive data or logic changes made solely for debugging.

**Note on stepping:** `Step Over` executes the current statement without entering method calls; `Step Into` can enter `canEnter`; `Resume` continues to the next breakpoint. When multiple calls run back-to-back, the debugger may pause multiple times at the same breakpoint; read the **call stack** and input values to distinguish each invocation.

## 9. Complete Java 21 Program with Clear Breakpoint Locations

Save as **`GuardedCaseBreakpointsDemo.java`**. The `BP-*` comments mark suggested breakpoint locations on **executable lines**.

~~~java
public class GuardedCaseBreakpointsDemo {
    record User(String name, boolean active) {}
    record Login(User user, int failedAttempts) {}
    record Logout(String userId) {}

    private static int passed = 0;

    static boolean canEnter(String name, boolean active, int failedAttempts) {
        boolean validName = name != null && !name.isBlank(); // BP-GUARD-NAME
        boolean validAttempts = failedAttempts >= 0 && failedAttempts < 3;
        boolean result = validName && active && validAttempts; // BP-GUARD-RESULT
        return result;
    }

    static String route(Object input) {
        return switch (input) {
            case null -> "IGNORED:null";

            case Login(User(var name, var active), var failedAttempts)
                    when canEnter(name, active, failedAttempts) -> {
                String result = "ALLOW:" + name; // BP-ALLOW
                yield result;
            }

            case Login(User(var name, var active), var failedAttempts) -> {
                String result = "DENY:policy"; // BP-DENY-POLICY
                yield result;
            }

            case Login(var user, var failedAttempts) -> {
                String result = "DENY:no-user"; // BP-DENY-USER
                yield result;
            }

            case Logout(var id) when id != null && !id.isBlank() ->
                    "LOGOUT:" + id;

            case Logout(var id) -> "DENY:logout-id";
            default -> "IGNORED:type";
        };
    }

    static void check(String label, Object input, String expected) {
        String actual = route(input);
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    label + ": expected " + expected + ", got " + actual);
        }
        passed++;
        System.out.println("PASS " + label + " -> " + actual);
    }

    public static void main(String[] args) {
        check("accepted",
                new Login(new User("Lan", true), 2), "ALLOW:Lan");
        check("accepted-zero",
                new Login(new User("Lan", true), 0), "ALLOW:Lan");
        check("at-limit",
                new Login(new User("Lan", true), 3), "DENY:policy");
        check("inactive",
                new Login(new User("Lan", false), 1), "DENY:policy");
        check("blank-name",
                new Login(new User("  ", true), 1), "DENY:policy");
        check("null-name",
                new Login(new User(null, true), 1), "DENY:policy");
        check("negative-count",
                new Login(new User("Lan", true), -1), "DENY:policy");
        check("missing-user", new Login(null, 0), "DENY:no-user");
        check("logout-ok", new Logout("A1"), "LOGOUT:A1");
        check("logout-blank", new Logout(" "), "DENY:logout-id");
        check("logout-null", new Logout(null), "DENY:logout-id");
        check("null-selector", null, "IGNORED:null");
        check("other-type", 42, "IGNORED:type");

        System.out.println("ALL PASSED: " + passed);
    }
}
~~~

Compile and run with JDK 21 or later:

~~~bash
javac -g --release 21 GuardedCaseBreakpointsDemo.java
java GuardedCaseBreakpointsDemo
~~~

The `-g` flag helps the debugger, while `--release 21` compiles against Java 21 APIs and language rules. When running builds via other tools (Maven, Gradle, IDE), ensure the corresponding source/release settings and debug information are configured.

**Exact output:**

~~~text
PASS accepted -> ALLOW:Lan
PASS accepted-zero -> ALLOW:Lan
PASS at-limit -> DENY:policy
PASS inactive -> DENY:policy
PASS blank-name -> DENY:policy
PASS null-name -> DENY:policy
PASS negative-count -> DENY:policy
PASS missing-user -> DENY:no-user
PASS logout-ok -> LOGOUT:A1
PASS logout-blank -> DENY:logout-id
PASS logout-null -> DENY:logout-id
PASS null-selector -> IGNORED:null
PASS other-type -> IGNORED:type
ALL PASSED: 13
~~~

### Three Breakpoint Experiments to Try

**Experiment A — guard is true:** set breakpoints at `BP-GUARD-NAME` and `BP-ALLOW`, and run the `accepted` case. The debugger enters `canEnter`, showing `validName == true` and `validAttempts == true`; then the program selects the `ALLOW` branch.

**Experiment B — guard is false:** set breakpoints at `BP-GUARD-RESULT` and `BP-DENY-POLICY`, and run the `at-limit` case. `failedAttempts == 3` makes `validAttempts == false`; the `ALLOW` branch does not run, and `DENY:policy` is selected next.

**Experiment C — pattern does not match:** set breakpoints at `BP-GUARD-NAME` and `BP-DENY-USER`, and run the `missing-user` case. `Login` matches on the outside, but `User(...)` fails to match when `user == null`. Therefore `canEnter` is not called, and the `DENY:no-user` branch handles the input.

In all three experiments, use **Resume** to advance to the next breakpoint; if you run all 13 cases back-to-back, the breakpoint inside `canEnter` will be hit multiple times. To observe a single scenario in isolation, you can temporarily create a method calling `route` with one input or use a conditional breakpoint instead of stepping through multiple runs.

### Why Are Assertions Valuable?

The `check` method does more than print output. It compares `route(input)` against the expected string and throws `AssertionError` if they differ. Thus `ALL PASSED: 13` only appears when every case is correct. The null, blank-name, and negative-count cases help observe paths that happy-path testing often misses.

## 10. Common Debugging Mistakes

**Mistake 1 — placing a breakpoint only in the guarded case body.** Not pausing does not tell you whether the pattern failed or the guard returned false. Add breakpoints in the guard method and fallback branches.

**Mistake 2 — expecting the guard to run even when a nested record does not match.** For `Login(null, 0)`, the `User(...)` pattern fails before `canEnter` is called. Inspect the selector before `switch` or pause in the broader `Login(var user, ...)` branch.

**Mistake 3 — assuming `var` guarantees non-null.** `var name` and `var user` can bind null from a record component; check according to your contract before calling methods on them.

**Mistake 4 — assuming there is a breakpoint on each operand of `&&`.** The JVM/IDE operates on bytecode and line-number/debug info; a long compound expression does not necessarily have separate stopping points for each operand. Extract Method or compute intermediate booleans if you need to inspect them individually.

**Mistake 5 — placing a breakpoint in a guard with side effects.** An expression evaluator or logpoint can re-invoke a method and mutate state. Keep guards and debugger expressions **pure**, avoiding statements that modify data.

**Mistake 6 — using `default` to explain every input.** `case null` is a separate case; `default` in a pattern switch does not automatically accept a null selector. Failing to match other subtypes also does not mean a particular subtype's guard was called.

**Mistake 7 — reading a pattern variable where it is not in scope.** `name` is only available in the guard and branch body once its corresponding pattern has matched; before `switch` or in another branch, that variable may not exist.

**Mistake 8 — putting a fallback branch before a guarded branch.** A broader branch can shadow a more specific one, causing a compiler dominated-case error or changing branch selection. Keep the guarded case before the fallback for the same variant.

**Mistake 9 — treating a missing breakpoint hit as a compiler bug.** The input may not reach the branch, the code may have been compiled differently, the running class may not match the open file, or the IDE may relocate the breakpoint. Verify the call stack, running class, build, and executable line.

**Mistake 10 — forgetting to turn a debugged path into an automated test.** Breakpoints help find the root cause once; regression tests keep the behavior from breaking again during refactoring.

## 11. Checklist When a Guarded Case "Doesn't Run"

1. What selector was actually passed into `switch`?
2. Is the case placed **after** a broader branch or dominated by another case?
3. Does the selector have the exact type of the outer pattern?
4. Could a nested record component be null, causing the inner pattern not to match?
5. Was the method in `when` actually called? If not, did the pattern fail to match?
6. Which guard condition returned false? `name != null`, `active`, or the `failedAttempts` threshold?
7. When the guard is false, which fallback case is selected?
8. Is the breakpoint placed on an actual executable line, and is debug info available?
9. Are you using a breakpoint condition/logpoint that causes re-evaluation or side effects?
10. Have you added tests verifying the true, false, null, and type-mismatch branches?

### Practice Exercises

- Change the threshold `failedAttempts < 3` to `failedAttempts < 5`. Set a breakpoint at `BP-GUARD-RESULT`, inspect an input with value 3, and update the `at-limit` expectation to match the new rule.
- Set a conditional breakpoint `name == null` inside `canEnter`. Compare the behavior of `null-name` and `missing-user`; explain why only one case can hit the breakpoint inside the guard.
- Temporarily change `Login(User(...))` to `Login(var user, ...)` and write a guard checking `user != null`. Set breakpoints to see how the evaluation order changes.
- Create a fallback `case Login(...)` that returns a specific error code for `failedAttempts < 0`; observe case ordering and update the `negative-count` test.
- Convert the return value to a `sealed interface Decision` with two records `Allowed` and `Denied`. Use an exhaustive `switch` to print the result and set a breakpoint in each branch.

**Key takeaway:** For a guarded case, there are **three distinct questions**: *did the pattern match*, *was the guard called and what did it return*, and *which case actually ran*. Set breakpoints before `switch` to inspect the selector, inside the **guard method** to observe true/false conditions, and inside the **guarded case body and fallback branches** to confirm the control flow. Do not rely solely on a breakpoint on `->` or confuse a skipped guard with a guard returning false.
