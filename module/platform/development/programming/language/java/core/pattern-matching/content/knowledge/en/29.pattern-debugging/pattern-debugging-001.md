# Reading Pattern Variable Values When Debugging

**Topic:** Java Core Pattern Matching — Debugging. This guide explains how to inspect **pattern variables** in a debugger when using **instanceof**, **record patterns**, and **switch patterns**. The full examples use **Java 21 or later** (record patterns/JEP 440 and pattern matching for switch/JEP 441 are finalized), without needing `--enable-preview`.

## 1. What is a pattern variable and why is it hard to inspect when debugging?

A **pattern variable** is a local variable created when a pattern successfully binds a value. For example:

~~~java
if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

When the expression `value instanceof String text` returns true, the variable **text** has type String and is allowed to be used inside the if branch. With a **record pattern**, the compiler can also bind the components of a record:

~~~java
record Point(int x, int y) {}

// Illustration snippet inside a method:
if (value instanceof Point(int x, int y)) {
    System.out.println(x + y);
}
~~~

When debugging, learners often encounter phenomena such as: seeing the variable **value** but not seeing **x, y**; adding a watch for a pattern variable and getting a variable-not-found error; a breakpoint placed in a case branch never triggering; or seeing a null value even though they assumed "if the pattern matched, the data must be non-null."

To read values accurately, you must distinguish:

1. **Has the pattern been evaluated and matched yet?**
2. **Has control flow reached a region where the pattern variable is in scope?**
3. **Is the debugger paused at the right stack frame and the right source location?**
4. **Does the compiled code have debug information for local variables?**
5. **Is this the variable bound by the pattern, or another variable with the same name in a different branch?**

**Principle:** a pattern variable is not a field of an object and does not exist at every point in a method. Its scope and lifetime depend on the pattern structure together with control flow; a debugger can only display it meaningfully when the program is paused at an appropriate location.

## 2. Flow scoping: the condition that determines where a variable can be read

Java uses **flow scoping**: the scope of a pattern variable is based on the execution paths where the compiler knows the pattern has matched.

### 2.1. Usable inside the if branch and after the && operator

~~~java
if (value instanceof String text && !text.isBlank()) {
    // Place a breakpoint on this line: text is already bound.
    System.out.println(text.trim());
}
~~~

If the debugger pauses at the `System.out.println` line, you can inspect **text** in the local variables list and evaluate **text.length()**. If `value` is not a String or is a blank string, the line inside the branch is not executed; there is no reason to expect that breakpoint to trigger.

**&&** is a short-circuit operator: the right-hand side is evaluated only when the left-hand side is true. Therefore, `text` is available in `!text.isBlank()`.

Conversely, the following snippet is invalid:

~~~java
// Does not compile: the right-hand side of || can run when the pattern does not match.
if (value instanceof String text || text.isBlank()) {
    System.out.println("invalid");
}
~~~

A debugger cannot "inspect a pattern variable anywhere" if the language itself does not allow using that variable at that location.

### 2.2. Not automatically in scope after if

~~~java
if (value instanceof String text) {
    System.out.println(text);
}
// Does not compile: text is not in scope here.
System.out.println(text);
~~~

However, when the non-matching path **completes abruptly** (for example, return or throw), flow scoping can allow using the variable after the if:

~~~java
static int lengthOrReject(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("expected String");
    }
    return text.length(); // text is guaranteed to be bound.
}
~~~

**Breakpoint placement must correspond to the actual control flow**, not merely to proximity to the condition in the source. Two ways of writing an if statement may look very similar yet produce different scopes.

## 3. Preparing a program for inspection with a debugger

### 3.1. Compiling with debug information for local variables

For a Java file named **PatternVariableDebugDemo.java**:

~~~bash
javac -g PatternVariableDebugDemo.java
java PatternVariableDebugDemo
~~~

The **-g** option tells javac to include debugging information—source, line numbers, and local variables—in the class file. This is a good choice for practicing inspecting pattern variables.

The default javac invocation usually includes source/line information, but **does not necessarily include the names and scopes of all local variables**. If you do not see variable names in the debugger, try recompiling with `-g`. You can inspect the debug metadata with:

~~~bash
javap -l -p PatternVariableDebugDemo
~~~

In the output, look for the **LocalVariableTable** section in the corresponding method. The fact that a variable is represented by the compiler in bytecode does not force every debugger/JVM to always display the variable name as written in source; it also depends on the local variable's live range, the pause location, the compiler, and the debugger's capabilities.

