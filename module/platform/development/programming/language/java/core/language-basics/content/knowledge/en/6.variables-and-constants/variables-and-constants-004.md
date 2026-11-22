# Requiring Assignment Before Reading Local Variables in Java

## 1. Core Rule: Definite Assignment

A **local variable** declared inside a method, constructor, or block does not need an initializer on the declaration line itself:

~~~java
int quantity;             // Declaration is allowed
quantity = 4;             // Assigned before use
System.out.println(quantity); // 4
~~~

However, **Java 17 requires a local variable to be definitely assigned before its value is read**. This rule is called **definite assignment**. It is checked by the `javac` compiler by analyzing the control-flow paths that can reach the variable read.

Deliberately invalid example:

~~~java
static void invalid() {
    int quantity;
    System.out.println(quantity); // COMPILE ERROR
}
~~~

`javac` typically outputs a message like:

~~~text
error: variable quantity might not have been initialized
~~~

This is a **compile-time** error, not a runtime-only exception. The compiler will not allow using a local variable that might not have been assigned.

> **Remember:** "declared" is different from "assigned a value". It does not have to be initialized on the declaration statement, but every execution path reaching the read must guarantee the variable has been assigned.

## 2. How Do Declaration, Assignment, and Reading Differ?

~~~java
int score;              // Declared, no readable value yet
score = 80;             // First assignment
int copied = score;     // Valid read of score; copied is initialized
score = score + 5;      // Reads old score, then assigns new score
System.out.println(score); // 85
~~~

| Statement | Reads the old value of `score`? | Condition |
|---|---|---|
| `int score;` | No | Valid declaration |
| `score = 80;` | No | Valid first assignment |
| `int x = score;` | Yes | `score` must already be assigned |
| `score = score + 1;` | Yes | Evaluates RHS before reassigning |
| `score++;` | Yes | Needs current value to increment |
| `score += 1;` | Yes | Compound assignment also uses the old value |

Examples that **do not compile** even though they contain `=`:

~~~java
int count;
// count = count + 1; // Invalid: RHS reads unassigned count
// count++;           // Invalid: needs to read current count
// count += 1;        // Invalid: also needs the old value
~~~

Fix by initializing first:

~~~java
int count = 0;
count++;
System.out.println(count); // 1
~~~

## 3. The Compiler Checks Every if/else Branch Leading to a Read

**Invalid** case:

~~~java
static String invalid(boolean passed) {
    String result;
    if (passed) {
        result = "PASS";
    }
    return result; // ERROR: passed could be false
}
~~~

If `passed` is `false`, the assignment statement is not executed. Thus `return result` has a path that reads an unassigned variable.

Fix 1 — **assign on both branches**:

~~~java
static String status(boolean passed) {
    String result;
    if (passed) {
        result = "PASS";
    } else {
        result = "FAIL";
    }
    return result;
}
~~~

Fix 2 — **give a default value at declaration**:

~~~java
static String status(boolean passed) {
    String result = "FAIL";
    if (passed) {
        result = "PASS";
    }
    return result;
}
~~~

Fix 3 — **use a conditional expression** when only choosing one value:

~~~java
static String status(boolean passed) {
    return passed ? "PASS" : "FAIL";
}
~~~

All three can be valid, but choose the one that accurately reflects the requirements. **Do not assign a dummy value just to silence a compile error** if that value misleads the business logic.

## 4. Early Return Branches Can Guarantee Assignment

The compiler cares about **paths that can reach the read statement**, not necessarily that every branch assigns the same variable.

~~~java
static String sign(int number) {
    if (number < 0) {
        return "NEGATIVE";
    }

    String label;
    if (number == 0) {
        label = "ZERO";
    } else {
        label = "POSITIVE";
    }
    return label;
}
~~~

The `number < 0` branch already executes `return`, so it cannot reach `return label`. The remaining branches all assign `label`, making the code valid.

A shorter example:

~~~java
static int nonnegative(int value) {
    if (value < 0) {
        throw new IllegalArgumentException("Negative value");
    }
    int accepted = value;
    return accepted;
}
~~~

`return` or `throw` can terminate the current control-flow path. However, if a branch **only prints an error and continues**, it still must ensure the variable is assigned before being read.

## 5. Loops Might Run Zero Times

A `while` or `for` loop with a pre-check condition can execute **0 iterations**, so assigning inside the loop cannot be assumed sufficient by default.

~~~java
static void invalid(int limit) {
    int last;
    for (int i = 0; i < limit; i++) {
        last = i;
    }
    // System.out.println(last); // If uncommented: compile error
}
~~~

If `limit <= 0`, no iterations run. The right approach when reading a result after a loop is to define a meaningful initial value:

