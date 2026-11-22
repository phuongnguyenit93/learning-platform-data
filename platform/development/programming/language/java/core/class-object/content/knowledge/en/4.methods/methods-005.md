# Call Execution Flow, return, and Abrupt Completion in Java Methods

A method is an important unit of behavior of a class and object. When one method calls another, the program does not simply "jump in and return": Java must determine which method is invoked, evaluate the receiver object and arguments, create an execution context for the invocation, execute the statements, and then **complete normally** or **complete abruptly** due to an error/exception or a control-flow mechanism.

This article explains that process using practical Java 17+ code: **method invocation → method body execution → `return` / `throw` → returning to the call site or propagating an exception**. You will also learn how to read a call stack and how `try`, `catch`, and `finally` affect the outcome.

## 1. Terms to Distinguish

| Term | Meaning in this article |
| --- | --- |
| **Caller** | The code containing the expression or statement that invokes a method |
| **Callee** | The method executed by that invocation |
| **Arguments** | The expressions passed at the call site; for example, `sum(2, 3)` has two arguments |
| **Parameters** | The variables that receive the argument values in the method declaration, for example `int left, int right` |
| **Call stack** | The stack model of active method invocations in a thread |
| **Stack frame** | The execution context of a single method invocation, containing the information required for that call according to JVM semantics |
| **Normal completion of an invocation** | The invocation completes along a valid return path, resuming execution in the caller |
| **Abrupt completion** | An execution construct terminates due to a reason such as `return`, `break`, `continue`, or `throw`, rather than reaching the end of its statements normally |

A very important point regarding Java terminology: **a `return` statement causes the method body to complete abruptly with the reason "return" according to the Java Language Specification, yet the _method invocation_ itself can still complete normally and return a value to the caller**. Conversely, if an exception escapes a method without being handled inside it, **the method invocation completes abruptly by `throw`**.

Example:

~~~java
static int add(int a, int b) {
    return a + b;
}
~~~

`return` stops the method body and provides a value. When calling `int result = add(2, 3);`, the invocation `add(2, 3)` completes normally with the result `5`.

## 2. Model of a Method Invocation

For the call `result = account.deposit(amount);`, the following model can be used:

~~~text
Caller
  |
  | 1. Determine the invocation mode, type, and matching method
  | 2. Evaluate the receiver and argument expressions
  | 3. Pass the argument values to the parameters
  v
Callee / method body
  |
  | 4. Execute statements following the control flow
  |
  +---- return / void body completes normally --------+
  |                                                   |
  +---- exception escapes the method -----------------+----> caller handles or propagates
                                                      |
Caller continues after the call if the invocation completes normally
~~~

At the **language** level, argument expressions are evaluated from left to right; an instance call also has a receiver expression. The JVM steps may be optimized by the JIT and do not necessarily create an independent physical frame exactly as depicted for every small method. However, the **observable order and behavior** must obey Java semantics.

### Instance Methods and Static Methods

~~~java
class Calculator {
    int doubleValue(int value) {
        return value * 2;
    }

    static int tripleValue(int value) {
        return value * 3;
    }
}
~~~

This is an **illustrative class** that can compile when placed in a suitable source file; it does not itself have `main` to run standalone.

- `new Calculator().doubleValue(4)` is an **instance method** invocation on a specific object; inside an instance method, `this` can be used.
- `Calculator.tripleValue(4)` invokes a **static method**, which does not have `this` for a specific Calculator.
- When using `instance.method()`, Java must determine the receiver object. If the receiver is `null`, it will result in a `NullPointerException` for an instance invocation unless the evaluation throws another exception first.
- A static method can be called from another method and still has an invocation in the execution flow; `static` does not mean "not using the call stack".

## 3. Nested Call Sequence: Reading from Caller to Callee and Back

Create the file **`CallFlowDemo.java`**:

~~~java
public class CallFlowDemo {
    static int trace(String label, int value) {
        System.out.println("trace " + label + ": " + value);
        return value;
    }

    static int twice(int number) {
        System.out.println("twice begin");
        int result = number * 2;
        System.out.println("twice end");
        return result;
    }

    static int combine(int first, int second) {
        System.out.println("combine begin");
        int doubled = twice(first);
        System.out.println("combine end");
        return doubled + second;
    }