### 3.2. Placing breakpoints at statements that run after matching

Do not place a single breakpoint **right at the start of the method** and expect every pattern variable to already exist. At that point, the condition may not have been evaluated yet.

For an `instanceof` branch, a good position is **the first line inside the true branch** after the condition. For a switch, a good position is **the first statement inside the case body** after the pattern label and guard. When a guard is false, a breakpoint inside the body will **not hit**; check the fallback branch or pause before the switch and step through.

### 3.3. Selecting the right stack frame

In an IDE or `jdb`, the **Locals** list is tied to the *currently selected stack frame*. If the debugger is paused inside `String.trim()` or another helper, it does not have the same local variables as the method containing the pattern. Switch back to the frame handling the pattern and inspect the values there.

## 4. Complete Java 21 program for practice

The example includes three message types. Locations marked with a **BREAKPOINT** comment are convenient places to inspect variables after a pattern has matched.

Save everything into **PatternVariableDebugDemo.java**:

~~~java
public class PatternVariableDebugDemo {
    sealed interface Message permits Login, Transfer, Logout {}

    record Login(String username, int attempts) implements Message {}
    record Transfer(String from, String to, long amount) implements Message {}
    record Logout(String username) implements Message {}

    static String inspect(Message message) {
        if (message instanceof Login(String username, int attempts)
                && username != null && !username.isBlank()) {
            String normalized = username.trim();
            // BREAKPOINT-IF: inspect message, username, attempts, normalized.
            System.out.println("IF: username=[" + username
                    + "], attempts=" + attempts);
            return "LOGIN:" + normalized;
        }

        return switch (message) {
            case Login(var username, var attempts) ->
                    "LOGIN_REJECTED:" + attempts;

            case Transfer(String from, String to, long amount)
                    when from != null && to != null && amount > 0 -> {
                // BREAKPOINT-TRANSFER: inspect from, to, amount.
                System.out.println("CASE: from=" + from
                        + ", to=" + to + ", amount=" + amount);
                yield "TRANSFER_OK:" + amount;
            }

            case Transfer(var from, var to, var amount) ->
                    "TRANSFER_REJECTED:" + amount;

            case Logout(var username) -> {
                // BREAKPOINT-LOGOUT: inspect username.
                System.out.println("CASE: username=" + username);
                yield "LOGOUT:" + username;
            }

            case null -> "NO_MESSAGE";
        };
    }

    public static void main(String[] args) {
        Message[] samples = {
                new Login(" An ", 1),
                new Login(" ", 2),
                new Login(null, 3),
                new Transfer("A", "B", 100),
                new Transfer("A", "C", -2),
                new Transfer(null, "B", 100),
                new Logout("Binh"),
                null
        };

        for (Message message : samples) {
            System.out.println(inspect(message));
        }
    }
}
~~~

Run with JDK 21+:

~~~bash
javac -g PatternVariableDebugDemo.java
java PatternVariableDebugDemo
~~~

**Exact stdout** when running normally:

~~~text
IF: username=[ An ], attempts=1
LOGIN:An
LOGIN_REJECTED:2
LOGIN_REJECTED:3
CASE: from=A, to=B, amount=100
TRANSFER_OK:100
TRANSFER_REJECTED:-2
TRANSFER_REJECTED:100
CASE: username=Binh
LOGOUT:Binh
NO_MESSAGE
~~~

The lines marked BREAKPOINT in comments do not pause the program on their own; you need to launch the application under a debugger and set actual breakpoints on the statements immediately following the comments. Nor does every branch print variables: the **LOGIN_REJECTED** and **TRANSFER_REJECTED** values are produced directly by the switch expression.

## 5. Observing values step by step at each breakpoint

### 5.1. Breakpoint in the instanceof + record pattern branch

With **new Login(" An ", 1)**, the program matches the pattern `Login(String username, int attempts)`; the conditions that username is non-null and not blank are both true.

When paused at **BREAKPOINT-IF**, we expect:

| Variable/expression | Observed value |
| --- | --- |
| **message** | A record `Login[username= An , attempts=1]` (display depends on the debugger) |
| **username** | A string with a leading and trailing space: `" An "` |
| **attempts** | `1` |
| **normalized** | `"An"` |
| **username.equals(normalized)** | `false` |

Do not mistake the **username** variable for the trimmed value; **normalized** is the variable created from the trim result. If you want to observe the variable before and after the assignment, set two breakpoints: on the **normalized** assignment line and on the println line after the assignment. Before the assignment statement executes, the normalized variable does not yet have an assigned value; the debugger may not show it as an available variable or may display a value that is not yet meaningful to read.

