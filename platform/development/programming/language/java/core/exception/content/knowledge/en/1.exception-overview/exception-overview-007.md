# Prerequisites and Recommended Learning Sequence — Java Core Exception

> **Context:** Java Core → Exception → Overview. This article answers two questions: what you need to know **before learning exceptions**, and **in what order** you should learn to understand the mechanism, write proper error-handling code yourself, and progress toward designing maintainable programs. The examples use Java 17 or later.

## 1. Learning Objectives

After this learning path, learners should be able to:

1. Read a stack trace, identifying the exception type, message, origin location, and call chain.
2. Explain the execution flow when an exception is thrown: which code is skipped, where `catch` is searched for, how the stack is unwound, and the meaning of `finally`.
3. Distinguish between `Error`, checked exceptions, and unchecked exceptions; choose to catch or propagate based on **actual ability to handle**.
4. Use `try`/`catch`/`finally`, `throw`, `throws`, and try-with-resources in the right context.
5. Preserve the root cause of errors, avoid hiding errors, and place handling boundaries appropriate to each program layer.
6. Test both the success path and failure paths, especially when handling input and resources.

**Minimum starting point:** already able to write, compile, and run a Java program with methods, conditional statements, and simple classes on your own. If not yet achieved, complete Section 2 before studying Section 4.

## 2. Prerequisites: How Much Is Needed?

| Knowledge | Required Level | Self-Check Before Continuing |
| --- | --- | --- |
| Basic Java syntax, data types, variables, operators, `if/else`, loops | Required | Able to write input validation code and explain each execution branch. |
| Methods: parameters, return types, `return`, variable scope | Required | Able to trace the call chain `main() → methodA() → methodB()` and the return point of each method. |
| Classes, objects, constructors, and access modifiers | Required | Able to create a class with methods, instantiate an object, and call its methods. |
| Inheritance, `extends`, overriding, polymorphism, and the "is-a" relationship | Required before the exception hierarchy section | Able to explain why a `catch` for a superclass can catch an object of a subclass. |
| Using `javac`, `java`, file names, and `public class` | Required | Able to run standalone examples from the terminal and distinguish compile-time errors from runtime errors. |
| Call stack, sequential flow, and method call sites | Recommended from the start | Able to draw three frames when three methods are called nestedly; understand that exceptions travel in the reverse direction of calls. |
| Working with files, streams, `AutoCloseable` | Needed before try-with-resources | Know why resources like streams must be closed, even when an operation fails. |
| Unit testing with JUnit, reading logs/debugger | Learned in parallel at a later stage | Able to verify expected results and assert cases where an exception is thrown. |

**No need to learn beforehand:** multithreading, Spring, JDBC, microservice design, or the entire I/O API. Exceptions are foundational knowledge for learning those topics later.

### 2.1. Self-Assess Your Foundation with a Small Program

Save as `PrerequisiteCheck.java`:

```java
public class PrerequisiteCheck {
    public static void main(String[] args) {
        System.out.println(describe(8));
        System.out.println(describe(-3));
    }

    static String describe(int value) {
        if (value >= 0) {
            return "Không âm: " + value;
        }
        return "Âm: " + value;
    }
}
```

Run:

```bash
javac PrerequisiteCheck.java
java PrerequisiteCheck
```

Exact output:

```text
Không âm: 8
Âm: -3
```

If you cannot yet explain why the program prints these two lines, review `main`, return types, parameters, `if`, and `return`. If you are already solid on them, try drawing the stack at the moment execution is inside `describe`. The next exception lesson will use this exact relationship between calls.

## 3. Mental Model to Grasp Before Learning Syntax

In Java, an exception is an object representing an abnormal situation. When a `throw` statement executes, or when a library/JVM raises an exception, normal flow at that location stops. The runtime searches for a matching handler: starting from the current `try` block, then out to the calling methods if needed. When no handler can handle it, the exception escapes to the top of the execution thread and may terminate that thread with a stack trace.

Example call chain:

```text
main()
  └── loadProfile()
        └── parseAge()
              └── Integer.parseInt("abc")
                   → NumberFormatException
```

