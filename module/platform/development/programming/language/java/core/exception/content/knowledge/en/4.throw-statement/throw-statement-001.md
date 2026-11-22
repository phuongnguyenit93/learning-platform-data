# `throw` Syntax and `Throwable` Type Requirement in Java

> **Scope:** Java Core → Exception → The `throw` statement. The `throw` statement is used to **throw an object representing an error or an exceptional situation**, causing the execution flow to leave the normal path. In Java, the expression after `throw` must have a type compatible with `java.lang.Throwable`; compile-time type checking is different from determining which object is actually thrown at runtime.

## 1. Standard `throw` Syntax

General form:

```java
throw expression;
```

Where:

- `throw` is a Java keyword.
- `expression` must be an expression of a reference type assignable to `Throwable` (including the `null` expression case; see Section 7).
- The semicolon `;` terminates the **statement**.
- At runtime, the expression is evaluated, and then the corresponding `Throwable` object is thrown. If the resulting value is `null`, the JVM throws a `NullPointerException` instead.
- `throw` is a **statement**, not an operator that returns a value or a regular expression.

Most common way to write it:

```java
throw new IllegalArgumentException("Số lượng phải lớn hơn 0");
```

`new IllegalArgumentException(...)` creates the exception object; `throw` throws that object. Simply instantiating an exception without throwing it does not transfer the execution flow to the error-handling path:

```java
new IllegalArgumentException("Giá trị không hợp lệ"); // Only creates the object.
```

**First takeaway:** `throw` is not a function call that returns a special value. It is a statement that controls execution flow using a `Throwable`.

### 1.1. Valid Forms

The following snippets are **illustrative code fragments inside a method**, not standalone programs:

```java
// Create and throw an unchecked exception.
throw new IllegalArgumentException("Sai tham số");
```

```java
// Throw an existing exception object (the method must declare/catch it if checked).
java.io.IOException cause = new java.io.IOException("Lỗi đọc");
throw cause;
```

```java
// Use a conditional expression to produce one of two RuntimeExceptions.
throw invalidInput
        ? new IllegalArgumentException("Dữ liệu sai")
        : new IllegalStateException("Trạng thái sai");
```

The third snippet assumes `invalidInput` has been declared as a `boolean`. The entire conditional expression returns an object compatible with `Throwable`. However, `throw` itself is still a **statement**; it cannot be placed arbitrarily as a value-returning branch of the `?:` operator.

Invalid example:

```java
// INVALID: throw is a statement, not an expression in the ?: operator.
// int value = condition ? 10 : throw new IllegalArgumentException();
```

The correct way to express this is to use `if`/`throw` and then return a valid value in the remaining branch.

### 1.2. `throw` Is Not `throws`

| Criterion | `throw` | `throws` |
| --- | --- | --- |
| Position | Inside a method body, constructor, or appropriate block | In a method or constructor declaration |
| Role | Actually throws a `Throwable` object | Declares the exception types that may escape, especially checked exceptions |
| Form | `throw new IOException("...");` | `void read() throws IOException { ... }` |
| Number of objects/types | Each statement throws one `Throwable` value during that execution | Can list multiple types separated by commas |
| Effect on control flow | Stops the normal execution path at that point | Does not throw any object by itself |
| Can be used together? | Yes | Yes; a method can `throw` a checked exception and declare the corresponding `throws` |

Illustrative method example:

```java
static void requireData(String data) throws java.io.IOException {
    if (data == null) {
        throw new java.io.IOException("Thiếu dữ liệu");
    }
}
```

`throws IOException` informs the caller of the obligation to handle/declare; `throw new IOException(...)` is what actually raises the exception when `data == null`. Choosing `IOException` in the example is meant to express a data error from an I/O source; for pure input parameter validation, `IllegalArgumentException` or `NullPointerException` may be more semantically accurate.

## 2. Why Must It Be Compatible with `Throwable`?

Java defines the inheritance hierarchy of objects that can be thrown via `throw`:

```text
java.lang.Object
└── java.lang.Throwable
    ├── java.lang.Exception
    │   ├── java.io.IOException
    │   └── java.lang.RuntimeException
    │       ├── IllegalArgumentException
    │       ├── NullPointerException
    │       └── IllegalStateException
    └── java.lang.Error
        ├── AssertionError
        ├── LinkageError
        └── VirtualMachineError
```

This is a representative part of the hierarchy, not an exhaustive list.