With **Login(" ", 2)** or **Login(null, 3)**, the if condition is not satisfied, so execution does not pause at BREAKPOINT-IF. Move the breakpoint to the **case Login(var username, var attempts)** branch of the switch to inspect the username and attempts of the rejected value.

### 5.2. Breakpoint in a switch case with when

With **new Transfer("A", "B", 100)**, the record pattern binds three variables **from, to, amount**. The guard **from != null && to != null && amount > 0** is true, so the case body runs.

At **BREAKPOINT-TRANSFER**, expected values:

| Variable | Value |
| --- | --- |
| **message** | Record `Transfer[from=A, to=B, amount=100]` |
| **from** | `"A"` |
| **to** | `"B"` |
| **amount** | `100L` (type `long`) |

You can add a watch for **amount > 0**; here the result is true. A breakpoint inside the case body proves the guard passed, but **does not by itself show all prior case attempts**. If you need to understand why a case was not selected, set a breakpoint before the switch and use Step Over/Step Into as appropriate, or inspect the fallback branch.

With **Transfer("A", "C", -2)**, the guard is false because amount is negative; the program enters the unguarded Transfer case and returns **TRANSFER_REJECTED:-2**. With **Transfer(null, "B", 100)**, the guard is false because from is null; the result is **TRANSFER_REJECTED:100**. In both cases, BREAKPOINT-TRANSFER does not trigger.

### 5.3. Breakpoint in the Logout branch

With **Logout("Binh")**, the Logout case matches and this case's own **username** variable holds the value **"Binh"**. Even though it shares the same name as username in the Login branch, they are **different pattern variables in different scopes**. Do not infer the value or lifetime of a variable from another case.

### 5.4. The null case

With **message == null**, the switch selects **case null -> "NO_MESSAGE"**. None of the pattern variables **username**, **from**, or **amount** are bound. Watching those names is meaningless in the null branch; read **message** directly to confirm the selector is null.

## 6. How to operate in an IDE and jdb

### 6.1. IDE: IntelliJ IDEA, Eclipse, or VS Code with Java Debugger

IDEs have slightly different command names and UIs, but the general workflow is:

1. Compile with a **Debug** configuration or use `javac -g`; open the exact source file matching the class being run.
2. Set breakpoints on the statements in the **IF**, **TRANSFER**, or **LOGOUT** branches that have BREAKPOINT comments.
3. Run the application in **Debug** mode instead of just Run.
4. When the debugger pauses, select the stack frame of **PatternVariableDebugDemo.inspect**.
5. Inspect **Variables/Locals**, expand the **message** object, and directly read the pattern variables currently in scope.
6. Use **Evaluate Expression** or **Watch** for small expressions, such as `username.length()`, `amount > 0`, or `message.getClass().getSimpleName()` when the corresponding variable and receiver are non-null.
7. Use **Step Over** to observe the transition from a condition into a case body or from an assignment to the next line; use **Resume** to advance to the next input.

Expressions evaluated in the debugger can actually invoke methods. Do not call methods with **side effects**, mutate objects, or trigger transactions just to inspect a value. For a null object, an expression like `message.getClass()` will throw a NullPointerException; in the null case, simply read message.

### 6.2. Command line: using jdb

After compiling with debug symbols:

~~~bash
javac -g PatternVariableDebugDemo.java
jdb -classpath . PatternVariableDebugDemo
~~~

In the `jdb` prompt, you can start with these commands:

~~~text
stop in PatternVariableDebugDemo.inspect
run
locals
next
locals
print message
where
~~~

The **stop in** command sets a breakpoint at the start of the inspect method; **run** starts the program, **locals** lists local variables in the current stack frame, **next** steps to the next statement, **print** evaluates an expression, and **where** displays the call stack.

At method entry, **message** may already be present, but **username**, **attempts**, **from**, or **to** are not yet in scope. Continue using **next** until reaching a statement that actually executes inside a matched branch, then try:

~~~text
locals
print username
print attempts
cont
~~~

The **print username** command is only meaningful when the debugger is paused inside a branch that has the corresponding username variable. If the debugger reports that the variable cannot be found, check the **pause location, frame, debug symbols, and execution path** before concluding that the program failed to bind the pattern. For the Transfer branch, try **print from**, **print to**, and **print amount** once paused inside that branch's body.

You can also set a **source-line breakpoint** using `stop at ClassName:lineNumber` with the actual line number in the compiled file. Line numbers are not hardcoded in this guide because they can shift when copying code, adding a package, or editing the file.