If `parseAge` does not catch the exception, it propagates out to `loadProfile`; if `loadProfile` also does not catch it, it continues to `main`. This is called **exception propagation** and **stack unwinding**. Code after the failing operation on the normal path does not continue running, while related cleanup blocks (such as `finally` or closing resources via try-with-resources) still execute according to their respective rules.

Do not assume "exception = system error that must always terminate the program." Many situations can be anticipated and handled at the right boundary: invalid user input, missing file, invalid request. Conversely, being able to **catch** an exception syntactically does not mean you can **recover** from it at the business level.

### 3.1. Understanding the Hierarchy Correctly

```text
Throwable
├── Error
└── Exception
    ├── RuntimeException
    │   ├── IllegalArgumentException
    │   │   └── NumberFormatException
    │   └── NullPointerException
    └── IOException
        └── FileNotFoundException
```

- **Checked exceptions:** subclasses of `Exception`, excluding `RuntimeException` and its subclasses. The compiler forces code to catch them or declare `throws`, for example `IOException`. This is a Java rule about exception types; it does not guarantee that the caller can recover on its own.
- **Unchecked exceptions:** `RuntimeException` and its subclasses; `Error` and its subclasses. The compiler does not require catching or declaring them. For example, `NumberFormatException` when a string is not a number.
- **`Error`:** usually indicates a serious environment/runtime issue (for example `OutOfMemoryError`). Normal application code should not use `catch (Error)` or `catch (Throwable)` as a catch-all rescue for every situation.

Important note: `NumberFormatException` **is an** `IllegalArgumentException`. Therefore, when using multiple `catch` blocks, the subclass branch must come before the superclass branch. Reading the inheritance relationship first will help you understand the compiler error "exception has already been caught".

## 4. Recommended Learning Sequence: From Mechanism to Design

You should follow the stages below in order. Only move to the next stage when you can complete the mini-check; the number of sessions is a suggestion and can be faster or slower depending on experience.

| Stage | Topics in Order | Must Be Able to Do Before Moving to the Next Stage |
| --- | --- | --- |
| 0 | Review conditionals, methods, objects, inheritance, call stack | Run `PrerequisiteCheck` and draw the call chain. |
| 1 | What an exception is; `Throwable`/`Exception`/`RuntimeException`/`Error`; reading a stack trace | State the error type, message, the first line related to your own code, and the error propagation path. |
| 2 | `try`, `catch`, multiple `catch` blocks, `finally`, control flow | Accurately predict the executed branch, skipped branch, and output for valid/invalid input. |
| 3 | Checked/unchecked; `throw`, `throws`; propagation across methods | Know when `throws IOException` is needed and when to throw `IllegalArgumentException`. |
| 4 | Try-with-resources, `AutoCloseable`, closing resources, suppressed exceptions | Read files/streams safely without manually closing in every branch. |
| 5 | Custom exceptions; message, cause; rethrowing and wrapping errors | Preserve the root cause when translating errors from a lower layer to a higher layer. |
| 6 | Deciding where to catch; user errors vs. programmer errors; logging | Do not swallow errors; do not use exceptions to replace normal conditional statements. |
| 7 | Testing error cases, debugging stack traces, synthesis | Write tests for normal values, invalid input, I/O errors, and resource release. |

### Stage 0 — Confirm the Foundation

Write at least one method that calls another method on your own. When the program encounters an invalid value, identify which condition produced it. Review inheritance with two parent/child classes and try passing a child object through a parent-type variable. This is direct preparation for catching exceptions by object type.

**Pass criterion:** know that `return` ends a normal call; understand that `throw` alters that flow in a different way.

### Stage 1 — Start with the Stack Trace, Then Learn the Syntax

Run an example that causes a `NumberFormatException` from `Integer.parseInt("abc")`. Observe the first line containing the exception name, message, and the `at ...` frames below. Find the first frame belonging to your own code and trace back the caller chain. The outermost location is not necessarily where the initial cause occurred, especially when an error is wrapped in another exception.

