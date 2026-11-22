# Control-Flow Analysis and Validity Conditions During Java Compilation

## 1. Objectives

When checking a Java program, the compiler does not merely verify whether syntax and data types are valid. It also analyzes **the possible execution paths through the program** to catch several bugs before running: unreachable statements, local variables that might be read before assignment, final variables that might be reassigned, methods that can finish without returning a value, or unhandled checked exceptions.

This is the **flow analysis** part in the picture of compilation phases. After this lesson, you can:

- Understand how if/else statements, switch, loops, return, break, continue, and try/catch create control branches.
- Distinguish **reachability** (whether a statement is considered reachable) and **definite assignment** (a variable is definitely assigned at a given point).
- Understand assignment constraints on final variables, method return requirements, and checked exception checking.
- Read, predict, and fix javac errors by analyzing all relevant branches.
- Recognize the compiler's limits: it does not prove all runtime conditions, does not execute the program to decide, and does not eliminate all runtime errors.

This lesson uses **Java 17** syntax. Code snippets explicitly note whether they are complete programs or intentional error-triggering examples.

## 2. What Is Control Flow?

**Control flow** is the order and directions in which execution can move through statements. With sequential code, the program runs top to bottom. With if, it branches; with for/while, it can loop back; with return/throw, the current flow terminates; with break/continue, it jumps to a location determined by the enclosing construct.

Consider a small example:

~~~java
static String label(int points) {
    if (points >= 60) {
        return "pass";
    }
    return "retry";
}
~~~

One way to visualize the flow diagram:

~~~text
              Start
                |
          points >= 60?
            /       \
          true      false
           |          |
     return "pass"  return "retry"
            \        /
           end of call
~~~

The two return statements sit on two different branches. Regardless of which branch is taken, calling label returns a String. The compiler checks Java's requirements based on the control structure like this, rather than trying to call the method with every value of points.

In a compiler implementation, analysis can be based on the syntax tree, branch state, and/or an intermediate flow representation. We use a **control-flow graph (CFG)** to learn how to reason, without claiming javac is required to build the exact illustrative diagram above.

### Basic Blocks, Branches, and Merge Points

In a conceptual CFG, a **node** represents a statement or block; an **edge** represents a possible transfer of control. Where two branches meet again is a **merge point**. Information the compiler knows at a merge point generally must hold across **all paths reaching that point**.

For instance:

~~~java
int result;
if (valid) {
    result = 10;
} else {
    result = 0;
}
System.out.println(result);
~~~

Both the true and false paths assign result. Thus the print statement can safely use result under definite assignment rules.

Conversely:

~~~java
int result;
if (valid) {
    result = 10;
}
System.out.println(result); // COMPILE ERROR
~~~

If valid is false, there is no assignment to result before printing. javac reports an error like **variable result might not have been initialized**, even if on a particular run you happen to know valid is always true.

> **Core point:** checking “definiteness” at compile time is conservative. One valid path where a variable is unassigned is enough to reject reading that variable.

## 3. Reachability: Can a Statement Be Reached?

**Reachability** is the language rule set determining whether a statement is considered executable according to control structure. Java forbids certain **unreachable** statements because they follow a statement that always terminates or transfers flow.

Intentional error example, not a runnable program:

~~~java
static void stop() {
    return;
    // System.out.println("never"); // If // is removed: unreachable statement
}
~~~

When uncommenting the print statement, javac reports **unreachable statement**. After return there is no normal control path to execute that statement.

Similarly:

~~~java
static int answer() {
    throw new IllegalStateException("stop");
    // return 42; // If // is removed: unreachable statement
}
~~~

throw transfers control abnormally; the return statement immediately following is unreachable.

### Loops and Exit Capability

Error-inducing snippet:

~~~java
static void spin() {
    while (true) {
        System.out.println("tick");
    }
    // System.out.println("done"); // If // is removed: unreachable statement
}
~~~

A while loop with a constant true condition expression and no reachable break to exit renders the subsequent statement not reachable. Do not run spin: it prints forever until the program is terminated or hits a resource failure.

Yet if a reachable break exists:

~~~java
static void spinUntil(boolean stop) {
    while (true) {
        if (stop) {
            break;
        }
    }
    System.out.println("done");
}
~~~