### 6.3. When the IDE shows values different from stdout

Check the following in order:

- Are you running the exact build compiled from the current source?
- Are there multiple calls to inspect with different inputs, and which invocation is the breakpoint paused on?
- Is the variable you are looking at the original **username** or **normalized**?
- Does the selected stack frame belong to inspect or to another method?
- Is the breakpoint placed before or after the assignment statement?
- Is the local variable still in scope in the bytecode/debug metadata?

If you need to quickly verify an execution path, a temporary log in the relevant branch or a test assertion can complement the debugger, though adding logs everywhere should not become your primary method.

## 7. Null and record patterns: a common point of confusion when reading variables

You need to separate two different situations:

**A. Null selector in instanceof**

~~~java
Object missing = null;
System.out.println(missing instanceof String s); // false
~~~

There is no String object to bind to the variable s, so the result is false.

**B. A record component is null**

~~~java
record Wrapper(String value) {}

System.out.println(
        new Wrapper(null) instanceof Wrapper(String inner)); // true
System.out.println(
        new Wrapper(null) instanceof Wrapper(var inner));    // true
~~~

This is an important behavior of **unconditional component patterns**: when the static type of the component is already String, the component pattern `String inner` can even bind a null value of that component. Do not assume every nested type pattern matches null: whether it matches depends on the **static type of the component** and whether the pattern is unconditional for that type.

Therefore, in the main example, the condition `message instanceof Login(String username, int attempts)` **can match Login(null, 3)**, and the username variable can hold null. To avoid a NullPointerException, the code deliberately writes:

~~~java
if (message instanceof Login(String username, int attempts)
        && username != null && !username.isBlank()) {
    // At this point, username is guaranteed to be non-null.
}
~~~

If you omit **username != null**, calling **username.isBlank()** can throw a NullPointerException **right inside the if condition**, before entering the if body. A breakpoint placed only inside the if body will not catch that error path; you need to enable an exception breakpoint or pause before the condition.

Similarly, in the switch, Transfer's guard checks **from != null && to != null** before checking amount > 0. When a component is null, the guarded case is not selected, but the case **Transfer(var from, var to, var amount)** can still match.

**Special note:** a **nested record pattern** requires deconstructing a child record, such as `Box(Point(var x, var y))`. If the Point component is actually null, the nested pattern Point(...) does not match. That is not the same situation as binding a reference component with an unconditional pattern.

## 8. Distinguishing "variable not visible" from "value did not match"

When a breakpoint does not trigger or the debugger cannot read a variable name, form the right hypothesis:

| Symptom | Common cause | How to check |
| --- | --- | --- |
| Breakpoint in if does not run | Pattern did not match or && condition was false | Pause before the if, inspect message and each side of the condition |
| Breakpoint in switch case with when does not run | Pattern did not match or guard was false | Pause before the switch, follow execution to the fallback case |
| Watch reports variable not found | Outside flow scope or wrong stack frame | Pause inside the right case body and select the inspect frame |
| Variable appears but is null | Record component can be null | Check the constructor, components, and guard |
| Only message is visible, component variables are not | Paused before matching or missing local-variable metadata | Step into the post-match branch and compile with -g |
| username is visible but value is unexpected | Paused on a different sample or a different scope with the same name | Check the current message and call stack |
| Stale data shown despite editing source | Old class files are still being executed | Clean/rebuild and check the run configuration |
| Exception occurs before case body | Guard, selector, accessor, or condition threw an error | Enable exception breakpoints, inspect the call stack |

When a record pattern is tested, Java may invoke an accessor to retrieve a component. If an application-overridden accessor throws an error, matching can complete abruptly (in the corresponding case, represented by a **MatchException** with a cause). In that case, a breakpoint inside the body is never executed. You need to pause at the exception site or at the accessor call, rather than looking for a pattern variable that has not yet been completely bound.

## 9. Rules for Evaluate Expression and setting Watches

