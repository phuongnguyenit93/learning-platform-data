# How a Program Starts, Calls Methods, and Terminates

## 1. From the `java` Command to the `main` Method

In **Java 17+** running an application in compiled class mode, the command `java ClassName` selects the **entry-point class**, starts the JVM, and calls the matching `main` method. Before executing the body of `main`, the JVM needs to load, link, and initialize the required classes. `static` initializers can print messages **before** the first statement inside `main`.

The common entry point on Java 17:

~~~java
public static void main(String[] args) {
    // Program starts processing from here
}
~~~

A simple run proceeds in order: JVM initializes class → calls `main` → `main` calls methods → methods return → `main` finishes. If exceptions occur or other threads are running, the path can differ.

~~~mermaid
flowchart TD
    A["java FlowDemo"] --> B["Initialize required classes"]
    B --> C["main(String[] args)"]
    C --> D["Call method"]
    D --> E{"How does method end?"}
    E -->|"return"| F["Return to caller"]
    E -->|"throw"| G["Search for catch up the call chain"]
    F --> H["main continues"]
    G --> H
    G --> I["Uncaught: thread terminates abnormally"]
    H --> J["main finishes"]
    J --> K["JVM checks remaining live non-daemon threads"]
    I --> K
~~~

The diagram illustrates the high-level flow; it does not imply every error is caught or every JVM process terminates immediately after `main`.

## 2. Practice Program with Predictable Output

Create the file with the exact name **`FlowDemo.java`**:

~~~java
public final class FlowDemo {
    static {
        System.out.println("0. Khoi tao lop");
    }

    private FlowDemo() {}

    static int twice(int number) {
        System.out.println("3. Vao twice(" + number + ")");
        if (number < 0) {
            throw new IllegalArgumentException("number must be >= 0");
        }
        int value = Math.multiplyExact(number, 2);
        System.out.println("4. Tra ve " + value);
        return value;
    }

    static void display(int result) {
        System.out.println("6. Ket qua: " + result);
    }

    public static void main(String[] args) {
        System.out.println("1. Bat dau main");

        int input = args.length == 0 ? 3 : Integer.parseInt(args[0]);
        System.out.println("2. Input: " + input);

        int answer = twice(input);
        System.out.println("5. Quay lai main");

        display(answer);
        System.out.println("7. Het main");
    }
}
~~~

In the directory containing the file, check your JDK and compile/run.

**Bash (Linux/macOS):**

~~~bash
java -version
javac -version
javac --release 17 -encoding UTF-8 FlowDemo.java
java -cp . FlowDemo
java -cp . FlowDemo 5
~~~

**PowerShell (Windows):**

~~~powershell
java -version
javac -version
javac --release 17 -encoding UTF-8 .\FlowDemo.java
java -cp . FlowDemo
java -cp . FlowDemo 5
~~~

**Output with no arguments:**

~~~text
0. Khoi tao lop
1. Bat dau main
2. Input: 3
3. Vao twice(3)
4. Tra ve 6
5. Quay lai main
6. Ket qua: 6
7. Het main
~~~

**Output when passing `5`:**

~~~text
0. Khoi tao lop
1. Bat dau main
2. Input: 5
3. Vao twice(5)
4. Tra ve 10
5. Quay lai main
6. Ket qua: 10
7. Het main
~~~

Each `java` command in the example starts a new JVM, so the `static` block prints line `0` on **every run**.


## 3. How Do `main` Arguments Participate in Execution Flow?

With `java -cp . FlowDemo 5`, the launcher selects the `FlowDemo` class and passes the string `"5"` into `args[0]`. The `main` method uses `Integer.parseInt(args[0])` to convert the string into an `int` before calling `twice`. If no argument is supplied, the expression `args.length == 0 ? 3 : ...` chooses the default number `3`.

On Java 17, the traditional entry point is `public static void main(String[] args)`: the launcher invokes that `static` method without creating an object; `args` is an array of application argument strings. Breakdown of each part of the signature and the rules for checking `args.length` are covered in **Role of public static void main(String[] args)**. Here, observe **when** data conversion happens: passing `abc` causes `Integer.parseInt` to throw `NumberFormatException` right inside `main`, even before `twice` is called.

The command `java -cp . FlowDemo.class` is invalid in class mode; the launcher takes the class name `FlowDemo`. If the class is in a package, the fully qualified class name and matching classpath root are required, such as `java -cp out demo.Entry`.

## 4. Method Call Mechanics: Who Runs First and Who Receives the Result?

In the `FlowDemo` example, `main` reaches the expression:

~~~java
int answer = twice(input);
~~~

At that point:

1. Java evaluates the argument `input` and then performs the call to `twice`.
2. The body of `twice` executes from the start until `return` or until an exception is thrown.
3. `return value;` makes the `twice` call **complete normally** and passes the `int` value back to the expression at the caller.
4. `main` assigns that value to `answer` and only then prints line `5`.
5. `main` calls `display(answer)`. Because `display` returns `void`, it sends back no assignable value.
6. When `display` finishes, `main` continues with line `7`.