The print statement is considered reachable thanks to the exit path via break. If stop is never true in a particular run, the call may loop infinitely; the compiler does not prove termination from runtime data.

### An Important Exception: if(false) and while(false)

Do not automatically infer that every block inside a constant false condition is rejected by javac.

~~~java
static void example() {
    if (false) {
        System.out.println("disabled"); // Valid per if reachability rules
    }
}
~~~

Java has a special reachability rule for **if**, so the snippet above is allowed to compile; this is useful for conditionally enabling/disabling code blocks at compile time. Conversely:

~~~java
static void example() {
    while (false) {
        System.out.println("never"); // ERROR: unreachable statement
    }
}
~~~

In Java 17, the body of while(false) is treated as unreachable. This is why you should learn **Java's reachability rules** rather than relying solely on intuition about “definitely runs or not”. Detailed rules are specified in the JLS, section *Unreachable Statements*.

## 4. Definite Assignment: Variables Must Definitely Be Assigned Before Reading

**Definite assignment (DA)** concerns whether a variable has been assigned **on all relevant control paths** before its value is used. Common subjects are local variables and blank finals; for fields, initialization rules and default values have additional differences.

### Valid Example: Assigned in Both Branches

~~~java
static int fee(boolean member) {
    int value;
    if (member) {
        value = 5;
    } else {
        value = 10;
    }
    return value;
}
~~~

If member is true then value equals 5; if false then 10. Because every path reaching return assigns value, javac accepts it.

### Invalid Example: Missing else and Reading the Variable

~~~java
static int fee(boolean member) {
    int value;
    if (member) {
        value = 5;
    }
    return value; // ERROR: variable value might not have been initialized
}
~~~

On the member=false path, variable value has not been assigned before return. There are two common fixes:

~~~java
// Approach A: assign initially.
int value = 10;
if (member) {
    value = 5;
}
return value;
~~~

~~~java
// Approach B: have an else branch.
int value;
if (member) {
    value = 5;
} else {
    value = 10;
}
return value;
~~~

These snippets illustrate **method bodies**, not standalone programs to run with java. If you want to run them, place them inside a method with an int return type and an appropriate member parameter.

### Why Does the Compiler Use an “All Branches” Merge?

Consider the variable state after if/else:

| Path | State after branch |
| --- | --- |
| member=true | value has been assigned |
| member=false | value has been assigned |
| Rejoin after if/else | value is definitely assigned |

If else is omitted, the false path retains the “unassigned” state, so at the merge point DA cannot be concluded.

Conceptually, “definitely assigned” information is obtained via the **intersection** of possible states, not “at least one branch assigned it”. Java's actual rules are even finer-grained due to break, continue, &&, ||, conditional operators, switch, try/finally, and abrupt completion forms.

## 5. Blank Final and Definite Unassignment

A local variable declared final without an initial value is called a **blank final**. It must be assigned before reading, and every assignment must satisfy **definite unassignment (DU)**: at the assignment point, the compiler can prove the variable has not been assigned on any relevant path.

Valid:

~~~java
static int choose(boolean enabled) {
    final int timeout;
    if (enabled) {
        timeout = 30;
    } else {
        timeout = 5;
    }
    return timeout;
}
~~~

Each path assigns timeout exactly once before return.

Invalid:

~~~java
static int choose(boolean enabled) {
    final int timeout;
    if (enabled) {
        timeout = 30;
    }
    timeout = 5; // ERROR: timeout may already have been assigned
    return timeout;
}
~~~

If enabled=true, timeout gets assigned 30 and then assigned 5 again. Even though the enabled=false path assigns only once, the compiler cannot prove the second assignment is always valid for a blank final.

Fix: add an else branch, or pick the value directly in a single expression:

~~~java
final int timeout = enabled ? 30 : 5;
~~~

**Do not confuse with field default values.** An uninitialized int local variable does not automatically receive 0 so it can be validly read. An instance field of type int without an initializer, by contrast, is default-initialized to 0 by Java. For blank final fields, there are additional rules on completing initialization in constructors/static initializers. This lesson focuses on method flow analysis.

## 6. Short-Circuiting Creates Additional Control Paths

The **&&** and **||** operators use short-circuit evaluation:

- For a && b, if a=false then b is not evaluated.
- For a || b, if a=true then b is not evaluated.

Therefore, an assignment inside the second operand has not necessarily occurred after the full expression.