    public static void main(String[] args) {
        System.out.println("main begin");
        int answer = combine(trace("first", 3), trace("second", 4));
        System.out.println("answer = " + answer);
        System.out.println("main end");
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac -encoding UTF-8 CallFlowDemo.java
java CallFlowDemo
~~~

Stdout:

~~~text
main begin
trace first: 3
trace second: 4
combine begin
twice begin
twice end
combine end
answer = 10
main end
~~~

Explanation in order:

1. `main` prints `main begin`.
2. Java needs to evaluate the arguments of `combine(...)`. `trace("first", 3)` runs first, prints one line, and returns `3`; then `trace("second", 4)` prints one line and returns `4`.
3. `combine(3, 4)` starts and prints `combine begin`.
4. `combine` calls `twice(first)` with `first = 3`; `twice` prints two lines and then executes `return 6`.
5. Returning from `twice` causes `combine` to resume at the line after `int doubled = twice(first);`. `combine` prints `combine end`, then returns `6 + 4 = 10`.
6. `main` receives the result `10`, then prints `answer = 10` and `main end`.

At the point when `twice` is running, the unfinished invocations have the following relationship:

~~~text
      Top of stack (currently executing call)
       +---------------------------+
       | twice(first)              |
       +---------------------------+
       | combine(3, 4)             |
       +---------------------------+
       | main(args)                |
       +---------------------------+
      Bottom of stack
~~~

When `twice` returns, execution continues in `combine`; when `combine` returns, execution continues in `main`. **A nested call temporarily transfers control to the callee; the unfinished caller can still resume after the callee returns.**

### Why Pay Attention to Argument Evaluation Order?

In `combine(trace("first", 3), trace("second", 4))`, both arguments have the side effect of printing logs. Java guarantees that argument expressions are evaluated **from left to right** in a method invocation. If the first argument throws an exception, the second argument **is not evaluated**, and the target method body is not entered yet.

You should not rely on evaluation order to intentionally create complex side effects across multiple arguments. A more readable coding style is:

~~~java
int first = trace("first", 3);
int second = trace("second", 4);
int answer = combine(first, second);
~~~

This snippet only illustrates how to organize statements, placed inside `main` or an appropriate method; the corresponding result remains unchanged.

## 4. Parameter Passing: Java Always Passes Arguments by Value

Before running the method body, the value of each argument is transferred to the corresponding parameter according to invocation conversion rules. For primitive types, the method receives a **copy of the primitive value**; for reference types, the method receives a **copy of the reference value**.

Create the file **`ParameterFlowDemo.java`**:

~~~java
public class ParameterFlowDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void change(int number, Box box) {
        number = 99;
        box.value = 20;
        box = new Box(500);

        System.out.println("inside number = " + number);
        System.out.println("inside box = " + box.value);
    }

    public static void main(String[] args) {
        int number = 5;
        Box box = new Box(10);

        change(number, box);

        System.out.println("outside number = " + number);
        System.out.println("outside box = " + box.value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ParameterFlowDemo.java
java ParameterFlowDemo
~~~

Stdout:

~~~text
inside number = 99
inside box = 500
outside number = 5
outside box = 20
~~~

Inside `change`:

- Assigning `number = 99` only changes the local parameter. The variable `number` in `main` remains `5`.
- Initially, the parameter `box` references **the same Box** as the `box` variable in `main`. `box.value = 20` modifies the state of the shared Box, so the caller sees `20`.
- The statement `box = new Box(500)` only assigns a **new reference to the parameter `box`**. It does not reassign the variable in the caller; the caller's Box still holds `20`.
- When `change` finishes, the parameters no longer exist in that invocation. The object created by `new Box(500)` is not automatically returned to the caller.

Therefore, saying "Java passes objects by reference so that a method can modify the original variable" is inaccurate. **Java uses pass-by-value**, and the value passed can be a reference to a mutable object.

## 5. How Does `return` Terminate a Method Body?

### Methods That Return a Value

A method with a return type other than `void` must have valid execution paths to return an appropriate value or terminate with an exception. `return expression;` evaluates the expression, applies a type conversion to the return value if permitted, and then terminates the method body.

~~~java
static int absolute(int number) {
    if (number >= 0) {
        return number;
    }
    return -number;
}
~~~

This is an **illustrative method snippet**, placed inside a corresponding class. If `number = 3`, the method returns `3` via the first branch; if `number = -3`, the method returns `3` via the second branch. In Java, specifically for the value `Integer.MIN_VALUE`, the operation `-number` on `int` overflows and remains negative; when designing an absolute value function for business logic, you should consider this edge case.

After executing a `return`, statements on the normal path following it **are not executed**. Code that is clearly unreachable can cause an `unreachable statement` compilation error.

Example of a compilation error, **do not include in runnable examples**:

~~~java
static int broken() {
    return 1;
    // System.out.println("never"); // If uncommented, this will be unreachable.
}
~~~

### `void` Methods and `return;`

A `void` method does not provide a result usable as an expression value. It can complete when control flow reaches the end of its body or use `return;` to exit early.

~~~java
static void printPositive(int value) {
    if (value <= 0) {
        return;
    }
    System.out.println(value);
}
~~~

A method with return type `void` cannot execute `return 42;`. Conversely, a method with return type `int` cannot simply write `return;`.

### Multiple `return` Paths Are Valid

Save the file **`ReturnBranchesDemo.java`**:

~~~java
public class ReturnBranchesDemo {
    static String grade(int score) {
        if (score < 0 || score > 100) {
            return "invalid";
        }
        if (score >= 80) {
            return "good";
        }
        if (score >= 50) {
            return "pass";
        }
        return "retry";
    }

    static void announce(String name) {
        if (name == null || name.isBlank()) {
            System.out.println("skip");
            return;
        }
        System.out.println("Hello " + name);
    }

    public static void main(String[] args) {
        System.out.println(grade(101));
        System.out.println(grade(85));
        System.out.println(grade(65));
        System.out.println(grade(20));

        announce("");
        announce("Mai");
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReturnBranchesDemo.java
java ReturnBranchesDemo
~~~

Stdout:

~~~text
invalid
good
pass
retry
skip
Hello Mai
~~~

Each invocation of `grade` follows only **one return branch**. After `return "good";`, the conditions below it are no longer checked in that call. `announce("")` prints `skip` and stops early; `announce("Mai")` continues on to print the greeting.

Use multiple `return` statements when each branch is short, meaningful, and easy to verify. There is no rule requiring every Java method to have only a single `return` statement.

### Every Control Path of a Non-Void Method Must Be Covered

Example that **does not compile**:

~~~java
static int sign(int number) {
    if (number > 0) {
        return 1;
    }
    // Error: there is a path reaching the end of the method without returning an int.
}
~~~

The compiler does not accept a method declared to return `int` if an execution path reaches the end of the method without returning a value. A method may throw an exception instead of returning a value on a valid branch:

~~~java
static int parseCount(String value) {
    if (value == null) {
        throw new IllegalArgumentException("value is required");
    }
    return Integer.parseInt(value);
}
~~~

The second snippet is a valid method: when `value` is null, it **does not return an `int`** but instead completes abruptly with an exception. When non-null, it evaluates `Integer.parseInt` and can return an `int` or go on to throw an exception if the string is invalid.

## 6. `return` of a Reference Type Does Not Automatically Copy the Object

If a method returns `Student`, `Box`, or another reference type, the returned value is a reference, not a deep copy of the object by default.

~~~java
class Document {
    String title;

    Document(String title) {
        this.title = title;
    }
}

class DocumentRepository {
    private final Document document = new Document("Draft");

    Document current() {
        return document; // Returns a reference to the same object.
    }
}
~~~

The two classes above are **illustrative code**, without `main`. If the caller receives `Document d = repository.current();` and modifies `d.title`, the object inside `DocumentRepository` is also modified, because `d` points to the same document.

For mutable objects, you should consider providing controlled operations or a defensive copy if you do not want the caller to directly affect internal state. `return` does not alter Java's aliasing rules.

If a method returns `int` or another primitive, the caller receives the computed primitive **value**. If a method returns a `null` reference, the invocation can still complete normally with the result value `null`; a `NullPointerException` may occur later when that result is used.

## 7. How Does "Abrupt Completion" by `throw` Differ from `return`?

`throw` causes control flow to exit the current execution point with an exception. If the exception is not handled inside the current method, it travels **up to the caller** through the active invocations. The caller can catch it with `catch`, or the exception continues to propagate higher.

Example:

~~~text
main()
   |
   +--> process(text)
           |
           +--> parsePositive(text)
                   |
                   +--> may throw IllegalArgumentException
           |
           +--> if the throw is not caught here:
                process does not return along the normal return path
   |
   +--> main catches the exception and then continues
~~~

Java distinguishes:

- **Checked exceptions:** certain exception types that the compiler requires to be handled or declared with `throws`, for example `java.io.IOException`. This checking rule is based on the exception type and the invocation context.
- **Unchecked exceptions:** `RuntimeException` and its subclasses, along with subclasses of `Error`, are not required to be declared or caught at compile time. Examples include `IllegalArgumentException`, `NumberFormatException`, and `NullPointerException`.
- **`throw`:** the statement that **throws** an exception object.
- **`throws`:** the part of a method declaration that describes the exceptions allowed to escape according to the type contract; `throws` itself does not throw an exception.
- **`catch`:** handles a matching exception thrown from the corresponding `try` block.

You should not catch `Exception` indiscriminately just so the program "reports no errors". Choose a handling site that can provide sensible behavior: notifying the user, prompting for re-entry, recovering the task, or closing resources.

## 8. Running in Practice: Exceptions Passing Through Call Layers

Save the file **`ExceptionFlowDemo.java`**:

~~~java
public class ExceptionFlowDemo {
    static int parsePositive(String text) {
        System.out.println("parse begin: " + text);
        int value = Integer.parseInt(text);

        if (value <= 0) {
            throw new IllegalArgumentException("must be positive");
        }

        System.out.println("parse end");
        return value;
    }

    static int process(String text) {
        System.out.println("process begin");

        try {
            int number = parsePositive(text);
            System.out.println("process normal");
            return number * 2;
        } finally {
            System.out.println("process finally");
        }
    }

    public static void main(String[] args) {
        for (String input : new String[] {"4", "0", "oops"}) {
            System.out.println("input=" + input);

            try {
                System.out.println("result=" + process(input));
            } catch (IllegalArgumentException ex) {
                System.out.println("caught=" +
                        ex.getClass().getSimpleName());
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 ExceptionFlowDemo.java
java ExceptionFlowDemo
~~~

Stdout:

~~~text
input=4
process begin
parse begin: 4
parse end
process normal
process finally
result=8
input=0
process begin
parse begin: 0
process finally
caught=IllegalArgumentException
input=oops
process begin
parse begin: oops
process finally
caught=NumberFormatException
~~~

### Analyzing the `"4"` Case

1. `main` starts calling `process("4")`.
2. `process` prints `process begin` and then calls `parsePositive("4")`.
3. `parsePositive` converts the string to the number 4, prints `parse end`, and executes `return 4`.
4. `process` prints `process normal` and prepares `return 8`.
5. Before the method completes, the `finally` block prints `process finally`.
6. The `process` invocation completes normally with the value 8; only **after that** is the outer expression printed via `System.out.println("result=" + ...)`.

### Analyzing the `"0"` Case

`parsePositive("0")` parses the number 0 but throws `IllegalArgumentException` on the non-positive check. Therefore, the `parse end` line **does not run**, `parsePositive` does not return a value, and `process` does not print `process normal`.

Before the exception leaves `process`, `finally` prints `process finally`. `main` receives the exception at `catch (IllegalArgumentException ex)` and prints the exception class name. There is no `result=...` line because the argument evaluation for `println` did not complete.

### Analyzing the `"oops"` Case

`Integer.parseInt("oops")` throws `NumberFormatException`. This is a subclass of `IllegalArgumentException`, so the same `catch (IllegalArgumentException ex)` handles it. `ex.getClass().getSimpleName()` reflects the **runtime type** `NumberFormatException`.

Both errors cause `finally` to run under normal conditions, but the exception causes are different. That is why, when diagnosing an error, you must read the **exception type and stack trace**, not merely check whether some `catch` statement exists.

## 9. How Do `try`, `catch`, and `finally` Alter the Exit Path?

A method can complete through multiple branches:

~~~text
                       try
                        |
             +----------+----------+
             |                     |
       no exception            exception
             |                     |
      next statement        matching catch?
             |              /             \
             |            yes              no
             |             |                |
             |         run catch    propagate exception
             |             |                |
             +-------------+----------------+
                           |
                   finally if present
                           |
              continue, return, or throw
              based on the final outcome
~~~

The diagram simplifies the case where the blocks do not themselves throw other exceptions. In practice, `catch` or `finally` itself can also `return` or `throw`, changing the outcome. `finally` is executed when control leaves `try`/`catch` via normal mechanisms, including `return` and exceptions; however, `finally` cannot be relied upon as a guarantee to run in every case where the JVM/process terminates abruptly.

### `finally` Still Runs When `try` Has `return`

Create the file **`FinallyReturnDemo.java`**:

~~~java
public class FinallyReturnDemo {
    static int calculate() {
        int value = 1;

        try {
            System.out.println("try");
            return value;
        } finally {
            value = 9;
            System.out.println("finally value=" + value);
        }
    }

    public static void main(String[] args) {
        System.out.println("returned=" + calculate());
    }
}
~~~

~~~bash
javac -encoding UTF-8 FinallyReturnDemo.java
java FinallyReturnDemo
~~~

Stdout:

~~~text
try
finally value=9
returned=1
~~~

Explanation: the expression of `return value;` is evaluated while `value` is still 1. Before completing the invocation, `finally` sets the **local variable** `value` to 9 and prints the log. The previously determined return value remains 1.

**Distinguish the case of returning a mutable object:** If `return ref;` has already evaluated the reference to an object, `finally` can still modify the fields of that object before the caller uses it. The caller still receives the same reference but may observe the object's state after `finally` modifies it. That does not contradict the fact that the reference value of the `return` expression was already determined.

### Do Not `return` Inside `finally` If You Want to Preserve `try`'s Result

The following method snippet is valid, but **should not be applied as a normal design pattern**:

~~~java
static int confusing() {
    try {
        return 1;
    } finally {
        return 2;
    }
}
~~~

The `return 2;` statement inside `finally` replaces the previous completion reason, causing the method to return **2**. Similarly, if `try` threw an exception and `finally` executes `return`, the original exception can be masked. If `finally` throws a new exception, the new exception can replace the pending outcome, making diagnosis difficult.

Keep `finally` for appropriate cleanup work, and avoid `return`, `break`, `continue`, or intentionally throwing another error from cleanup unless the design and contract truly require it.

### Catching an Exception Does Not Necessarily Stop the Method

~~~java
static int recover() {
    try {
        Integer.parseInt("bad");
        return 1;
    } catch (NumberFormatException ex) {
        System.out.println("recovered");
    }
    return 2;
}
~~~

This is an **illustrative method snippet**; when called, it prints `recovered` and returns 2. The exception has been handled by `catch`; control flow continues after the `try-catch` block. An exception occurring does not mean the method always exits immediately, nor does every `catch` block have to `return`.

## 10. `try-with-resources` and Resource Closing Order

When a method uses a file, stream, socket, or connection implementing `AutoCloseable`, you should learn how to close resources in the execution flow. `try-with-resources` provides an automatic closing mechanism when exiting the block, even if the block throws an exception.

Create the file **`ResourceCloseDemo.java`**:

~~~java
public class ResourceCloseDemo {
    static final class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        try (Resource first = new Resource("A");
             Resource second = new Resource("B")) {
            System.out.println("body");
        }

        System.out.println("after");
    }
}
~~~

~~~bash
javac -encoding UTF-8 ResourceCloseDemo.java
java ResourceCloseDemo
~~~

Stdout:

~~~text
open A
open B
body
close B
close A
after
~~~

Resources are initialized from left to right and closed in the **reverse** order: B then A. Closing resources is part of exiting the block, handled before control flow continues to the `after` line.

If the `try` body throws an exception and `close()` also throws an exception, the try-with-resources mechanism generally preserves the primary exception and attaches the resource-closing error as a **suppressed exception**; it can be inspected via `Throwable.getSuppressed()`. This preserves the primary cause instead of arbitrarily using `return` inside `finally` and masking the original error.

Certain special cases, such as immediate JVM termination, still provide no guarantee that cleanup will occur. Do not equate `try-with-resources` with garbage collection scheduling: GC does not replace closing resources according to business logic.

## 11. Checked Exceptions, `throws`, and Method Boundaries

For a checked exception such as `java.io.IOException`, the compiler checks methods that might allow the exception to escape. A method can handle it with `catch` or declare the exception in its signature.

Illustrative method snippet:

~~~java
static String firstLine(java.nio.file.Path path)
        throws java.io.IOException {
    try (java.io.BufferedReader reader =
            java.nio.file.Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
~~~

This snippet is not a standalone runnable file; it is a method placed inside a class, using a `Path` parameter provided by the caller. `newBufferedReader` and `readLine` can throw `IOException`. The method **declares `throws IOException`** so that the caller is responsible for handling or propagating it, while closing the reader when the block finishes.

Example of a caller handling it:

~~~java
try {
    String line = firstLine(path);
    System.out.println(line);
} catch (java.io.IOException ex) {
    System.out.println("Cannot read file: " + ex.getMessage());
}
~~~

This is also an **illustrative snippet**, requiring a `path` variable of type `Path` and the `firstLine` method in the same appropriate context. The takeaway is not the detailed I/O syntax, but that **abrupt completion can cross multiple method boundaries**, and `throws` clarifies part of a method's contract.

A method declaring `throws IOException` does not mean that every invocation will throw an exception. If the execution path completes and returns, the invocation is still normal. Conversely, an unchecked exception can escape even if the method does not declare it in `throws`.

## 12. Evaluation Order and Errors Right in the Arguments

Sometimes an error occurs **before the target method begins running**. When reading a stack trace or log, you must determine whether the exception arose in an expression preparing the invocation or inside the method body itself.

Create the file **`ArgumentEvaluationDemo.java`**:

~~~java
public class ArgumentEvaluationDemo {
    static int first() {
        System.out.println("first argument");
        return 1;
    }

    static int second() {
        System.out.println("second argument");
        throw new IllegalStateException("failed to prepare second");
    }

    static void receive(int a, int b) {
        System.out.println("receive body");
    }

    public static void main(String[] args) {
        try {
            receive(first(), second());
        } catch (IllegalStateException ex) {
            System.out.println("caught: " + ex.getMessage());
        }
        System.out.println("main continues");
    }
}
~~~

~~~bash
javac -encoding UTF-8 ArgumentEvaluationDemo.java
java ArgumentEvaluationDemo
~~~

Stdout:

~~~text
first argument
second argument
caught: failed to prepare second
main continues
~~~

`first()` runs and returns 1, then `second()` starts, prints a log, and throws `IllegalStateException`. Because the second argument does not finish evaluating, the `receive` method **is not entered**, so the `receive body` line does not appear. `catch` in `main` handles the exception, and then the program prints `main continues`.

### The Receiver Expression Is Also Evaluated Before an Instance Invocation

In `getService().run(computeArgument())`, the `getService()` expression is evaluated to determine the receiver before the argument expressions. If evaluating the receiver **itself throws an exception**, the subsequent arguments are not evaluated. If the receiver result is `null`, in a normal instance invocation Java still evaluates the argument expressions before detecting that the call has no valid receiver and throwing `NullPointerException` (unless another exception occurs earlier). This is a subtle difference between a **receiver expression throwing an exception** and a **receiver expression returning `null`**.

You do not need to write code with side effects inside arguments to demonstrate this rule. In normal design, placing intermediate results into clearly named local variables makes debugging easier.

## 13. Overloading Selects the Signature; Overriding Selects the Implementation

An instance invocation is influenced by two mechanisms that are easily confused:

- **Overloading**: multiple methods share the same name but have different parameter lists; the compiler selects the matching signature based on the expression types at the call site and overload resolution rules.
- **Overriding**: a subclass provides an implementation for an inherited instance method that allows overriding; at runtime, the appropriate implementation is chosen based on the actual type of the receiver.

Create the file **`DispatchFlowDemo.java`**:

~~~java
public class DispatchFlowDemo {
    static class Parent {
        String render(Object value) {
            return "Parent(Object)";
        }

        String render(String value) {
            return "Parent(String)";
        }
    }

    static final class Child extends Parent {
        @Override
        String render(Object value) {
            return "Child(Object)";
        }
    }

    public static void main(String[] args) {
        Parent receiver = new Child();
        Object data = "hello";

        System.out.println(receiver.render(data));
        System.out.println(receiver.render("hello"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 DispatchFlowDemo.java
java DispatchFlowDemo
~~~

Stdout:

~~~text
Child(Object)
Parent(String)
~~~

On the first line, the variable `data` has the **declared type `Object`**, even though its runtime object is a `String`. The compiler selects the `render(Object)` overload. The runtime receiver is `Child`, so the overriding implementation `Child.render(Object)` is invoked.

On the second line, the literal argument `"hello"` has type `String`, so the compiler selects the `render(String)` overload. `Child` does not override this version, so the inherited implementation `Parent.render(String)` is used.

Even though both statements have the same runtime receiver Child and string data with the same content, the executed method can differ because **overload resolution happens first, dynamic dispatch happens second**. This is an important factor when tracing the call flow of a class hierarchy.

Static methods are not overridden via dynamic dispatch like instance methods. If a subclass declares a static method with a matching signature, that is **method hiding**; its resolution differs from overriding.

## 14. Recursion Also Consists of Normal Method Invocations

A method can call itself. Semantically, each call has its **own parameters and local variables**, with the same caller–callee relationship as any other method. There must be a stopping condition to avoid looping infinitely.

Create the file **`RecursiveReturnDemo.java`**:

~~~java
public class RecursiveReturnDemo {
    static int factorial(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("n must be >= 0");
        }
        if (n <= 1) {
            return 1;
        }
        return n * factorial(n - 1);
    }

    public static void main(String[] args) {
        System.out.println(factorial(4));
    }
}
~~~

~~~bash
javac -encoding UTF-8 RecursiveReturnDemo.java
java RecursiveReturnDemo
~~~

Stdout:

~~~text
24
~~~

Sequence of calls:

~~~text
factorial(4)
  -> 4 * factorial(3)
          -> 3 * factorial(2)
                  -> 2 * factorial(1)
                          -> return 1
                  -> return 2
          -> return 6
  -> return 24
~~~

The multiplications are completed on the way **back**: after `factorial(1)` returns 1, `factorial(2)` computes 2, then `factorial(3)` computes 6, and finally `factorial(4)` computes 24.

If the stopping condition is missing or the recursion depth is too large, execution can lead to a `StackOverflowError`. Java **does not guarantee tail recursion optimization**, so do not rely on unbounded or deeply nested recursive calls to process large inputs. The example uses `int`, which also has representation limits: `factorial(13)` exceeds the `int` range and overflows with ordinary multiplication; this is an arithmetic issue independent of the call stack.

## 15. Exceptions and the Call Stack: Reading an Error as an Execution Path

When an exception is not handled inside a method, the JVM can generate a stack trace describing the sequence of relevant calls. An illustrative trace may look like:

~~~text
java.lang.IllegalStateException: failed
    at Demo.leaf(Demo.java:...)
    at Demo.middle(Demo.java:...)
    at Demo.main(Demo.java:...)
~~~

This is a **format simulation**, not fixed stdout: line numbers, file names, and details can vary depending on the program, environment, and how the JVM constructs the stack trace.

Reading from top to bottom:

1. The first line shows the **exception type and message**.
2. Frames near the top usually point to the location where the error was thrown/detected.
3. Lower frames show the callers that invoked the execution path leading to the error.
4. Tracing this flow backward helps identify which input caused the error, which method passed the input, and whether any `catch` handled it.

If an exception is unhandled and escapes to the thread's entry point, the default mechanism typically prints the stack trace to **stderr**, not stdout. You should not copy a stack trace output with guessed line numbers as the "exact output" of the lesson.

### When Does a Call Not Return Normally?

- The method body throws an exception and does not catch it there.
- A method invoked inside it throws an exception; the current method does not handle it.
- A receiver or argument expression throws an exception before the target method body runs.
- Code inside `finally` throws an exception that replaces the pending completion path.
- The JVM may encounter serious errors such as `StackOverflowError` or `OutOfMemoryError`; do not assume every runtime error can be handled and resumed safely.

Having a `return` at the end of a method does not guarantee the method always returns a result: any preceding expression or operation can also throw an exception if an error condition occurs.

## 16. Practice Analyzing Flow Before Running

### Exercise 1 — Predict the Log Order

Given the illustrative code snippet placed inside a class:

~~~java
static int left() {
    System.out.println("L");
    return 2;
}

static int right() {
    System.out.println("R");
    return 3;
}

static int sum(int a, int b) {
    System.out.println("S");
    return a + b;
}
~~~

When calling `System.out.println(sum(left(), right()));`, the output is:

~~~text
L
R
S
5
~~~

Explanation: Java evaluates the two arguments from left to right, then executes the body of `sum`; the outermost `println` only prints 5 once the `sum(...)` expression has completed.

### Exercise 2 — Early `return`

~~~java
static String status(int count) {
    if (count < 0) {
        return "invalid";
    }
    if (count == 0) {
        return "empty";
    }
    return "active";
}
~~~

The predicted results for `status(-2)`, `status(0)`, and `status(3)` are `invalid`, `empty`, and `active`, respectively. Only one `return` branch is executed in each invocation.

### Exercise 3 — An Exception Prevents Subsequent Statements from Running

~~~java
static int fail() {
    throw new IllegalStateException("boom");
}

static int compute() {
    int result = fail();
    System.out.println("unreachable at runtime");
    return result + 1;
}
~~~

This snippet is **illustrative** and compiles inside an appropriate class. The code after `fail()` is valid syntax that compiles because the compiler is not required to deduce that calling `fail` always throws an exception, yet **when running this version of `fail`**, it will not print the `unreachable at runtime` line and will not execute `return result + 1`. You must distinguish "the compiler detecting an unreachable statement" from "a line not being reached due to runtime data or exceptions".

### Exercise 4 — `finally` and the Return Value

~~~java
static int value() {
    int n = 1;
    try {
        return n + 1;
    } finally {
        n = 100;
    }
}
~~~

The result is **2**, not 101. The expression `n + 1` is evaluated before `finally` runs; `finally` only modifies the local variable.

### Exercise 5 — Reading a Recursive Call Stack

For `factorial(4)`, write down the pending calls when `factorial(1)` begins. The order from the bottom to the top of the stack is `main → factorial(4) → factorial(3) → factorial(2) → factorial(1)`. After `return 1`, the levels return `2`, `6`, and `24` respectively.

## 17. Common Mistakes When Reading and Writing Call Flows

| Misconception | Correct Understanding |
| --- | --- |
| "Whenever `return` is encountered in a callee, the entire program stops." | `return` stops the callee invocation; the caller can continue after the call. |
| "`return` and `throw` both return a value." | `return` returns a result or exits a `void` method; `throw` propagates an exception rather than returning a normal value. |
| "A `void` method cannot exit early." | A `void` method can use `return;` without an expression. |
| "Both primitive and reference parameters are passed by reference." | Java passes by value; for objects, a copy of the **reference** is passed. |
| "Two arguments can be evaluated in any arbitrary order." | Java specifies left-to-right evaluation in a method invocation. |
| "The target method always runs even if an argument raises an error." | If preparing an argument throws an exception, the target method may never be entered. |
| "A method with `return` definitely cannot throw an exception." | Any expression before or during the return process can throw an exception; `finally` can also change the outcome. |
| "`finally` only runs when an exception occurs." | It executes on both normal completion paths and `return` paths under normal conditions. |
| "The return value is always computed after `finally`." | The `return` expression is evaluated first; `finally` runs before the invocation actually completes. |
| "`return` inside `finally` is a safe way to override a result." | It masks the pending `return` or exception; it should be avoided. |
| "`throws` throws an exception by itself." | `throws` only declares the exception types that may escape; `throw` actually raises the exception. |
| "Overload selection is determined by the runtime object type of the argument." | Overload resolution is based on compile-time types; overriding uses dynamic dispatch for instance methods. |
| "Without `catch`, every exception automatically disappears when the method ends." | An exception can propagate up through callers, eventually terminating the thread if unhandled. |
| "Ending a method immediately destroys every object it created." | Objects may still be reachable via the caller or fields; memory reclamation is not the same as method return. |

## 18. Learning Verification Checklist

- [ ] I can identify the caller, callee, argument, and parameter in an invocation.
- [ ] I can draw the call stack of three nested calls and indicate the return order.
- [ ] I can predict the log printing order when arguments are calls to other methods.
- [ ] I can distinguish `void` methods, value-returning methods, `return;`, and `return expression;`.
- [ ] I understand that `return` exits a single call, whereas an unhandled exception can propagate across multiple calls.
- [ ] I understand that both primitives and object references are passed by value in Java.
- [ ] I can pinpoint where a target method has not executed because the receiver or an argument threw an exception.
- [ ] I know how `try`, `catch`, and `finally` can alter control flow.
- [ ] I can predict the return value from `try` when `finally` modifies a local variable.
- [ ] I know why `return` inside `finally` risks masking the original error.
- [ ] I know the meanings of checked exception, unchecked exception, `throw`, and `throws`.
- [ ] I can distinguish overload resolution from dynamic dispatch when invoking methods on a class with inheritance.
- [ ] I can run each Java 17+ program in this article and compare stdout before and after modifying the data.

When you need to analyze a Java program with multiple methods, ask in turn: **which argument is evaluated first, which method is actually selected, can the running method exit via `return` or `throw`, does `finally` execute, and where will the caller resume?** Answering these questions in sequence helps trace execution flow systematically, pinpoint bugs accurately, and design class behavior that is easy to test.