| Printed line | Active method | Why does it appear at that moment? |
|---|---|---|
| 0 | Static initializer | JVM initializes the class before calling `main` |
| 1, 2 | `main` | First statements inside `main` |
| 3, 4 | `twice` | `main` called `twice` and is waiting for the result |
| 5 | `main` | `twice` has returned |
| 6 | `display` | `main` calls `display` |
| 7 | `main` | `display` finishes, `main` continues |

**Declaring a method above `main` in the file does not make it run before `main`.** A method runs because it is called, not because of where it is written in the source file.

### `return` only exits the current method

~~~java
static void printIfPositive(int value) {
    if (value <= 0) {
        return;
    }
    System.out.println(value);
}

// Placed inside a main method:
printIfPositive(0);
System.out.println("main van tiep tuc");
~~~

The output is just `main van tiep tuc`. `return;` inside `printIfPositive` **does not** terminate `main`, let alone shut down the JVM.

## 5. Call Stack: Descending and Returning

Each Java thread has a **call stack** containing frames for the active method invocations. When a new method is called, the caller's context is preserved so execution can resume after the callee returns.

~~~text
While main is running:        When main calls twice:
+-----------------------+     +-----------------------+
| main(args)            |     | twice(number=3)       |  <-- currently running
+-----------------------+     +-----------------------+
                              | main(args)            |
                              +-----------------------+
After return: only main remains, continuing at the statement after the call.
~~~

This is an explanatory model, not an actual memory-address layout for every JVM.

Try another program, **`CallChain.java`**:

~~~java
public class CallChain {
    static int inner(int x) {
        System.out.println("inner");
        return x * 2;
    }

    static int middle(int x) {
        System.out.println("middle");
        return inner(x) + 1;
    }

    static void outer() {
        System.out.println("outer");
        int value = middle(3);
        System.out.println("value = " + value);
    }

    public static void main(String[] args) {
        System.out.println("main starts");
        outer();
        System.out.println("main ends");
    }
}
~~~

Run:

~~~bash
javac --release 17 CallChain.java
java -cp . CallChain
~~~

Output:

~~~text
main starts
outer
middle
inner
value = 7
main ends
~~~

The downward call sequence is `main → outer → middle → inner`. Results flow back up as `inner` returns `6`, `middle` returns `7`, and `outer` prints `7`. Thus `main ends` only appears after `outer` finishes.

## 6. Parameters: Java Always Passes by Value

When calling a method, Java **copies the argument's value** into the parameter. For primitives, that is the value itself, such as an `int`. For objects, that is the **reference value**, so both the caller and the callee can point to the same object.

~~~java
static void change(int n, StringBuilder box) {
    n = 99;
    box.append("!");
    box = new StringBuilder("Khac");
}

// Inside main:
int count = 3;
StringBuilder text = new StringBuilder("Hi");
change(count, text);
System.out.println(count); // 3
System.out.println(text);  // Hi!
~~~

Assigning `n = 99` does not change the caller's `count` variable. `box.append("!")` mutates the **shared object's state**, so `text` sees `Hi!`. Reassigning `box` does not make `text` point to the new object.

Do not describe Java as "pass-by-reference" merely because a mutable object can be modified through a parameter.

## 7. Throwing an Exception Differs from `return`

In `twice`, negative numbers are rejected:

~~~java
if (number < 0) {
    throw new IllegalArgumentException("number must be >= 0");
}
~~~

Try:

~~~bash
java -cp . FlowDemo -1
~~~

Before the stack trace, the program prints:

~~~text
0. Khoi tao lop
1. Bat dau main
2. Input: -1
3. Vao twice(-1)
~~~

Then `IllegalArgumentException` propagates from `twice` up to `main` because there is no matching `catch`. The stack trace typically looks like:

~~~text
Exception in thread "main" java.lang.IllegalArgumentException: number must be >= 0
    at FlowDemo.twice(FlowDemo.java:...)
    at FlowDemo.main(FlowDemo.java:...)
~~~

The line numbers in `...` depend on the file. Lines `4` through `7` are not printed because the call did not complete along the normal path.

With:

~~~bash
java -cp . FlowDemo abc
~~~

`Integer.parseInt("abc")` throws `NumberFormatException` while computing `input`, **before** line `2` and before `twice` is called. Only lines `0` and `1` appear before the error message.

To recover from an expected exception, the caller can handle it:

~~~java
try {
    int answer = twice(-1);
    System.out.println(answer);
} catch (IllegalArgumentException ex) {
    System.out.println("Input sai: " + ex.getMessage());
}
System.out.println("Tiep tuc");
~~~

When placed inside a valid method, it prints `3. Vao twice(-1)`, then `Input sai: number must be >= 0`, and then `Tiep tuc`. The `System.out.println(answer)` statement inside `try` does not execute because the exception transferred control to `catch`.

An uncaught exception can cause the **main thread** to terminate abnormally; that is not a `System.exit` call and does not guarantee no other threads remain.

## 8. When Does a Java Application Truly Stop?

Distinguish three situations:

| Case | Consequence |
|---|---|
| `main` runs to the end or executes `return;` | The main thread finishes |
| `main` exits due to an uncaught exception | The main thread terminates abnormally; usually prints a stack trace |
| `System.exit(status)` | Requests the JVM to run its shutdown sequence with the status code |