Error-inducing example:

~~~java
static void check(boolean enabled) {
    int number;
    boolean ok = enabled && ((number = 7) > 0);
    System.out.println(number); // ERROR: number might not have been initialized
}
~~~

If enabled=false, the ((number = 7) > 0) part is skipped. Yet inside the **true branch of if** below, the assignment has definitely occurred:

~~~java
static void check(boolean enabled) {
    int number;
    if (enabled && ((number = 7) > 0)) {
        System.out.println(number); // VALID: true branch requires right side to have run
    }
}
~~~

One technique for reading errors is drawing true/false edges for each part of a condition, including sides that can be skipped due to short-circuiting. Java does not require every condition to be a literal true/false; it only requires the condition expression of if/while/for to have type boolean or Boolean convertible by unboxing accordingly.

**Be careful:** if you write if (flag = true) instead of if (flag == true), the assignment expression still has boolean type so it **can compile successfully** while mutating data. Flow analysis is not a tool for catching every logic bug.

## 7. Return Paths: Every Normal Completion Path of a Value-Returning Method Must Be Handled

A method declaring a non-void return type must guarantee the method body cannot **complete normally without a return value**. This is a compile-time control-check requirement.

Wrong:

~~~java
static String status(int score) {
    if (score >= 50) {
        return "pass";
    }
    // ERROR: missing return statement
}
~~~

The score<50 path reaches the end of the method without returning a String.

Corrected by supplying the missing path:

~~~java
static String status(int score) {
    if (score >= 50) {
        return "pass";
    }
    return "retry";
}
~~~

A method can also transfer flow via throw on a branch:

~~~java
static int requirePositive(int number) {
    if (number <= 0) {
        throw new IllegalArgumentException("must be positive");
    }
    return number;
}
~~~

This is valid because the error branch does not complete normally. The compiler does not need to prove number is always positive; it only checks control paths and corresponding return types.

**Distinction:** a void method can end without a return. In a lambda with a value-returning block body, return paths must satisfy requirements matching the target functional interface.

## 8. Loops, break, continue, and Exit Paths

Loops introduce at least two edge kinds: an edge looping back to the condition/loop head and an edge exiting the loop. With for-each, the loop can run **0 times** when the collection/array is empty.

Invalid example:

~~~java
static int first(int[] values) {
    int value;
    for (int x : values) {
        value = x;
        break;
    }
    return value; // ERROR: array may be empty
}
~~~

Do not assume that having a break guarantees the assignment inside the loop ran. If values has length 0, zero iterations occur.

Fix with a meaningful fallback path:

~~~java
static int firstOrMinusOne(int[] values) {
    for (int x : values) {
        return x;
    }
    return -1;
}
~~~

For empty values, the result is -1. For non-empty values, the first element is returned. Both paths are valid.

**continue** jumps control to the next iteration step (or the update step of a for loop), so statements after continue in the same block do not execute on that branch. **break** exits an enclosing permitted construct; it is not synonymous with returning from the method. Java requires break/continue to be used where a valid target exists; you cannot place break outside a loop/switch and expect the compiler to guess intent.

### Tricky Example: One Branch Continues, the Other Assigns

~~~java
static int sumNonNegative(int[] values) {
    int sum = 0;
    for (int value : values) {
        if (value < 0) {
            continue;
        }
        sum += value;
    }
    return sum;
}
~~~

sum is assigned 0 before the loop. Every path that can reach return holds a valid value for sum, even if the array is empty or every element is negative. continue merely skips the addition on the current iteration.

## 9. Switch and Branch Coverage Requirements

Switch creates multiple edges according to the examined value. With a traditional **switch statement**, cases can fall through without break; with a **switch expression** (Java 17), the switch must have a way to produce a value for every valid case.

Valid switch expression example with int:

~~~java
static String category(int code) {
    return switch (code) {
        case 1, 2 -> "small";
        case 3 -> "medium";
        default -> "other";
    };
}
~~~

Here default handles int values outside the listed cases. Every branch provides a String, so the switch expression has type String.

Invalid example due to missing coverage:

~~~java
static String category(int code) {
    return switch (code) {
        case 1 -> "one";
        case 2 -> "two";
    }; // ERROR: switch expression is not exhaustive for int
}
~~~

