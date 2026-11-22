# Exceptions Originating from Java Code, APIs, or the JVM

## 1. Objectives

When reading a stack trace, you often see an exception name such as `NullPointerException`, `NumberFormatException`, or `IOException`. The error type name tells you **what was reported**, but it is not enough to tell you **who or which mechanism created that error**.

After this lesson, you will be able to:

- Distinguish three common origins of exceptions: application code actively executing `throw`, an API method reporting a failure, and the JVM raising an exception/error during execution.
- Identify where an exception originates, how it propagates across methods, how `catch` selects a handler, and its effect on `finally`.
- Explain why the same exception type can come from multiple sources, especially `NullPointerException` and `IllegalArgumentException`.
- Distinguish checked exceptions, unchecked exceptions, and `Error` regardless of their origin.
- Write and run Java 17+ examples, observe the control flow, and apply appropriate diagnostic approaches.

> “Java code”, “API”, and “JVM” are classifications based on **where or which mechanism reports the error**. They are not three independent class branches in the `Throwable` hierarchy. An API is also written in Java or native code, and the JVM runs both application code and API code.

## 2. Background: how does an exception enter the control flow?

In Java, the thrown object must be `Throwable` or one of its subclasses. Main hierarchy:

```text
java.lang.Throwable
├── java.lang.Exception
│   ├── checked exceptions (e.g., IOException)
│   └── java.lang.RuntimeException
│       ├── IllegalArgumentException
│       │   └── NumberFormatException
│       ├── NullPointerException
│       └── IndexOutOfBoundsException
└── java.lang.Error
    ├── AssertionError
    ├── LinkageError
    └── VirtualMachineError
        ├── OutOfMemoryError
        └── StackOverflowError
```

This is a **diagram of representative classes**, not an exhaustive listing of the entire hierarchy. Classes in the `Error` branch are not `Exception` even though all of them can be thrown. In Java, `RuntimeException` and `Error` along with their subclasses belong to the *unchecked* group; other `Exception` classes that do not inherit from `RuntimeException` are generally *checked* (or more technically precise: any subclass of `Throwable` that is neither `RuntimeException` nor `Error` is checked).

When an expression or method call completes abruptly (*abrupt completion*) by throwing an exception:

1. The remainder of the currently executing expression/statement does not continue normally.
2. The JVM searches for a matching `catch` handler in the enclosing `try` blocks.
3. If there is no handler in the current method, propagation continues to the caller; appropriate `finally` blocks are executed during normal stack unwinding.
4. If uncaught all the way to the thread's execution boundary, the exception may reach `UncaughtExceptionHandler`; that thread terminates. This does not necessarily stop all threads or the entire JVM immediately.

The origin **does not change the propagation mechanism**. An `IllegalArgumentException` that you `throw` and an `IllegalArgumentException` thrown by an API both go through the same `catch` selection rules.

## 3. Three main origins

| Origin | What creates the error signal? | Typical examples | What to check |
| --- | --- | --- | --- |
| **Java application code** | A `throw` statement written by the developer when a condition/invariant is not met | `throw new IllegalArgumentException("age < 0")` | Validation conditions, method contract, input data |
| **API/library** | The called method reports a failure according to its contract; internally it may use a Java `throw` or native handling | `Integer.parseInt("12x")` → `NumberFormatException`; `Files.readString(path)` can throw `IOException` | JavaDoc, arguments, resource state, `throws`, root cause |
| **JVM at runtime** | A language/bytecode-level operation violates a runtime condition or the VM cannot satisfy resource demands | Calling a method on `null` → `NullPointerException`; integer division by 0 → `ArithmeticException`; stack exhausted → `StackOverflowError` | Code/bytecode line, runtime values, message, and JVM state |