- `Throwable` is the common superclass of `Exception` and `Error`.
- `Exception` is the branch commonly used for exceptional situations in a program.
- `RuntimeException extends Exception`: these exceptions are **unchecked**.
- `Error extends Throwable`: also unchecked, but normally should not be created/caught to model business errors.
- It is possible to create a class that `extends Throwable` directly; Java allows this syntactically, but in practice `Exception` or `RuntimeException` is usually chosen for application APIs.

Requiring the type to be `Throwable` ensures that the `throw`/`catch` mechanism works with objects that have `Throwable` characteristics, such as an error message, cause, stack trace, suppressed exceptions, and a clear type hierarchy. It also helps the compiler enforce the checked exception contract.

### 2.1. What Can the `throw` Expression Be?

A valid expression can take the form of:

- `new SomeException(...)` — create and throw immediately.
- `throw e;` — throw a variable referencing an exception.
- `throw createException();` — throw the return value from a method of a compatible type.
- `throw condition ? exceptionA : exceptionB;` — throw the result of a conditional expression of a compatible type.
- `throw null;` — syntactically valid, but throws `NullPointerException` at runtime; not a recommended practice.

The type examined at compile time is the **static type of the expression**; the concrete object thrown at runtime carries the actual runtime type, which determines which `catch` matches.

## 3. Runnable Java 17 Example: Validating Input with `throw`

Create the file `ThrowBasicDemo.java`:

```java
public class ThrowBasicDemo {
    static int requirePositive(int value) {
        if (value <= 0) {
            throw new IllegalArgumentException("Giá trị phải dương");
        }
        return value;
    }

    public static void main(String[] args) {
        for (int input : new int[] {5, 0, -2}) {
            try {
                int result = requirePositive(input);
                System.out.println("OK: " + result);
            } catch (IllegalArgumentException e) {
                System.out.println("Lỗi " + input + ": " + e.getMessage());
            }
        }
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac -encoding UTF-8 ThrowBasicDemo.java
java ThrowBasicDemo
```

Exact stdout:

```text
OK: 5
Lỗi 0: Giá trị phải dương
Lỗi -2: Giá trị phải dương
```

**Execution path for each input:**

1. `5`: the condition `value <= 0` is false, returns `5` and prints `OK: 5`.
2. `0`: creates `IllegalArgumentException` and throws it with `throw`; the `return value` statement does not execute. The `catch` in `main` receives the object and prints the message.
3. `-2`: similar to `0`; the loop continues after the `catch` completes.

An exception **does not automatically terminate the entire JVM**. It alters the execution flow; it can be handled in the caller, propagated further, or if unhandled, can cause the thread to terminate abnormally.

### 3.1. Why Use `IllegalArgumentException`?

The `requirePositive` method has a precondition that the parameter must be positive. `IllegalArgumentException` clearly expresses that the caller passed data violating the contract, and it is an unchecked exception so it does not require declaring `throws`. If invalid input is an expected, frequent state (such as form validation), an API returning a structured validation result may also be appropriate. Which approach to choose is a design decision, not a requirement of the `throw` syntax.

## 4. Invalid Types After `throw`

The following examples are **intentionally wrong to explain the rules**, not for use in a runnable Java file:

```java
throw "Không hợp lệ";           // Invalid: String does not extend Throwable.
throw 123;                     // Invalid: int is a primitive.
throw new Object();            // Invalid: Object is not a Throwable.
throw System.out.println("x"); // Invalid: println() returns void.
```

You cannot simply have the word `Error`/`Exception` in text and turn it into an exception. You need an **actual object of type `Throwable`** or a valid expression of a compatible type.

For example, if you want to report an error from a string, write:

```java
throw new IllegalStateException("Không hợp lệ");
```

Java has no mechanism to convert any `Object` into a `Throwable` by casting. Trying `(Throwable) new Object()` may pass type checking in some contexts if a reference cast is permitted, but at runtime it will fail because the object is not a `Throwable`; you should not use casting to bypass the type requirement.

### 4.1. Static Type Matters Even When the Runtime Object Is Valid

Illustrative snippet below:

```java
Object problem = new IllegalArgumentException("Dữ liệu sai");
// throw problem; // Does not compile: static type Object is not assignable to Throwable.
```

It is the same object, but held in a variable of type `Object`. To throw it, you need to narrow the type validly, for example:

```java
Object problem = new IllegalArgumentException("Dữ liệu sai");
if (problem instanceof Throwable failure) {
    throw failure; // Static type Throwable: checked exception rules still apply.
}
```

The snippet above is **not a complete program**. `failure` has static type `Throwable`, so the method containing it must normally catch or declare `throws Throwable`, even though the concrete object at runtime is `IllegalArgumentException`. You should not overuse `throws Throwable` just to accommodate an overly general variable; if you know for sure that only unchecked exceptions are thrown, you should express the `RuntimeException` type directly in the contract.