You can add default or exhaustively cover the value domain under the applicable Java rules. With enums, listing all enum constants can suffice for a switch expression to be considered exhaustive in many cases; enum evolution across library versions can still introduce runtime behavior worth noting. In this lesson we use default with int for easy testing.

With a **switch statement** using traditional colons `:`, remember break if you do not want execution to fall through into the next case. Reachability, definite assignment, and normal completion constraints are evaluated depending on the switch form. Do not apply switch expression rules to every switch statement.

## 10. Checked Exceptions Are Part of Control-Path Analysis

Java distinguishes **checked** exceptions (briefly: Exception subclasses excluding RuntimeException and its subclasses) from **unchecked** ones (RuntimeException and Error along with their subclasses). When an operation can throw a checked exception, the compiler requires the method to **catch** it or **declare throws** accordingly.

Invalid example if placed inside a class importing java.io.BufferedReader:

~~~java
static String load(java.io.BufferedReader reader) {
    return reader.readLine(); // ERROR: unreported exception IOException
}
~~~

BufferedReader.readLine() declares it may throw IOException. You can declare:

~~~java
static String load(java.io.BufferedReader reader)
        throws java.io.IOException {
    return reader.readLine();
}
~~~

Or handle the exception at the call site:

~~~java
static String load(java.io.BufferedReader reader) {
    try {
        return reader.readLine();
    } catch (java.io.IOException e) {
        return "read failed";
    }
}
~~~

In the catching case, you are choosing an application policy: converting a read failure into a fallback String. In real applications, do not swallow errors indiscriminately; logging or propagating the error to the right handling layer may be more appropriate.

**try/finally** adds normal or abrupt completion paths: finally runs when leaving try under normal cases, including return or exception, except abrupt runtime termination situations. A finally clause that throws/returns itself can override the prior flow's result; avoid return inside finally because it easily masks exceptions or return values.

The compiler checks checked exceptions per language rules, yet does not guarantee a call will not throw an unchecked exception at runtime. For instance, indexing an array out of bounds or dereferencing null can throw runtime errors even though the code compiles.

## 11. A Complete Java 17 Project to Observe Every Mechanism

Create the project:

~~~text
flow-lab/
├── src/
│   └── demo/
│       └── flow/
│           └── FlowDemo.java
└── out/
~~~

File **src/demo/flow/FlowDemo.java**:

~~~java
package demo.flow;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public final class FlowDemo {
    private FlowDemo() {
    }

    static String grade(int score) {
        if (score >= 80) {
            return "A";
        }
        if (score >= 60) {
            return "B";
        }
        return "C";
    }

    static int firstEvenOrMinusOne(int[] values) {
        for (int value : values) {
            if (value % 2 == 0) {
                return value;
            }
        }
        return -1;
    }

    static String readFirstLine(String input) throws IOException {
        try (BufferedReader reader =
                     new BufferedReader(new StringReader(input))) {
            return reader.readLine();
        }
    }

    public static void main(String[] args) throws IOException {
        final int result;
        boolean passed = true;

        if (passed) {
            result = 10;
        } else {
            result = 0;
        }

        System.out.println("Grade: " + grade(75));
        System.out.println("Even: "
                + firstEvenOrMinusOne(new int[] {3, 7, 8, 10}));
        System.out.println("Result: " + result);
        System.out.println("Line: " + readFirstLine("hello\nworld"));
    }
}
~~~

This is **a complete program** with consistent file/class/package names. Using a terminal in the **flow-lab** directory, create out:

~~~bash
# Bash on macOS/Linux
mkdir -p out
~~~

~~~powershell
# PowerShell on Windows
New-Item -ItemType Directory -Path out -Force | Out-Null
~~~

Compile:

~~~sh
javac -encoding UTF-8 --release 17 -d out src/demo/flow/FlowDemo.java
~~~

Run:

~~~sh
java -cp out demo.flow.FlowDemo
~~~

**Exact stdout:**

~~~text
Grade: B
Even: 8
Result: 10
Line: hello
~~~

Explanation of each part:

- grade(75): the score >= 80 branch is not taken; the score >= 60 branch returns "B"; if both branches are false, return "C" still exists.
- firstEvenOrMinusOne: the loop skips 3 and 7, returning 8; if there is no even number or the array is empty, it still returns -1.
- final int result: both passed=true and false branches assign exactly once; at the print statement, result is definitely assigned.
- readFirstLine: readLine can throw IOException, so the method declares throws IOException. main also declares throws IOException because the call is not caught. try-with-resources ensures the resource closes per Java rules.
- The data "hello\nworld" contains a newline; BufferedReader.readLine returns "hello" without the line terminator.