**Practice:** explain the difference between "where the error originated", "where the error was caught", and "where the message was printed". Do not learn how to hide the stack trace from the screen before understanding it.

### Stage 2 — Learn Catching Errors and Flow Through `finally`

Learn `try` with a single specific `catch`, then multiple `catch` blocks ordered from subclass to superclass; finally learn `finally`. Understand that `finally` normally runs whether an exception occurs or `return` is executed, but must not be treated as an absolute guarantee in every case such as abrupt JVM termination. Avoid `return` or throwing a new exception inside `finally` because it can mask the original result or error.

**Practice:** predict the output for the strings `"15"`, `"abc"`, and a negative number. Compare with the actual output in Section 5.1.

### Stage 3 — Separate Responsibilities: Creating, Declaring, and Handling Errors

- `throw new IllegalArgumentException("...")`: **throws an exception object** at a specific location.
- `throws IOException` in a method signature: **declares the possibility** of an exception escaping the method; by itself it does not throw an error.
- `catch (IOException e)`: handle it here when there is a sensible action, such as returning an appropriate message to the caller, adding context, or recovering with a fallback.

Checked exceptions are a compile-time constraint on an API; unchecked exceptions have no declaration constraint. Both can propagate across multiple call layers at runtime. `throws` for unchecked exceptions is optional; it can be useful to express a contract, but does not replace API documentation.

**Practice:** try removing `throws IOException` from the method reading `BufferedReader.readLine()` in Section 5.2 without adding a `catch`; explain the compile error. Do not try to "fix" it by catching and ignoring the exception.

### Stage 4 — Safe Resource Management

Learn `try (resource = ...) { ... }` with objects implementing `AutoCloseable`. Resources close when exiting the block, even if an exception occurs; if multiple resources are declared in the parentheses, they close in reverse order. If the operation inside `try` already threw an exception and closing the resource also fails, the close error is normally recorded in `getSuppressed()` instead of replacing the primary exception. An object placed into try-with-resources must follow Java's resource declaration/reference syntax rules.

**Practice:** run Section 5.2, then try replacing `StringReader` with a custom `AutoCloseable` resource to observe the close operation when the block throws an error.

### Stage 5 — Designing and Propagating Error Context

Only create a custom exception when the caller needs to distinguish a meaningful error type, for example `InvalidQuantityException`. Choose checked or unchecked based on the API contract and the caller's ability to handle it; there is no rule that "business errors are always checked" applicable to every application. When converting exceptions, use a constructor that accepts a `cause` if available, such as `new IllegalStateException("Không nạp được cấu hình", e)`, to preserve the root cause trace.

**Practice:** write a meaningfully named exception and catch that exact type in the presentation layer. Compare that with catching a generic `Exception` and displaying a message with no context.

### Stage 6 — Handling Errors at the Appropriate Boundary

A lower layer usually does not know what message the end user needs to see; the interface layer (CLI, UI, API) usually knows how to translate a failure state into an appropriate message or result. Where the error occurs should provide sufficient context; where handling is possible is where you decide to retry, prompt for re-entry, report failure, or stop.

Distinguish **common invalid input values** from **abnormal situations**: you can use an `if` condition to check for missing input before calling an API, and use exceptions to signal contract violations or execution failures. Do not use exceptions as the primary control flow for normal loops.

**Practice:** for user age input, catch `NumberFormatException` at the input layer and prompt to re-enter; do not put `System.out.println` deep inside the string-to-number conversion function and return a dummy value like `-1`.

### Stage 7 — Testing and Reading Errors in Real Scenarios

For every function that can fail, prepare at least one success path and meaningful failure cases. In JUnit 5, `assertThrows(IllegalArgumentException.class, () -> method(...))` is usually suitable for asserting exceptions; also check the message/cause when they are part of the contract. Verify that resources are closed on both success and failure paths. Use a debugger or stack trace to pinpoint where the issue occurred; log errors **intentionally** at the handling boundary, avoiding duplicate logging of the same stack trace across multiple layers.

**Completion criterion:** able to explain to someone else not only *what exception occurred*, but also *why it was caught at that location*, *what the caller received*, and *how resources were released*.