**Note on boundaries:** You cannot conclude for certain whether it is “from the JVM”, “from an API”, or “from your own code” **by the class name alone**. For example, `NullPointerException` can come from dereferencing `null` in bytecode, from `Objects.requireNonNull(null)` in an API, or from a developer explicitly writing `throw new NullPointerException()`. The stack trace, call site, and API contract are what help identify the origin.

### 3.1. Exceptions actively thrown by Java code

Syntax:

```java
if (quantity <= 0) {
    throw new IllegalArgumentException("quantity must be positive");
}
```

This is an **illustrative snippet inside a method**. The `throw` statement creates an abrupt exit; subsequent statements on the same branch do not run. If a method is declared to return a value, the `throw` path does not need to return a value.

Choose the exception type to communicate the contract accurately:

- `IllegalArgumentException`: invalid argument; a common variant is `NumberFormatException`.
- `IllegalStateException`: the current state does not allow the operation.
- Custom or built-in checked exception: the caller needs to know and is forced by the compiler to handle/declare it if the thrown type is checked.
- Do not use `Error` or `OutOfMemoryError` to express ordinary business/application errors.

The `throw` statement can rethrow **the same caught object**:

```java
try {
    performWork();
} catch (IllegalStateException failure) {
    // Log appropriate context, then preserve the original exception.
    throw failure;
}
```

This is an **illustrative snippet**; `performWork()` is not defined in this fragment. When creating a wrapper exception with `new SomeException(message, cause)`, preserve `cause` so the causal chain is not lost.

### 3.2. Exceptions reported by a Java API or library

APIs have contracts regarding valid data and failure conditions. Examples:

```java
Integer.parseInt("12x");        // NumberFormatException
java.util.Objects.requireNonNull(null); // NullPointerException
java.util.List.of("a").get(3); // IndexOutOfBoundsException
```

The lines above are **isolated examples of calls that throw errors**, not a complete `main` program. `Integer.parseInt` detects that the string cannot be converted to an `int`; `Objects.requireNonNull` actively checks the reference; `List.get` checks the index. These are errors reported according to the **API contract**, even when the exception type overlaps with a type the JVM can throw.

APIs also declare checked exceptions:

```java
String content = java.nio.file.Files.readString(path); // may throw IOException
```

This is an **illustrative snippet**; `path` must be an initialized `java.nio.file.Path`, and the statement must be placed inside an `IOException` handling block or a method with `throws IOException`. Depending on the filesystem and permissions, the call may succeed or report a subclass of `IOException`.

Read the JavaDoc to determine: what the method accepts, which types it throws, whether it validates arguments, and whether it depends on files/network/configuration/threads. `throws` in the signature describes checked exceptions that must be accounted for; some unchecked exceptions are documented in the JavaDoc without being required in the signature.

### 3.3. Exceptions/errors the JVM may raise during execution

Some Java operations perform runtime checks and can fail even when there is **no explicit `throw` statement in the source code**.

| Operation | Example | Type that may be raised |
| --- | --- | --- |
| Accessing a field/calling a method via `null` | `String s = null; s.length();` | `NullPointerException` |
| Accessing an array element out of bounds | `int[] a = new int[1]; int x = a[2];` | `ArrayIndexOutOfBoundsException` |
| Casting a reference to an incompatible type | `Object x = "hi"; Integer n = (Integer) x;` | `ClassCastException` |
| Integer division by 0 | `int zero = 0; int q = 10 / zero;` | `ArithmeticException` |
| Creating an array with a negative size | `int[] a = new int[-1];` | `NegativeArraySizeException` |
| Assigning an element incompatible with the runtime type of a reference array | `Object[] a = new String[1]; a[0] = 42;` | `ArrayStoreException` |
| Thread stack exceeds its limit | Deeply nested recursion | `StackOverflowError` (`Error`) |
| JVM cannot satisfy an allocation/resource request | Heap exhaustion, native resource limits depending on the situation | `OutOfMemoryError` (`Error`) |

Technical notes:

- With `double` or `float` operands, division by `0.0` under IEEE 754 normally produces `Infinity` or `NaN`, **not** an `ArithmeticException` like integer division by 0.
- `Error` types such as `OutOfMemoryError` and `StackOverflowError` belong to `Throwable` but **do not belong to `Exception`**; `catch (Exception e)` will not catch them.
- Do not intentionally trigger out-of-memory/stack-overflow errors to test handling logic in production; the consequences depend on the JVM, resources, and implementation.

## 4. Runnable example: observing all three origins

Create the file **`ExceptionOriginsDemo.java`**:

```java
import java.util.Objects;

public class ExceptionOriginsDemo {
    private static void validateAge(int age) {
        if (age < 0) {
            throw new IllegalArgumentException("age cannot be negative");
        }
    }

    private static void observe(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": OK");
        } catch (RuntimeException failure) {
            System.out.println(label + ": "
                    + failure.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        observe("Java code", () -> validateAge(-1));

        observe("JDK API parse", () -> Integer.parseInt("12x"));

        observe("JDK API null check", () -> Objects.requireNonNull(null));

        observe("JVM null access", () -> {
            String text = null;
            text.length();
        });

        System.out.println("Program continues");
    }
}
```

Compile and run with **JDK 17+**:

```bash
javac ExceptionOriginsDemo.java
java ExceptionOriginsDemo
```

`stdout` output:

```text
Java code: IllegalArgumentException
JDK API parse: NumberFormatException
JDK API null check: NullPointerException
JVM null access: NullPointerException
Program continues
```

Line-by-line explanation:

1. **Java code**: `validateAge(-1)` checks the argument and actively executes `throw new IllegalArgumentException(...)`.
2. **JDK API parse**: `Integer.parseInt("12x")` receives an invalid string and throws `NumberFormatException` per the API contract.
3. **JDK API null check**: `Objects.requireNonNull(null)` actively checks the reference and throws `NullPointerException` at the API layer.
4. **JVM null access**: calling `text.length()` attempts to dereference `null`, causing the JVM to throw `NullPointerException` during execution.
5. **Program continues**: `observe` handles each `RuntimeException` right at the example's boundary, so the main thread continues. In real applications, you should not necessarily catch every `RuntimeException`; recovery boundaries must have a clear purpose.

The program prints only the **exception class name**, avoiding reliance on detailed `NullPointerException` messages that can vary by JDK, bytecode, and JVM configuration.

Key takeaway: the last two lines in the error group both print `NullPointerException`, but one error is from an API method performing an active check, while the other is from the JVM checking a reference access operation.

## 5. Exception propagation: any origin goes through the same mechanism

Create the file **`ExceptionFlowDemo.java`**:

```java
public class ExceptionFlowDemo {
    private static void lowLevel() {
        System.out.println("low: before throw");
        throw new IllegalStateException("invalid state");
    }

    private static void middleLevel() {
        try {
            lowLevel();
            System.out.println("middle: after call");
        } finally {
            System.out.println("middle: finally");
        }
    }

    public static void main(String[] args) {
        try {
            middleLevel();
            System.out.println("main: after call");
        } catch (IllegalStateException failure) {
            System.out.println("main caught: " + failure.getMessage());
        }
        System.out.println("main continues");
    }
}
```

```bash
javac ExceptionFlowDemo.java
java ExceptionFlowDemo
```

`stdout` output:

```text
low: before throw
middle: finally
main caught: invalid state
main continues
```

Exact sequence of events:

- `lowLevel()` prints the first line and then executes `throw`, so it does not return normally.
- `middleLevel()` has no `catch`, but its `finally` block still executes during exception propagation.
- The statements `middle: after call` and `main: after call` do not run.
- `catch (IllegalStateException)` in `main` catches the error, prints the message, and lets the program continue.

If you replace `throw new IllegalStateException(...)` with an API call that throws `IllegalStateException` or another JVM operation throwing a `RuntimeException` that matches the `catch`, the handler lookup and unwinding mechanism remain the same. **The origin of the error** does not automatically determine where the error will be caught.