The program uses Java 17 JDK APIs and has no external library dependencies. If you edit code without recompiling, the JVM may run stale bytecode in out; compile successfully before concluding the result.

## 12. Hands-on Practice Fixing Each Error Category

The examples below **intentionally fail to compile** if you enable the commented line. Experiment in a separate copy, keeping the working FlowDemo.java intact for easy restoration.

### Exercise A — Unreachable statement

Add a method:

~~~java
static int fixed() {
    return 1;
    // System.out.println("after return"); // Remove // to trigger error
}
~~~

Remove // and run javac. Expect an error like **unreachable statement** at the print statement. Fix by removing the unreachable statement or moving it before return if appropriate to the logic.

### Exercise B — Definite assignment

Add the method:

~~~java
static int charge(boolean active) {
    int amount;
    if (active) {
        amount = 50;
    }
    return amount; // COMPILE ERROR
}
~~~

Expect an error like **variable amount might not have been initialized**. Draw the two true/false branches: only the true branch assigns. Add an else assigning a value or declare int amount = 0; before if.

### Exercise C — Blank final reassigned

~~~java
static int limit(boolean fast) {
    final int max;
    if (fast) {
        max = 20;
    }
    max = 10; // ERROR: might already have been assigned
    return max;
}
~~~

Fix with else, or assign once via an appropriate ? : operator.

### Exercise D — Missing return

~~~java
static String direction(int x) {
    if (x > 0) {
        return "positive";
    }
    // ERROR: path x <= 0 reaches the end of the method
}
~~~

Expect an error like **missing return statement**. Add return "non-positive"; after if or use if/else with return in both branches.

### Exercise E — Unreported checked exception

~~~java
static String line(BufferedReader reader) {
    return reader.readLine(); // ERROR: IOException
}
~~~

Fix by adding throws IOException to the declaration, or catching IOException with an appropriate handling policy. Also check call sites after adding throws.

### Exercise F — Loop not guaranteed to have elements

~~~java
static int last(int[] values) {
    int value;
    for (int number : values) {
        value = number;
    }
    return value; // ERROR: array may be empty
}
~~~

Fix with an intentional default value, checking the empty condition and throwing appropriately, or changing the method contract to reflect missing data.

**Testing rule:** read full javac diagnostics and fix the cause of each error; exact position, caret ^, and wording may vary across JDK versions.

## 13. Common Thinking Pitfalls

| Misconception | Reality |
| --- | --- |
| “One branch assigning is enough.” | Reading a local variable requires definite assignment on all paths that can reach the read. |
| “An int local variable defaults to 0.” | An unassigned local cannot automatically be read with a default value; fields follow different rules. |
| “final is only for compile-time constants.” | final also applies to variables receiving runtime values, provided assignment rules are met. |
| “if(false) must report unreachable.” | Reachability has a special rule for if; in while(false) the loop body is rejected. |
| “A return inside if is enough.” | If a path goes past if without returning, a value-returning method can still miss a return. |
| “break and return are the same.” | break exits the target loop/switch; return ends the method invocation. |
| “Loops run at least once.” | for/while/for-each can execute 0 times depending on condition/data. |
| “The compiler already checked null and index bounds completely.” | Code can compile yet still hit NullPointerException or ArrayIndexOutOfBoundsException at runtime. |
| “Every exception must be caught/declared with throws.” | Checked exceptions obey checking rules; unchecked exceptions do not require declaring/catching. |
| “The compiler knows a boolean variable is always true in practice.” | Analysis uses language rules and information provable at compile time, rather than running all inputs. |

## 14. Boundary Between Flow Analysis and Other Compiler Steps