## 5. Two Standalone Java 17 Practice Programs

The two programs are designed to be studied in sequence: first, unchecked exceptions and selecting a `catch` branch; next, checked exceptions and resource lifecycle. Each `java` code fence is a standalone file, saved with the exact name shown at the start of the section.

### 5.1. Catching Specific Exceptions and Understanding Inheritance

Save as `FirstExceptions.java`:

```java
public class FirstExceptions {
    public static void main(String[] args) {
        for (String input : new String[] {"12", "x", "-5"}) {
            try {
                int age = parseAge(input);
                System.out.println("OK: " + age);
            } catch (NumberFormatException e) {
                System.out.println("Không phải số: " + input);
            } catch (IllegalArgumentException e) {
                System.out.println("Tuổi âm: " + input);
            }
        }
    }

    static int parseAge(String text) {
        int age = Integer.parseInt(text);
        if (age < 0) {
            throw new IllegalArgumentException("Tuổi không hợp lệ");
        }
        return age;
    }
}
```

Run:

```bash
javac -encoding UTF-8 FirstExceptions.java
java FirstExceptions
```

Stdout:

```text
OK: 12
Không phải số: x
Tuổi âm: -5
```

Explanation: `"12"` is parsed and returned normally; `"x"` causes `Integer.parseInt` to throw `NumberFormatException`; `"-5"` parses successfully and is then rejected by the business check with `IllegalArgumentException`. Because `NumberFormatException extends IllegalArgumentException`, the narrower catch branch must be placed before the broader branch. Swapping the two branches will cause a compile error because the narrower branch becomes unreachable.

**Progressive exercise:** add the input `"0"`; change the condition to `age <= 0` and predict the output; add a call `parseAge(null)` and analyze the actual exception. Do not assume that every `null` value causes `NullPointerException`: behavior depends on the API being called.

### 5.2. Checked Exceptions and try-with-resources