### Does `finally` always run?

You cannot promise it “always runs” in every circumstance. In the normal example above, `finally` runs when the method exits due to an exception. However, if the process/VM terminates abnormally, `Runtime.halt` is called, power is lost, or the environment does not allow continuation, it is not guaranteed to complete. If `finally` itself throws a new exception, the propagation result can change; do not write a `finally` block that masks the original error.

## 6. Checked exceptions: obligations when calling APIs

Whether an exception comes from a library or from application code **does not determine** whether it is checked. The classification is determined by the **inherited class type** and the catch/declaration context.

- **Checked**: for example, `IOException`. If code can throw a checked exception, the compiler requires catching it with a matching `catch` or declaring it with `throws` on the calling method (within Java's rules).
- **Unchecked**: subclasses of `RuntimeException` and `Error`. Not required to be declared in the signature or caught at the call site.
- The `throws` keyword **does not create an exception**; it declares the possibility that the method may complete abruptly with the listed exception types. `throw` is the operation that actually throws an object.

Runnable example with an API declaring `throws IOException`, even though the data read in the example does not cause an error.

Create the file **`CheckedApiDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;

public class CheckedApiDemo {
    private static String firstLine(Reader source) throws IOException {
        try (BufferedReader reader = new BufferedReader(source)) {
            return reader.readLine();
        }
    }

    public static void main(String[] args) throws IOException {
        String value = firstLine(new StringReader("hello\nworld"));
        System.out.println(value);
    }
}
```

```bash
javac CheckedApiDemo.java
java CheckedApiDemo
```

Output:

```text
hello
```

`BufferedReader.readLine()` has a signature declaring `IOException`. Therefore, `firstLine` and `main` declare `throws IOException` to satisfy checked exception rules. This run uses `StringReader` and succeeds, but **that does not remove the obligation to declare/catch the checked exception**. With a real I/O source, read errors can occur due to conditions outside the program.

You can replace `throws IOException` at the application boundary with `try/catch (IOException e)` when there is an appropriate way to respond. For resources like files/sockets/streams, prefer `try-with-resources` to close resources. If both the body and the `close()` operation throw exceptions, the try-with-resources mechanism generally preserves the primary exception and records the closing exception as a **suppressed exception**; inspect `getSuppressed()` as well when diagnosing.

## 7. Diagnosing from stack traces and API contracts

When encountering an error, a useful order of analysis is:

1. **Read the full type and message**: which type is it, and what parameter, path, index, or state does the message mention? Avoid ignoring `Caused by` and `Suppressed`.
2. **Read the stack trace from the point of origin**: inspect the top frames to find where the error was created/checked, then follow the call chain back to your own code. For wrapped errors, inspect each `cause` to find the root error.
3. **Classify the operation**: is there an explicit application `throw`, an API reporting a contract violation or resource error, or an operator/access checked by the JVM?
4. **Inspect values at the time of failure**: `null`, indices, divisors, string inputs, invariants, file/network state, or resource capacity.
5. **Fix the root cause** and decide the right place to handle it: reject invalid input early, fix logic, ensure resource cleanup, return a business error message, or escalate an operational alert.

For example, the same `NullPointerException` can require different investigation paths:

| Situation | Investigation direction |
| --- | --- |
| `customer.getName()` when `customer == null` | Trace the data path that produces/allows `null`, fix the contract and logic branch |
| `Objects.requireNonNull(config, "config")` | Check why the argument passed to the API is missing and which call violates the contract |
| Third-party API throws `NullPointerException` internally | Cross-check the contract, library version, input, and stack trace; it may be a library bug |
| `OutOfMemoryError` when calling an API | Check the API workload, data, memory limits, and JVM environment; the origin is at the actual allocation operation |

A stack trace **does not necessarily prove every deep root cause**: the JVM may optimize how it is displayed, a library may wrap errors, and runtime data may have changed before investigation. Keep appropriate logs/inputs/JDK versions to reproduce the issue.

### When actively rethrowing or wrapping errors

Preserve context using `cause` when translating a low-level error to a higher layer. Example **snippet inside a method that reads data**:

```java
try {
    loadFromStorage();
} catch (java.io.IOException failure) {
    throw new IllegalStateException("Cannot initialize data", failure);
}
```

This is an **illustrative snippet**; a real program needs a `loadFromStorage()` method declaring `throws IOException`. `IllegalStateException` is unchecked, but `failure` remains accessible via `getCause()`. Do not indiscriminately wrap across many layers with meaningless messages, or log only `failure.getMessage()` and lose the stack trace.

## 8. Common misconceptions to avoid

**“An exception created by an API is created automatically by the JVM.”** Not necessarily. A JDK method can use `throw` after checking its contract, such as `Objects.requireNonNull`. The JVM merely executes that call; classifying the origin depends on where the error condition is detected.

**“`NullPointerException` always proves there was a call on `null`.”** False. Application code or an API can explicitly throw this same class.

**“Exceptions raised by the JVM are all `Error`.”** False. `null` access, invalid array indices, or integer division by 0 typically produce `RuntimeException` classes.

**“`catch (Exception)` catches every error in Java.”** False. It does not catch `Error` such as `StackOverflowError` or `OutOfMemoryError`. Avoid catching `Throwable` broadly unless in specialized infrastructure with a clear reason.

**“If there is no `throws`, the method cannot fail.”** False. Unchecked exceptions/`Error` can occur without being declared, and unchecked exceptions documented in JavaDoc still need to be understood.

**“Having `throws IOException` guarantees an error will be thrown at runtime.”** False. It is a possibility that must be handled at compile time, not a guaranteed runtime event.

**“Once caught, the program has recovered.”** Not necessarily. Only handle and continue when state and resources still satisfy invariants. In particular, do not assume it is safe to continue after a JVM resource-exhaustion error.

**“Throwing exceptions with the same name means the same cause.”** False. The class name must be evaluated alongside the failing operation, the message, and the `cause` chain.

## 9. Self-check questions

1. **You write `throw new IllegalArgumentException("bad")` yourself. What is the origin?** Java application code.
2. **What does `Integer.parseInt("x")` raise and where?** `NumberFormatException` reported by the API because the data cannot be parsed per its contract.
3. **What does `String s = null; s.length();` raise?** The JVM may throw `NullPointerException` when evaluating the dereference operation.
4. **Are the two cases in questions 2 and 3 unchecked because both come from an API/JVM?** No. They are unchecked because they inherit from `RuntimeException`, independent of origin.
5. **Does `catch (IOException e)` catch `OutOfMemoryError`?** No; they belong to two different branches, `Exception` and `Error`.
6. **Must a method declaring `throws IOException` actually throw `IOException` on every call?** No. The signature indicates the possibility of a checked exception occurring.
7. **When you do not know whether a `NullPointerException` comes from an API or bytecode, what should you inspect?** The call site, stack trace, API contract, and actual runtime data at the time of the error.

## 10. Java 17 references

- [Java Language Specification 17 — §11.1.3 Causes of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.1.3): causes of exceptions.
- [Java Language Specification 17 — §11.2 Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): checked exception rules.
- [Java Language Specification 17 — §11.3 Run-Time Handling of an Exception](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.3): runtime propagation and handling.
- [Java SE 17 API — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): cause, stack trace, suppressed exceptions.
- [Java SE 17 API — Objects.requireNonNull](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T)): `null` checking per API contract.
- [Java SE 17 API — BufferedReader.readLine](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html#readLine()): an API with `throws IOException`.

When you understand **which operation reported the error**, **which `Throwable` type was thrown**, and **which handler receives it**, you can analyze control flow accurately and choose the right place to fix the bug.