| Check kind | Example question | Common error/symptom |
| --- | --- | --- |
| Syntax analysis | Balanced parentheses and semicolons? | ';' expected, illegal start of expression |
| Name and type resolution | Does the method exist? Called with compatible types? | cannot find symbol, incompatible types |
| Reachability | Is any statement completely blocked by structural rules? | unreachable statement |
| Definite assignment | Definitely assigned before reading? | variable ... might not have been initialized |
| Definite unassignment | Risk of reassigning a blank final? | variable ... might already have been assigned |
| Return checking | Can the method complete normally without a value? | missing return statement |
| Exception checking | Checked exception caught/declared with throws appropriately? | unreported exception ... must be caught or declared to be thrown |
| Runtime | Are actual data and runtime state valid? | NullPointerException, ArithmeticException, I/O errors... |

A single Java error sometimes involves multiple rules at once. The diagnostic location chosen by the compiler does not mean internal phases operate as completely isolated machines or execute in a strict fixed order. This is a classification for reasoning about and fixing errors.

### Limits of Static Analysis

Flow analysis is not a guarantee that a program is completely safe or will terminate:

- A loop with a permitted break can still run infinitely on specific data.
- A definitely assigned variable can still hold a value causing a logic error.
- The compiler does not automatically guarantee objects are non-null, arrays stay in bounds, or network requests succeed.
- Properly declaring or catching a checked exception does not mean I/O operations always succeed.
- Runtime bugs can exist due to dependencies, class loading, resources, concurrency, or real-world data.

Combine compilation checks with unit tests, integration tests, and appropriate data contract validation.

## 15. Workflow for Analyzing a Flow-Related Diagnostic

When javac reports an error, you can follow these steps:

1. **Pinpoint the reported error site:** which statement is unreachable, which variable is being read, which return path is missing, which exception is unhandled?
2. **Draw minimal branches:** from the start of the method to the error point; mark if true/false branches, loop iteration count possibly equal to 0, break/continue, return/throw, and try/catch/finally if present.
3. **Annotate state onto each branch:** variable unassigned/assigned; blank final assigned or not; whether the path can continue normally; whether an exception can escape.
4. **Merge information:** for definite assignment, it must hold on **all paths reaching the read point**; for missing return, check whether any path completes normally.
5. **Fix according to the real contract:** add else/default, sensible initial values, appropriate return/throw, or checked exception handling; avoid adding code just to silence the compiler in ways that break business logic.
6. **Recompile and run tests:** verify both language rules and desired behavior.

For example, if javac reports amount might not have been initialized, do not fix it by arbitrarily setting amount = 0 if business logic actually requires rejecting missing values. In that case, a throw branch can express intent far more clearly.

## 16. Knowledge Self-Check

Answer yourself before running the compiler:

1. Does the snippet int x; if(flag) x=1; System.out.println(x); definitely compile? **No**, the flag=false path has not assigned x.
2. If both if and else assign x, can x be read in the statement after if/else? **Yes**, provided every branch reaching the read assigns validly.
3. With final int x; if(flag) x=1; x=2;, why is it invalid? **Because the x=2 assignment may assign a second time**.
4. After return;, can a println statement be placed directly in the same block? **No**, that statement is unreachable.
5. Why is if(false) with a body accepted while a while(false) body is rejected? **Because Java's reachability rules specify them differently**.
6. Is a method returning int with one return branch and one throw branch accepted? **Yes**, if no normal completion path lacks a value and other constraints hold.
7. Does a for-each loop guarantee its body runs at least once? **No**, the array or collection may be empty.
8. readLine() throws IOException—how do you fix it? **Catch it or declare throws** according to the chosen contract.
9. Does successful compilation guarantee no null or divide-by-zero errors at runtime? **No**.
10. Must a variable declared final always be assigned right on the declaration line? **No**; a blank final can be assigned later if it satisfies definite assignment/unassignment.

**Completion criteria:** you can explain a flow-related compiler error using concrete branches, fix it intentionally, run the FlowDemo.java project, and distinguish what the compiler proves at compile time from what still requires testing at runtime.

### Authoritative Documentation for Deeper Study

In the *Java Language Specification* (JLS), the section on **Blocks and Statements**, especially *Unreachable Statements*, describes reachability rules. The **Definite Assignment** section specifies DA/DU for variables and control constructs. The **Exceptions** section explains checked exception checking. When encountering complex cases involving switch, try/finally, or conditional operators, consult the JLS rules for **the Java version in use** instead of reasoning from an oversimplified rule of thumb.

Principle to keep throughout: **which control paths can lead to the point where data is used, and what can the compiler prove across all of those paths?** This question connects analysis phases to the ability to read Java compilation errors in real projects.