### 4.2. `Throwable` Is a Reference Type, Not a String/Error Code

`throw` does not accept an error code `404`, text `"not found"`, or a `false` value like some other languages. You can put that data inside the exception (message, field, status code), but the object thrown must still be a `Throwable`.

## 5. How Do Checked and Unchecked Exceptions Affect `throw`?

Separate this into two steps:

1. **Type check:** the expression after `throw` must have a type compatible with `Throwable`.
2. **Checked exception check:** if the exception that can escape is checked, the code must catch or declare it appropriately.

These two conditions are independent. An expression with a valid `Throwable` type can still be rejected by the compiler if a checked exception is not handled.

| Thrown Type | In the Throwable hierarchy? | Checked/unchecked | Must `catch` or `throws` when escaping a method? |
| --- | --- | --- | --- |
| `IOException` | Yes | Checked | Yes |
| `Exception` | Yes | Checked | Yes |
| `Throwable` | Yes | Checked | Yes |
| `IllegalArgumentException` | Yes | Unchecked (`RuntimeException`) | Not required |
| `NullPointerException` | Yes | Unchecked (`RuntimeException`) | Not required |
| `AssertionError` | Yes | Unchecked (`Error`) | Not required |
| `String` | No | Not applicable | Cannot `throw` directly |

**Rule:** subclasses of `RuntimeException` and `Error` are unchecked. Other subclasses of `Throwable` are checked according to the Java language system. Therefore, you cannot equate `Exception` with all checked exceptions or `Throwable` with an unchecked type.

### 5.1. Invalid Example Due to an Unhandled Checked Exception

In a method that **does not declare `throws`** and has no matching handler:

```java
static void fail() {
    throw new java.io.IOException("Không đọc được");
}
```

The snippet above does not compile because `IOException` is a checked exception. The compiler message typically reads like “unreported exception IOException; must be caught or declared to be thrown”.

Two valid ways to handle it:

**Option A — declare for the caller:**

```java
static void fail() throws java.io.IOException {
    throw new java.io.IOException("Không đọc được");
}
```

**Option B — catch where it can be handled:**

```java
static void fail() {
    try {
        throw new java.io.IOException("Không đọc được");
    } catch (java.io.IOException e) {
        System.out.println("Đã xử lý: " + e.getMessage());
    }
}
```

Both snippets are examples inside a class body, not standalone files. In real handling, do not catch a checked exception and stay silent if there is no recovery path; the caller might think the operation succeeded.

### 5.2. `throws` Is Not a Guarantee of “Only This Exception”

`static void process() throws IOException` indicates that the method may let an `IOException` escape. It does not forbid an `IllegalArgumentException`, `NullPointerException`, or `Error` from occurring at runtime. Nor does `throws` guarantee that the method will definitely throw an exception.

Similarly, writing `throw new RuntimeException("...")` does not require `throws RuntimeException`; declaring unchecked exceptions is optional and Javadoc `@throws` is often used to express the contract more clearly.

## 6. Java 17 Program: Throwing a Checked Exception and Handling It in the Caller

The example uses `BufferedReader` on in-memory data to avoid file dependencies while still demonstrating a reading API capable of throwing `IOException`. When there is no line, the method proactively throws `EOFException` (a checked subclass of `IOException`).

Create the file `ThrowCheckedDemo.java`:

```java
import java.io.BufferedReader;
import java.io.EOFException;
import java.io.IOException;
import java.io.StringReader;

public class ThrowCheckedDemo {
    static String requireFirstLine(String content) throws IOException {
        try (BufferedReader reader =
                     new BufferedReader(new StringReader(content))) {
            String line = reader.readLine();
            if (line == null) {
                throw new EOFException("Không có dòng dữ liệu");
            }
            return line;
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println("Dòng đầu: "
                    + requireFirstLine("Java\nException"));
            System.out.println("Dòng đầu: " + requireFirstLine(""));
        } catch (EOFException e) {
            System.out.println("Hết dữ liệu: " + e.getMessage());
        } catch (IOException e) {
            System.out.println("Lỗi I/O: " + e.getMessage());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 ThrowCheckedDemo.java
java ThrowCheckedDemo
```

Exact stdout:

```text
Dòng đầu: Java
Hết dữ liệu: Không có dòng dữ liệu
```

Explanation:

- `readLine()` returns `"Java"` when there is a first line; the method `return`s normally.
- For an empty string, `readLine()` returns `null`; `throw new EOFException(...)` executes. `EOFException` is a checked exception, so it must be caught or declared when escaping the method.
- `requireFirstLine` declares `throws IOException`, which covers `EOFException` because it is a subclass of `IOException`.
- `main` has `catch (EOFException e)` before `catch (IOException e)`. If the order were reversed, the handler for `EOFException` would be unreachable and the program would not compile.
- When `EOFException` is thrown, the `return line` statement is skipped. Try-with-resources closes `reader` when leaving the block.
- The data in the example is in-memory; in a real file case, additional unexpected environment errors may occur.

Note: in practice, EOF is a normal result of many reading APIs and does not always need to throw an exception. Here we **proactively define a contract** of “there must be at least one line”, so having no line is treated as a failure that needs to be reported.

## 7. Extended Cases — Recognizing Essential Rules

The cases below help learners apply the **`throw` syntax** without repeating all the full demonstration programs from the dedicated lessons on `throw null`, rethrow, unreachable code, and `switch`.

### 7.1. Throwing a null Reference

```java
throw null; // Compiles validly; throws NullPointerException at runtime.
```

The `null` value is not a `Throwable` object. If the expression evaluates to `null`, the JVM throws a `NullPointerException`. A variable of type `RuntimeException` can still hold `null`; business code should create an exception with a clear message instead of intentionally using `throw null`.

### 7.2. Rethrowing or Wrapping Errors

```java
try {
    loadSettings();
} catch (java.io.IOException e) {
    throw new IllegalStateException("Không tải được cấu hình", e);
}
```

This is an illustrative snippet, where `loadSettings` is defined in the application. `throw e;` rethrows the **same object** that was caught; `throw new ...(..., e)` creates a new exception with `e` as the cause. Rethrowing a checked exception follows `catch-or-declare`, with the `precise rethrow` rule in certain effectively final `catch` blocks.

### 7.3. After `throw` and in `switch`

```java
if (quantity <= 0) {
    throw new IllegalArgumentException("quantity must be positive");
}
System.out.println("valid");
```

This is an illustrative snippet with `quantity` already declared. `throw` does not complete normally: a statement immediately following an unconditional `throw` **in the same block** is unreachable, whereas the path outside the `if` branch can still execute. In Java 17, a `switch` expression also allows a branch `default -> throw new IllegalArgumentException(...)` alongside branches that provide a value or `yield`; `throw` is still a statement, not a value-returning expression.

### 7.4. Broader Context

`throw` can appear in a constructor, a lambda block body, a loop, or when defining a custom error with appropriate syntax; the thrown exception must still belong to the `Throwable` hierarchy, and checked exceptions are also subject to method/functional interface signature constraints. Business exceptions are usually defined by extending `Exception` or `RuntimeException`, not by misusing `Error`. `finally`/`try-with-resources` performs cleanup according to contract, but **does not automatically roll back** modified data.

This section is a syntax map. Dedicated lessons in the chapter analyze identity, stack trace, null semantics, reachability according to the JLS, and `yield` in `switch` through in-depth examples, avoiding repeating those walkthroughs here.

## 8. Common Mistakes When Using `throw`

| Mistake or Misconception | Cause | How to Fix |
| --- | --- | --- |
| `throw "Lỗi";` | `String` is not a `Throwable`. | `throw new IllegalArgumentException("Lỗi");` or an appropriate type. |
| `throw new Object();` | `Object` is not compatible with `Throwable`. | Use an exception belonging to the `Throwable` hierarchy. |
| `throw new IOException(...);` without handling checked | The compiler requires catching or declaring it. | Add `throws IOException` or `catch` at the right layer. |
| Thinking `throws IOException` raises an error by itself | `throws` only declares; it does not execute. | Use `throw` when the failure condition occurs. |
| Creating `new Exception(...)` without `throw` | Only creates the object. | Write `throw new Exception(...)` and handle the checked exception. |
| `throw null;` to report missing data | Runtime throws `NullPointerException` instead, which is confusing. | Proactively create a meaningful exception. |
| `Throwable x = new RuntimeException(...); throw x;` and being surprised by having to declare it | The static type `Throwable` is checked as a checked exception. | Use a reasonably narrow type; understand precise rethrow when catching. |
| Catching an error and doing `throw new RuntimeException(e.getMessage())` | Loses the cause/error chain. | Use the constructor that accepts `cause` when wrapping errors. |
| Placing code unconditionally after `throw` | The code is unreachable. | Use `if` and arrange control flow clearly. |
| Thinking `throw` will roll back | Java does not automatically undo all side effects. | Design state contracts, validate beforehand, or use appropriate transactions. |
| `catch (Exception)` to catch a self-thrown `Error` | `Error` does not inherit from `Exception`. | Understand the `Throwable` hierarchy; do not catch broadly indiscriminately. |
| Using exceptions to control every normal branch | Code becomes hard to read and real errors are hard to distinguish. | Use normal conditions/results for situations that can be expressed simply. |