~~~java
static long sumFromOneTo(int limit) {
    long sum = 0L;
    for (long i = 1; i <= limit; i++) {
        sum += i;
    }
    return sum;
}
~~~

With `limit = 4`, the result is `10`; with `limit = 0`, the result is `0`. Using `long` for both the counter and sum avoids `int` overflow for very large `limit`; the loop still takes time proportional to `limit` and this example primarily illustrates variable assignment rules.

**Distinction:** the `int i = 1` variable in the `for` initializer is clearly assigned, so it can be read in the condition and loop body. The issue arises when you **only** assign another variable inside the loop and read it **after** the loop, while the loop might not run.

## 6. Local `final` Variables: First Assignment Allowed, No Reassignment

`final` allows writing a **blank final local** (declared without assignment), provided that before being read it has been validly assigned and is not reassigned along the execution path.

~~~java
static String mode(boolean custom) {
    final String selected;
    if (custom) {
        selected = "CUSTOM";
    } else {
        selected = "DEFAULT";
    }
    return selected;
}
~~~

The snippet above is valid: each execution path assigns `selected` exactly once before reading it.

Conversely:

~~~java
final int limit = 5;
// limit = 6; // ERROR: final variable cannot be reassigned
~~~

**`final` does not supply an initial value automatically.** If you declare `final int limit;` and read it without a definite assignment, `javac` still reports an error.


## 7. Scope of Application: Local Variables and Common Confusions

*Definite assignment* is checked for local variables. **Parameters** already receive values from the caller; **fields** are defaulted by type (numbers to `0`, `boolean` to `false`, references to `null`); **new array elements** are also defaulted by type.

~~~java
int[] numbers = new int[2];  // Local numbers is assigned a reference
System.out.println(numbers[0]); // 0: array element is defaulted
int[] missing;
// System.out.println(missing[0]); // Compile error: local missing unassigned
~~~

Being able to read a reference field defaulted to `null` does not guarantee calling a method on it is safe. The lesson on default values explains multidimensional arrays and specific types.

## 8. `var` Needs an Initializer to Infer Its Type

In Java 17, a local variable can use `var` when the compiler can infer its type from the initializer expression:

~~~java
var count = 5;        // Infers int
var name = "Java";    // Infers String
count = 6;            // Valid, still int
~~~

The following lines are invalid:

~~~java
// var count;          // Invalid: missing initializer to infer type
// var name = null;    // Invalid: cannot infer an appropriate type from null alone
// count = "six";      // Invalid: String cannot be assigned to int
~~~

`var` does not bypass type checking, nor does it relax the requirement to assign before reading. If you need to declare first and assign later in a conditional branch, use an **explicit type** such as `String label;`.

## 9. Complete, Runnable Java 17 Program

Create a file named exactly **`DefiniteAssignmentDemo.java`**:

~~~java
public final class DefiniteAssignmentDemo {
    private DefiniteAssignmentDemo() {}

    static final class Settings {
        int attempts;       // Field defaults to 0
        boolean enabled;    // Field defaults to false
        String note;        // Field defaults to null
    }

    static String review(boolean accepted) {
        String result;      // Declared unassigned
        if (accepted) {
            result = "ACCEPT";
        } else {
            result = "REJECT";
        }
        return result;      // Both branches assigned
    }

    static String classify(int number) {
        if (number < 0) {
            return "NEGATIVE";
        }
        String label;
        if (number == 0) {
            label = "ZERO";
        } else {
            label = "POSITIVE";
        }
        return label;
    }

    static long sum(int limit) {
        long result = 0L;   // Needs a value even if the loop does not run
        for (long i = 1; i <= limit; i++) {
            result += i;
        }
        return result;
    }

    static String chooseMode(boolean custom) {
        final String mode;
        if (custom) {
            mode = "CUSTOM";
        } else {
            mode = "DEFAULT";
        }
        return mode;
    }

    public static void main(String[] args) {
        int quantity;
        quantity = 4;
        System.out.println("quantity=" + quantity);

        System.out.println("review(true)=" + review(true));
        System.out.println("review(false)=" + review(false));
        System.out.println("classify(-2)=" + classify(-2));
        System.out.println("classify(0)=" + classify(0));
        System.out.println("classify(5)=" + classify(5));

        System.out.println("mode=" + chooseMode(args.length > 0));
        System.out.println("sum(4)=" + sum(4));
        System.out.println("sum(0)=" + sum(0));

        int[] numbers = new int[2];
        System.out.println("array[0]=" + numbers[0]);

        Settings settings = new Settings();
        System.out.println("field attempts=" + settings.attempts);
        System.out.println("field enabled=" + settings.enabled);
        System.out.println("field note=" + settings.note);
    }
}
~~~