Save as `ResourceExample.java`:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public class ResourceExample {
    public static void main(String[] args) {
        try {
            System.out.println(firstLine("Java\nException"));
        } catch (IOException e) {
            System.out.println("Lỗi đọc: " + e.getMessage());
        }
    }

    static String firstLine(String text) throws IOException {
        try (BufferedReader reader =
                     new BufferedReader(new StringReader(text))) {
            return reader.readLine();
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 ResourceExample.java
java ResourceExample
```

Stdout:

```text
Java
```

`BufferedReader.readLine()` declares that it can throw `IOException`. Therefore `firstLine` declares `throws IOException` and `main` catches that type, even though the specific in-memory input in this example reads successfully. Try-with-resources closes `BufferedReader` when exiting the block; with real streams/files, proper closing prevents resource leaks.

**Progressive exercise:** replace the content with an empty string and predict the return value; add a simple `AutoCloseable` that prints a message in `close()` to observe the closing order. If you replace it with `FileReader`, you must consider the file path/existence and encoding, and not use the stdout of the in-memory example as a prediction for a real file environment.

## 6. Suggested Practice Study Schedule

For someone already solid on core Java, this can be divided into **five sessions**, each dedicating one part to reading, one part to writing/triggering errors, and one part to explaining it back:

| Session | Focus | Verification Deliverable |
| --- | --- | --- |
| 1 | Review call stack, `Throwable` hierarchy, creating errors, and reading stack traces | Diagram of a 3-level call chain; explanation of 1 stack trace of your own. |
| 2 | `try`, `catch`, `finally`, checked and unchecked | Run `FirstExceptions`; predict output before running. |
| 3 | `throw`, `throws`, propagation; handling errors by caller responsibility | Write 2–3 methods calling one another and decide where to catch with justification. |
| 4 | Try-with-resources, resources, suppressed exceptions | Run `ResourceExample`; demonstrate that the resource closes when an error occurs. |
| 5 | Custom exceptions, cause, catch boundaries, testing | Complete the synthesis exercise in Section 7 and explain every handling decision. |

If you do not yet know inheritance or methods, add one to two foundational sessions before Session 1. If you have already used exceptions in projects, you should still check Stages 1, 4, and 6 because reading stack traces, preserving cause, and resource lifecycles are skills easily overlooked.

## 7. Synthesis Exercise to Confirm True Understanding

**Prompt:** write a program that receives a list of strings representing order quantities. The program attempts to convert each string into a positive integer and prints the result for each element. For unparseable strings or invalid numbers, state the specific error and continue to the next element. The conversion part should be an independent method that does not print to the console itself.

Implementation requirements:

1. Write `parseQuantity(String text)` returning `int`; use `Integer.parseInt` and `throw new IllegalArgumentException(...)` for non-positive numbers.
2. In `main`, catch `NumberFormatException` and `IllegalArgumentException` separately in the right order; do not use `catch (Exception e)` to ignore all errors.
3. Test with `"3"`, `"0"`, `"-2"`, `"abc"`. Only `"3"` is accepted input.
4. Add a function that reads data through `BufferedReader` in try-with-resources, declaring/catching `IOException` appropriately.
5. Explain verbally which methods the code passes through before reaching `catch` if an error occurs inside the conversion function.
6. Verify that unexpected exceptions are not silently swallowed, and that messages displayed to users do not expose sensitive data.

No framework is needed to complete this exercise. Once you can do it, you have the foundation to learn exception handling in real-world I/O, Java libraries, and frameworks.

## 8. Common Learning Pitfalls and How to Fix Them

| Misconception | What to Remember |
| --- | --- |
| "Every exception must be caught (`catch`) right where it occurs." | Only catch when the current layer has an appropriate way to handle it. Otherwise, propagate it outward and preserve context. |
| "`throws` creates an exception by itself." | `throws` declares a contract; `throw` is the statement that actually throws an exception object. |
| "Checked means more severe than unchecked." | That is a compiler-enforced classification, not a severity scale. |
| "`finally` always runs in every situation." | It normally runs under Java's control-flow rules, but the JVM/process can terminate abnormally. |
| "`catch (Exception e) {}` makes the application safe." | Catching and ignoring loses error signals, making corrupted data or wrong behavior hard to detect. |
| "Printing `e.getMessage()` is enough for debugging." | A message does not always contain the full call chain or root cause; keep the stack trace and appropriate cause. |
| "Number parsing errors are `IOException`." | `Integer.parseInt` throws `NumberFormatException` (unchecked); errors reading from a source may be `IOException` (checked). |
| "Always use custom exceptions for every case." | Only add a new type when there is clear semantics or a distinct handling need. |
| "Catch `RuntimeException`/`Throwable` everywhere to avoid crashes." | Can hide programmer errors or system errors. Only use broad handlers at carefully considered boundaries. |
| "Closing a stream at the end of a method is enough." | If an operation fails midway, the end block may be skipped; prefer try-with-resources. |
| "After `throw`, subsequent statements on the same path still run." | A `throw` statement transfers control abnormally; normal execution does not continue from that point. |

## 9. Learning Path Completion Checklist

Mark yourself **passed** when you can answer and perform the following without looking at the documentation:

- [ ] Run both Java 17 programs in this article on your own and explain stdout line by line.
- [ ] Draw a caller chain and state accurately where the exception is thrown, propagated, and caught.
- [ ] Explain why catching a superclass before a subclass can cause a compile error.
- [ ] Distinguish `Error`, checked exceptions, and unchecked exceptions with accurate examples.
- [ ] Write `try`/`catch`/`finally`, `throw`, and `throws` correctly; state the distinct role of each construct.
- [ ] Avoid empty `catch` blocks or turning every error into a dummy value without an explicit contract.
- [ ] Use try-with-resources for resources that must be closed and understand that errors raised during closing can be suppressed.
- [ ] When wrapping an exception, preserve `cause` rather than keeping only the message text.
- [ ] Know why each type of error is caught at the current layer or propagated to the caller.
- [ ] Test both success and failure cases, then read the stack trace to find the root cause.

**After this learning path:** move on to topics that apply exceptions concretely (Java I/O/NIO, data processing, APIs, concurrent programming), where the principles above are used with real error sources and resources.