### 8.1. Mistakes with Filenames, Imports, and Output

- `public class ThrowBasicDemo` must be in `ThrowBasicDemo.java`. Java filenames are case-sensitive on corresponding systems.
- `java.lang.RuntimeException`, `IllegalArgumentException`, and `Throwable` are automatically imported from `java.lang`; `IOException` and `EOFException` belong to `java.io`, so the example has `import` statements.
- The stack trace of an uncaught exception is normally printed to **stderr**, with line numbers depending on the file version. All stdouts recorded in this lesson come from programs that proactively caught errors and printed stable output.
- Code marked “illustrative” may rely on variables, methods, or enclosing classes not provided. Only the programs with filenames, `public class`, and `main` in Sections 3 and 6 are standalone compilable/runnable examples.

## 9. Exercises with Guided Answers

### Exercise 1 — Choose Valid `throw` Statements

Evaluate:

```java
throw new RuntimeException("A");
throw new java.io.IOException("B");
throw new Throwable("C");
throw null;
throw "D";
```

The lines are understood **independently**, not written sequentially in the same block as a complete program.

- `new RuntimeException`: valid type, unchecked, does not require `throws`.
- `new IOException`: valid type, but checked; must be caught/declared if escaping.
- `new Throwable`: valid type, but checked; must be caught/declared if escaping.
- `throw null`: valid syntax; throws `NullPointerException` at runtime.
- `throw "D"`: invalid because type `String` is not compatible with `Throwable`.

### Exercise 2 — Predict the Output

In `ThrowBasicDemo`, append `7` to the end of the array. The result will add the line `OK: 7` after the existing lines. If you replace `catch (IllegalArgumentException)` with `catch (Exception)`, the errors thrown in the example are still caught, but the handler type is broader and can easily mask unintended error types.

### Exercise 3 — Wide-Type Variable

Given:

```java
Object value = new IllegalStateException("Sai");
```

Why does `throw value;` not compile? Because the static type of `value` is `Object`, which does not satisfy the type constraint of `throw`. If you use pattern matching `instanceof Throwable error` and then `throw error`, why is there still a checked obligation? Because the variable `error` has static type `Throwable`.

### Exercise 4 — Difference Between `throw e` and Wrapping a Cause

In `ThrowCauseDemo`, try replacing:

```java
throw new ConfigurationException("Cổng không hợp lệ", e);
```

with `throw e;`. The `loadPort` method may still compile because `NumberFormatException` is unchecked, but the contract/information that `main` expects will change: the `catch (ConfigurationException)` handler can no longer catch the original exception. Designing wrapper types needs to be consistent with the caller's contract.

### Exercise 5 — Testing the Error Path

Write a method `parseAge(String input)`:

1. If the string is not an integer, let `NumberFormatException` propagate up.
2. If it parses but the value is outside a valid range you define, `throw new IllegalArgumentException(...)`.
3. If valid, return `int`.
4. From `main`, test valid strings, letters, negative numbers, and values exceeding the `int` range.
5. Verify that the method does not modify shared state before throwing an exception, and clearly document the contract of each error type.

## 10. Checklist Before Using `throw` in an API

- [ ] Does the expression after `throw` have a static type compatible with `Throwable`?
- [ ] Do you understand that a `null` value here produces `NullPointerException` at runtime?
- [ ] Have you distinguished the executing `throw` from the declaring `throws`?
- [ ] Have you determined whether the exception is checked or unchecked and the caller's obligation?
- [ ] Have you chosen an exception that expresses the right semantics, instead of misusing `Error`?
- [ ] If rethrowing an exception, is the necessary error information preserved?
- [ ] If wrapping an exception, is the original cause passed via `cause`?
- [ ] Does code after `throw` have a valid execution path, or has it accidentally become unreachable?
- [ ] Are resources that need closing and state modified before `throw` handled according to contract?
- [ ] Have you tested both the success path and the error-throwing path, including the exception type and post-error state?
- [ ] Have you determined the appropriate `catch` location that can handle it?

**Remember:** `throw expression;` throws a value compatible with `Throwable` and abnormally terminates the current execution path. The `throws` signature and the checked exception mechanism determine compile-time obligations; the runtime hierarchy determines the `catch` handler; while modified data and resources needing cleanup must be designed separately — they do not automatically undo themselves just because of `throw`.