Using **JDK 17 or later**, open a terminal in the directory containing the source file.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 DefiniteAssignmentDemo.java
java -cp . DefiniteAssignmentDemo
java -cp . DefiniteAssignmentDemo custom
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\DefiniteAssignmentDemo.java
java -cp . DefiniteAssignmentDemo
java -cp . DefiniteAssignmentDemo custom
~~~

Output for **the run without arguments**:

~~~text
quantity=4
review(true)=ACCEPT
review(false)=REJECT
classify(-2)=NEGATIVE
classify(0)=ZERO
classify(5)=POSITIVE
mode=DEFAULT
sum(4)=10
sum(0)=0
array[0]=0
field attempts=0
field enabled=false
field note=null
~~~

When running with the argument `custom`, all lines remain as above, **except the line `mode=CUSTOM`**. In this example, only the presence of arguments is checked via `args.length > 0`; the word `custom` itself is not parsed further.

## 10. How to Self-Diagnose Read-Before-Assignment Errors

When encountering an error similar to `variable x might not have been initialized`, check:

1. **What kind of variable is it?** If it is a local variable, do not assume it has a default value like a field.
2. **Where is the read?** Reads can hide inside `x++`, `x += 1`, `return x`, or as an argument passed to a method.
3. **Have all branches leading to the read line assigned it?** Check `if/else`, `switch`, and `return`/`throw` paths.
4. **Could a loop run 0 times?** If so, a value assigned *only* inside the loop is not guaranteed safe after the loop.
5. **Was it accidentally declared `final` and reassigned?** A blank final can be assigned on the first valid path; it cannot be assigned a second time.
6. **Are you using `var` without an initializer?** Switch to an explicit type or initialize immediately.
7. **Is the default value you picked meaningful?** Do not use `0`, `false`, or `null` merely to hide missing valid data.

The compiler checks **the certainty of assignment**, without knowing whether that value is valid for the business logic. A program can assign a completely wrong value and still pass the definite assignment check.

## 11. Short Exercises with Answers

### Exercise A — branch missing an assignment

~~~java
static int score(boolean passed) {
    int result;
    if (passed) {
        result = 100;
    }
    return result;
}
~~~

**Answer:** compile error because `passed=false` leaves `result` unassigned. You can add `else { result = 0; }` **if 0 fits the requirement**, or handle the false branch with a sensible `return`/`throw`.

### Exercise B — does incrementing read the variable?

~~~java
int counter;
// counter++;
~~~

**Answer:** yes. `counter++` has to read the old value so it is not yet valid. Put `int counter = 0;` before incrementing.

### Exercise C — why does the field not error?

~~~java
class Sample {
    int value;
    void show() {
        System.out.println(value);
    }
}
~~~

**Answer:** `value` is an **instance field**, defaulting to `0`. If `value` were an unassigned local variable inside the method, compilation behavior would differ.

### Exercise D — loop running 0 times

~~~java
int last;
for (int i = 0; i < 0; i++) {
    last = i;
}
// System.out.println(last);
~~~

**Answer:** when uncommenting the print line, `last` is not guaranteed to be assigned. The loop runs zero iterations so you cannot rely on the assignment in its body to read `last` afterward.

### Exercise E — final assigned in two branches?

~~~java
final String state;
if (ok) {
    state = "YES";
} else {
    state = "NO";
}
System.out.println(state);
~~~

**Answer:** valid if `ok` is an already-defined boolean variable. On each execution path, `state` is assigned **exactly once** before being read.

## 12. Completion Checklist

- [ ] Know that declaring a local variable does not mean it can be read before assignment.
- [ ] Recognize the `might not have been initialized` message as a compile error.
- [ ] Analyze execution paths through `if/else`, `return`, and `throw`.
- [ ] Understand that loops can execute 0 times.
- [ ] Know that `x++`, `x += 1`, and `x = x + 1` all need to read the old value.
- [ ] Distinguish local variables from parameters, fields, and array elements.
- [ ] Understand that `final` can be assigned once after declaration, but not reassigned.
- [ ] Understand that `var` needs an initializer to infer its type.
- [ ] Compile/run `DefiniteAssignmentDemo.java` and match each output line.
- [ ] Choose initial values based on actual requirements, not arbitrarily to avoid compiler errors.

**Conclusion:** Java requires local variables to be **definitely assigned on every path that can reach a read**. `javac` verifies this before execution; fields and array elements have default values, whereas local variables cannot be read while unassigned. Understanding definite assignment helps write `if/else` flows, loops, and `final` cleanly without artificial initializations.