In a single-threaded application like `FlowDemo`, when `main` finishes normally, the JVM typically exits with **exit code 0**. However, if any **non-daemon thread** is still alive, the JVM normally keeps running after `main` completes.

Try **`ThreadExitDemo.java`**:

~~~java
public class ThreadExitDemo {
    public static void main(String[] args) {
        Thread worker = new Thread(() -> {
            try {
                Thread.sleep(200);
                System.out.println("worker finished");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });
        worker.start();
        System.out.println("main finished");
    }
}
~~~

Run:

~~~bash
javac --release 17 ThreadExitDemo.java
java -cp . ThreadExitDemo
~~~

You will see both `main finished` and `worker finished`. The print order is the result of thread scheduling and should not be treated as a fixed contract; the JVM still waits for the non-daemon worker to complete before shutting down normally.

`System.exit(2)` requests stopping the **entire JVM** with status 2 (by convention, non-zero indicates failure). It is not equivalent to `return;`, and **it does not guarantee that `finally` blocks of stopped threads run as they would on normal method exit**. Avoid calling `System.exit` in library methods; let the startup layer decide how to report errors and terminate the application.

## 9. `finally` on a `return` Path

A method with `return` inside `try` still executes `finally` before returning control to the caller, assuming the JVM exits the block normally:

~~~java
static int compute() {
    try {
        System.out.println("A. try");
        return 10;
    } finally {
        System.out.println("B. finally");
    }
}

// Called in main:
int value = compute();
System.out.println("C. value = " + value);
~~~

Output:

~~~text
A. try
B. finally
C. value = 10
~~~

Do not put `return` inside `finally` so you do not mask exceptions or alter the result of `try`. When managing resources such as files or streams, use `try-with-resources` where appropriate instead of relying on the JVM being about to exit.

## 10. Common Troubleshooting Table

| Symptom | Possible cause | What to check |
|---|---|---|
| `Main method not found` | Class lacks a Java 17 entry point | Signature `public static void main(String[] args)` |
| `Could not find or load main class` | Wrong package, classpath, or class name | Classpath root, `.class` file, fully qualified name |
| Lines after a method call do not print | `throw`, early `return`, or branch did not execute | Trace calls and stack trace |
| `NumberFormatException` | `args[0]` is not a valid integer | Validate and handle input |
| `ArithmeticException` in `multiplyExact` | Multiplication result exceeds `int` range | Check value range/data type |
| `main` finished but terminal has not returned prompt | Non-daemon worker or blocking task still active | Inspect thread states and blocking I/O |
| Log lines between two threads appear out of predicted order | Non-deterministic scheduling | Synchronize when order matters; do not infer from incidental logs |

## 11. Exercises with Answers

### Exercise A — follow the call

~~~java
static int addOne(int x) {
    System.out.println("B");
    return x + 1;
}
// In main:
System.out.println("A");
int y = addOne(4);
System.out.println("C:" + y);
~~~

**Answer:**

~~~text
A
B
C:5
~~~

Because the caller only prints `C:5` once `addOne` has completed and returned `5`.

### Exercise B — does `return` stop the JVM?

If `validate()` hits `return;` while `main` still has `System.out.println("done");` after the call, what happens?

**Answer:** `validate` finishes; `main` still prints `done` unless an exception or another branch prevents it.

### Exercise C — predict output on invalid input

With `FlowDemo`, run:

~~~bash
java -cp . FlowDemo -1
~~~

**Answer:** the program prints lines `0`, `1`, `2`, `3` and then reports `IllegalArgumentException`; it does not print `4` through `7`.

### Exercise D — overflow in a helper method

~~~bash
java -cp . FlowDemo 2147483647
~~~

**Answer:** `Math.multiplyExact` throws `ArithmeticException` due to `int` overflow; no valid return value is produced for `main` to assign to `answer`.

### Exercise E — `main` ended while a worker is still running

An application still has one non-daemon thread processing work. Must the JVM stop immediately when `main` returns?

**Answer:** No. The main thread finishing is different from the entire JVM process terminating; normally the JVM waits for non-daemon workers.

## 12. Checklist

- [ ] Know the common `main` entry-point signature on Java 17.
- [ ] Run `javac` and `java` commands properly and understand `args[0]`.
- [ ] Explain why a static initializer can run before the body of `main`.
- [ ] Trace `main → method → return → main`.
- [ ] Understand call stack frames and pass-by-value parameter passing.
- [ ] Distinguish `return`, `throw`, and `System.exit`.
- [ ] Read a stack trace and locate where an error originated.
- [ ] Recognize cases where `main` finishes while the JVM keeps running.
- [ ] Understand `finally` on a `return` path and the risks of forcing JVM termination.

**Conclusion:** The launcher selects the class with the entry point; the JVM initializes required classes and calls `main`. A method call transfers control into the method body, `return` sends a result back to the caller, while an exception can follow a different path. `main` finishing does not mean the JVM always stops immediately: process lifetime also depends on non-daemon threads and shutdown mechanisms.