- **Only inspect variables currently in scope.** A persistent watch on `username` may be valid in the Login or Logout case, but meaningless in the Transfer case.
- **Check static type and runtime value:** `var amount` in the Transfer record pattern binds a `long` value; the value in the debugger may be displayed as 100 or 100L depending on the tool.
- **Avoid mutating program state while inspecting.** Evaluate Expression calling a method can run real logic, including throwing errors or changing state.
- **Do not call methods on a null variable.** When `username` can be null, evaluating `username.length()` before checking for null will cause a new error from the debugger itself.
- **Pay attention to guard conditions:** pausing inside the body only proves the guard was true on that invocation; to investigate a false guard, use a dedicated test input and a breakpoint before the branch.
- **Do not rely on bytecode variable names when debug info is missing.** The compiler may reuse slots for different locals; source names and scopes must be mapped through the appropriate metadata.
- **Check the timing of assignments:** a local variable declared before an assignment statement does not necessarily have a meaningful value at a pause point before the assignment has executed.
- **With lambdas or streams:** a pattern variable declared inside one lambda does not carry over to the next lambda; when paused in the debugger, select the frame and scope of the exact lambda currently being invoked.

## 10. Quick debugging tips for each pattern form

### 10.1. Type pattern instanceof

~~~java
if (value instanceof String text) {
    // Breakpoint here, read text.
    System.out.println(text);
}
~~~

If value is null, execution does not enter the branch. If value is not a String, there is no text variable. If value is a String, text references that same String object.

### 10.2. Record pattern

~~~java
if (value instanceof Point(int x, int y)) {
    // Breakpoint after matching, read x and y.
    System.out.println(x + y);
}
~~~

Set a breakpoint inside the branch to inspect the components; there is no need to cast to Point and call x()/y() just to view the data. The debugger can let you expand both value and the variables x, y to cross-check.

### 10.3. Switch pattern with guard

~~~java
return switch (message) {
    case Transfer(var from, var to, long amount)
            when amount > 0 -> {
        // Breakpoint at the following println.
        System.out.println(amount);
        yield "positive";
    }
    case Transfer(var from, var to, var amount) -> "other";
    case Login(var user, var attempts) -> "login";
    case Logout(var user) -> "logout";
    case null -> "null";
};
~~~

This is an **illustrative snippet** using the records from the main program. When amount is negative or zero, the first guarded branch does not run; the amount variable in the fallback branch is **a separate binding**. Do not confuse two variables with the same name with a single variable spanning multiple cases.

### 10.4. Nested patterns

Suppose we have `record Shipment(Point destination)`. With:

~~~java
// Illustration: Shipment and Point are declared appropriately.
if (value instanceof Shipment(Point(int x, int y))) {
    System.out.println(x + "," + y);
}
~~~

Set a breakpoint at println, read x/y, and also expand the value object to inspect Shipment.destination. If destination is null, the nested pattern Point(...) does not match and the breakpoint does not run. To distinguish "wrong type" from "null component", set a breakpoint before the condition or inspect the record object in the fallback branch.

## 11. Repeatable debugging workflow

Follow this order instead of setting watches randomly:

1. **Prepare concrete inputs:** for example Login(" An ", 1), Login(null, 3), Transfer("A", "B", 100), and Transfer("A", "C", -2).
2. **Compile with debug symbols:** `javac -g`; verify that you are running the matching class/source.
3. **Set breakpoints where variables are used:** after an instanceof condition, on the first line of a case body, or after the normalized variable assignment.
4. **Check the stack frame and selector:** inspect message first to know exactly which invocation is currently being processed.
5. **Read pattern variables:** observe username/attempts or from/to/amount; distinguish bound variables from variables computed afterward.
6. **Compare non-matching branches:** use Step and inspect the fallback branch, especially when a guard is false or a component is null.
7. **Enable exception breakpoints if needed:** errors in a condition, accessor, or guard can happen before the body.
8. **Cross-check with tests/stdout:** the debugger shows step-by-step state; assertions protect behavior during refactoring.
9. **Remove breakpoints and evaluation expressions with side effects** before ending the debugging session.

### Self-check checklist

- [ ] I know which locations in the source are actually **after the pattern matches**.
- [ ] I understand why a pattern variable is in or out of scope.
- [ ] I have selected the stack frame containing the variable I want to inspect.
- [ ] I compiled with debug information for local variables.
- [ ] I do not confuse a false guard branch with an exception thrown inside the guard.
- [ ] I checked a null selector and a null record component separately.
- [ ] I do not infer the value of a similarly named variable from another case.
- [ ] I do not run evaluations in the debugger that could alter application behavior.

**Conclusion:** To read pattern variables while debugging, pause the program **after matching succeeds and within the proper flow scope**. Use `javac -g`, select the right frame, and inspect both the selector object and the bound variables. For record patterns, pay special attention to potentially null components; for switch, pay attention to guards and fallback cases. Once you understand those boundaries, debugging pattern matching becomes following predictable execution flow rather than searching for a variable that seems to have "disappeared."