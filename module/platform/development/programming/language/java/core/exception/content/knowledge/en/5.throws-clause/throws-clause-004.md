# Distinguishing `throw` vs `throws` in Java

> **Topic:** Java Core → Exception → The `throws` Clause. These two keywords have similar names, but they perform **two different jobs**: `throw` is **the statement that actually throws an exception object**; `throws` is **the clause in a method/constructor declaration** that indicates which exception types can propagate out, specifically to satisfy the compiler's **checked exception** rules. Understanding this difference helps you read Java APIs accurately, understand how exceptions propagate, and design clear error-handling contracts.

## 1. Seeing the Difference Immediately Through Syntax

```java
// Executable statement inside a method body:
throw new IllegalArgumentException("Giá trị không hợp lệ");

// Clause in a method signature:
static void read() throws java.io.IOException {
    // Method body.
}
```

The two snippets above only illustrate syntax; they are not a standalone program. Key distinctions:

- **`throw expression;`** evaluates an expression whose type is compatible with `Throwable` and throws that object at the current execution point. It causes execution to terminate abnormally unless the exception is caught in an appropriate scope.
- **`throws ExceptionType1, ExceptionType2`** appears after the parameter list and before the method body (or before `;` for a declaration without a body). This is part of the **declaration**; by itself, it does not create or throw any object.

Notably: a method can have `throws` while **never executing a `throw` statement directly**; the exception can come from a callee method. Conversely, a method can use `throw` with an unchecked exception **without needing `throws`**.

### 1.1. Core Comparison Table

| Criterion | `throw` | `throws` |
| --- | --- | --- |
| Nature | Control-flow statement | Component of a declaration signature |
| Placement | Inside a method body, constructor, lambda block, or a context that allows statements | After the parameter list of a method/constructor and before the body or `;` |
| Syntax | `throw new IOException("Lỗi");` | `void load() throws IOException, SQLException` |
| Followed by | **An expression** whose type is compatible with `Throwable` | **A list of one or more exception types** that are subclasses of `Throwable` |
| Actually throws? | Yes, when the statement is executed | No |
| Effect on the program | Directs execution down the exception path; normal statements after the throw point do not run | Helps determine the caller's compile-time obligation for checked exceptions |
| Always written together? | No | No |
| Checked/unchecked | Can throw both | Checked exceptions must be caught or declared if they can escape; unchecked exceptions do not require declaration |

**Mnemonic:** `throw` answers "**what to throw, and when?**"; `throws` answers "**which error types can this method let escape for the caller to handle?**".

## 2. How Does `throw` Work?

General syntax:

```java
throw expression;
```

`expression` must have a type convertible to `java.lang.Throwable` according to the language rules. For example:

```java
throw new IllegalArgumentException("Số lượng âm");
```

What happens:

1. An `IllegalArgumentException` object is created.
2. The `new ...` expression written after `throw` is evaluated.
3. That object is thrown; normal execution from this statement stops.
4. Java searches for a compatible `catch` in active `try` blocks; if none exists, the error propagates outward along the call stack.

Do not confuse **instantiation** with **throwing**:

```java
new IllegalArgumentException("Lỗi");       // Only creates the object.
throw new IllegalArgumentException("Lỗi"); // Creates and actually throws it.
```

These are separate illustrative lines. The first line does not cause the program to enter `catch`; if no reference remains, the object can be garbage-collected like any other object. The second line alters control flow.

### 2.1. Which Types Are Allowed After `throw`?

```text
java.lang.Throwable
├── java.lang.Exception
│   ├── java.io.IOException
│   └── java.lang.RuntimeException
│       ├── IllegalArgumentException
│       ├── IllegalStateException
│       └── NumberFormatException
└── java.lang.Error
    ├── AssertionError
    └── LinkageError
```

`Throwable` is the root of the exception hierarchy; both `Exception` and `Error` are subclasses. The `throw` statement can throw objects from these branches as a matter of language syntax, but normal applications **should not use `Error` as a business exception**.

The following expressions have invalid types:

```java
// EXAMPLES INTENTIONALLY FAILING TO COMPILE:
throw 42;              // int is not a Throwable.
throw "Có lỗi";        // String is not a Throwable.
throw new Object();    // Object is not a Throwable.
```

Valid example:

```java
throw new IllegalArgumentException("Số không hợp lệ");
```

`throw null;` is a special case: Java allows the syntax, but if the expression after `throw` evaluates to `null`, the runtime throws a `NullPointerException` instead. This is not a good error-reporting technique; you should create an exception that clearly expresses the cause.

### 2.2. Static Variable Type vs. Actual Runtime Object Type

Suppose:

```java
Object error = new IllegalStateException("Trạng thái sai");
// throw error; // Invalid because the static type Object is not a Throwable.
```

Even though the underlying object is `IllegalStateException`, the type of the **expression** `error` is `Object`, so the compiler does not allow `throw error`.

If a variable is declared as `Throwable error`, `throw error` satisfies the **type requirement of the `throw` statement**, but it may require `throws Throwable` or a `catch` because the compiler treats it as checked at the broad `Throwable` type. Distinguishing type checking from checked exception rules is an important point in the sections that follow.

### 2.3. `throw` Is Not Synonymous With `return`

`return` completes normally and can return a value. `throw` terminates abnormally and does not return a value of the method's return type. For example:

```java
static int divide(int a, int b) {
    if (b == 0) {
        throw new ArithmeticException("Không thể chia cho 0");
    }
    return a / b;
}
```

This is an illustrative method and must be placed inside a class. The `b == 0` branch does not execute `return a / b`. In Java, placing an executable statement immediately after an **unconditional** `throw` in the same block causes an "unreachable statement" error.

## 3. How Does `throws` Work?

General syntax:

```java
ReturnType methodName(Parameters...) throws ExceptionType1, ExceptionType2 {
    // Body.
}
```

The `throws` clause is written in the **declaration** of a method or constructor; the names that follow are **`Throwable` types**, not `new Exception(...)` objects. You cannot write `throws new IOException("...")`.

Example of a reading method:

```java
static String readFirstLine(java.io.BufferedReader reader)
        throws java.io.IOException {
    return reader.readLine();
}
```

This method **has no `throw` statement**. However, `reader.readLine()` can throw `IOException`, and the method allows that exception to propagate to the caller, so declaring `throws IOException` is appropriate. If the caller does not handle or further declare this checked exception, the compiler reports an error.

### 3.1. `throws` Is Part of the Contract, Not an Executable Statement

Look at:

```java
static void maybeFail(boolean failed) throws java.io.IOException {
    if (failed) {
        throw new java.io.IOException("Không thể đọc");
    }
}
```

On every call, `throws IOException` remains in the signature. Yet only when `failed == true` is the `throw` statement executed. When `failed == false`, the method completes normally. **No exception is automatically generated just because the signature has `throws`.**

### 3.2. `throws` Can List Multiple Types

```java
static void process() throws java.io.IOException,
        java.text.ParseException {
    // Operation that may throw IOException or ParseException.
}
```

Types are separated by commas. That does not mean both exceptions will be thrown together on every call. A single abnormal termination typically has one `Throwable` object propagating (which may carry a cause or other suppressed exceptions).

There is also no need to declare redundant `throws` types when a supertype already covers the thrown subtypes. For example, `throws IOException` is sufficient for `FileNotFoundException extends IOException`. However, overly broad declarations such as `throws Exception` or `throws Throwable` often make it hard for callers to know how to handle specific failures, so prefer types that accurately express the contract.

### 3.3. `throws` Can Be Used in Constructors and Interface Declarations

```java
interface DocumentReader {
    String read() throws java.io.IOException;
}

final class ReaderSetup {
    ReaderSetup(String path) throws java.io.IOException {
        if (path == null) {
            throw new java.io.IOException("Thiếu đường dẫn");
        }
    }
}
```

These are type declarations without `main`. The `throws` clause belongs on interface methods and constructors. Conversely, `throw` appears **inside the constructor body** when an error condition is actually encountered.

## 4. Relationship With Checked and Unchecked Exceptions

**Checked exception:** subclasses of `Throwable` that are not under `RuntimeException` or `Error`, such as `IOException` and `ParseException`. If a checked exception can escape a method, the method must catch it or declare a sufficiently broad `throws` clause.

**Unchecked exception:** `RuntimeException`, `Error`, and their subclasses. The compiler does not require catching them or listing them with `throws`, though they can be thrown with `throw` and expected cases should be documented.

| Throw statement | Category | Required to have `throws`/`catch` when escaping a method? |
| --- | --- | --- |
| `throw new IOException("Lỗi I/O");` | Checked | Yes |
| `throw new ParseException("Sai định dạng", 0);` | Checked | Yes |
| `throw new Exception("Lỗi");` | Checked | Yes |
| `throw new IllegalArgumentException("Sai");` | Unchecked (`RuntimeException`) | Not required |
| `throw new AssertionError("Sai giả định");` | Unchecked (`Error`) | Not required, though should not be used for business errors |
| `throw new Throwable("Lỗi");` | Checked | Yes, usually requires `throws Throwable` or an appropriate handler |

Note: **`Exception` is not synonymous with checked exception**: `RuntimeException` is a subclass of `Exception` yet belongs to the unchecked category. Nor does every `Throwable` belong to the `Exception` branch: `Error` is a separate branch.

### 4.1. Checked Exception: Two Valid Ways to Compile

Suppose we need to raise an `IOException` when data is missing.

**Approach 1 — make the caller responsible using `throws`:**

```java
static void readOrFail(String data) throws java.io.IOException {
    if (data == null) {
        throw new java.io.IOException("Thiếu dữ liệu");
    }
}
```

**Approach 2 — handle it within the method itself using `try/catch`:**

```java
static void readOrReport(String data) {
    try {
        if (data == null) {
            throw new java.io.IOException("Thiếu dữ liệu");
        }
    } catch (java.io.IOException e) {
        System.out.println("Đã nhận lỗi: " + e.getMessage());
    }
}
```

These two examples are **methods**, not standalone program files. Both compile when placed inside a class, but they **differ in their contract**: Approach 1 delegates error-handling responsibility to the caller; Approach 2 reports the error locally and completes normally after `catch`. If it merely prints a log and ignores the failure—misleading the caller into thinking the operation succeeded—Approach 2 is inappropriate.

### 4.2. Unchecked Exception: `throw` Without `throws`

```java
static int requirePositive(int n) {
    if (n <= 0) {
        throw new IllegalArgumentException("Phải lớn hơn 0");
    }
    return n;
}
```

This is an unchecked exception. Adding `throws IllegalArgumentException` is valid but not required; it also **does not force the caller** to catch or declare it. Javadoc `@throws` is usually the right place to describe invalid-precondition errors that an API is expected to signal.

### 4.3. Declaring `throws` Does Not Restrict All Runtime Errors

A method declaring `throws IOException` can still encounter `NullPointerException`, `IllegalArgumentException`, or `Error`. This declaration describes the checked exceptions that the compiler/caller must account for under the contract; it **does not promise that the method can only throw `IOException`** or that all other errors have been ruled out.

## 5. Complete Java 17 Example: `throw` and `throws` Working Together

Save as `ThrowVsThrowsDemo.java`:

```java
import java.io.IOException;

public class ThrowVsThrowsDemo {
    static int parsePositive(String text) {
        int number = Integer.parseInt(text);
        if (number <= 0) {
            throw new IllegalArgumentException("Số phải dương");
        }
        return number;
    }

    static int readCount(String text) throws IOException {
        if (text == null) {
            throw new IOException("Nguồn dữ liệu trống");
        }
        return parsePositive(text);
    }

    static void show(String input) {
        try {
            System.out.println("Số lượng: " + readCount(input));
        } catch (IOException e) {
            System.out.println("Lỗi nguồn: " + e.getMessage());
        } catch (IllegalArgumentException e) {
            System.out.println("Lỗi đầu vào: "
                    + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        show("7");
        show("0");
        show("abc");
        show(null);
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 ThrowVsThrowsDemo.java
java ThrowVsThrowsDemo
```

Stdout:

```text
Số lượng: 7
Lỗi đầu vào: IllegalArgumentException
Lỗi đầu vào: NumberFormatException
Lỗi nguồn: Nguồn dữ liệu trống
```

**Why is this output produced?**

- `parsePositive("7")` returns `7`, and `readCount` also returns normally.
- `parsePositive("0")` executes `throw new IllegalArgumentException(...)`. It has no `throws` because this is an unchecked exception; `show` catches it with `catch (IllegalArgumentException)`.
- `Integer.parseInt("abc")` throws `NumberFormatException`. This type extends `IllegalArgumentException`, so it is still caught by `catch (IllegalArgumentException)`.
- `readCount(null)` **directly throws** `new IOException(...)` via `throw`. Because `IOException` is checked, `readCount` declares `throws IOException`; `show` takes responsibility for catching it.
- These exceptions do not occur simultaneously in a single call. Each invocation of `show` either succeeds or branches into one error-handling path.

**Lesson on responsibility:** a low-level method can **throw**, an intermediate method can **declare to propagate**, and a layer close to the user can **catch to display an appropriate result**. `throw`, `throws`, and `catch` do not compete with one another: they handle different stages along the same exception path.

## 6. Exception Propagation: Having `throws` Without `throw` in the Middle Layer

One of the most common uses of `throws` is to **propagate** a checked exception from a lower-level method rather than catching it at a layer that lacks sufficient context to handle it.

Create `ThrowsPropagationDemo.java`:

```java
import java.io.IOException;

public class ThrowsPropagationDemo {
    static void readSource() throws IOException {
        throw new IOException("Không đọc được nguồn");
    }

    static void prepareReport() throws IOException {
        readSource();
    }

    static void run() {
        try {
            prepareReport();
            System.out.println("Báo cáo đã sẵn sàng");
        } catch (IOException e) {
            System.out.println("Báo cáo thất bại: " + e.getMessage());
        }
    }

    public static void main(String[] args) {
        run();
        System.out.println("Đã xử lý xong yêu cầu");
    }
}
```

Run:

```bash
javac -encoding UTF-8 ThrowsPropagationDemo.java
java ThrowsPropagationDemo
```

Stdout:

```text
Báo cáo thất bại: Không đọc được nguồn
Đã xử lý xong yêu cầu
```

Execution flow:

```text
main()
  └── run()
        └── prepareReport() throws IOException
              └── readSource() throws IOException
                    └── throw new IOException(...)
        ◀──── IOException propagates back through prepareReport()
  └── catch (IOException) in run()
```

`readSource` has both `throw` and `throws`. `prepareReport` only has `throws`, with no direct `throw`; the exception raised by `readSource()` propagates through it. `run` catches it at a boundary that can report a meaningful failure outcome. The line "Báo cáo đã sẵn sàng" is skipped because the call to `prepareReport()` does not return normally.

**Having `throws` does not mean the exception is automatically thrown again.** The runtime propagates the same unhandled exception up the call stack; no new object is created merely by passing through a `throws` signature.

## 7. `throw e` and `throw new ...`: Rethrowing, Wrapping, and Preserving the Cause

After catching an exception, code can:

- handle it and complete normally;
- rethrow the same object with `throw e;`;
- create a new exception object and throw it with `throw new ...`, typically preserving the `cause`.

Example illustrating a method fragment:

```java
try {
    loadData();
} catch (java.io.IOException e) {
    recordFailure(e);
    throw e;
}
```

This code depends on `loadData`/`recordFailure` being defined, and the enclosing method must declare or catch the appropriate checked exception. `throw e;` does not create a new exception. Depending on context, the compiler may apply **precise rethrow** to an effectively final `catch` parameter, inferring the specific checked exceptions that can be thrown from the `try` block.

If you want to add context:

```java
try {
    loadData();
} catch (java.io.IOException e) {
    throw new IllegalStateException("Không nạp được dữ liệu", e);
}
```

Here `IllegalStateException` is unchecked, and the `IOException` cause is preserved via `getCause()`. **Avoid writing `throw new RuntimeException(e.getMessage())` just to drop the `throws` requirement**, because doing so loses the underlying cause object and does not recover the program.

### 7.1. Standalone Example Showing Wrapper and Cause

Create `WrapCauseDemo.java`:

```java
import java.io.IOException;

public class WrapCauseDemo {
    static void lowLevel() throws IOException {
        throw new IOException("Lỗi kết nối");
    }

    static void service() {
        try {
            lowLevel();
        } catch (IOException e) {
            throw new IllegalStateException("Tác vụ không thể hoàn tất", e);
        }
    }

    public static void main(String[] args) {
        try {
            service();
        } catch (IllegalStateException e) {
            System.out.println("Loại: "
                    + e.getClass().getSimpleName());
            System.out.println("Thông điệp: " + e.getMessage());
            System.out.println("Nguyên nhân: "
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 WrapCauseDemo.java
java WrapCauseDemo
```

Stdout:

```text
Loại: IllegalStateException
Thông điệp: Tác vụ không thể hoàn tất
Nguyên nhân: IOException
```

`service` has `throw new IllegalStateException(...)` without needing `throws` because the new exception is unchecked. `lowLevel` has `throw new IOException(...)` and `throws IOException` because it is checked. Wrapping does not erase **behavioral responsibility**: the caller still needs to understand the failure and the post-failure state; switching to an unchecked exception only changes the compiler constraint.

## 8. `throws` and Method Overriding Rules

The `throws` clause is an important part of the checked exception contract in Java polymorphism.

When a subclass method overrides a superclass/interface method:

- The overriding method **must not declare new or broader checked exceptions** than those permitted by the overridden method.
- The overriding method may declare **more specific** or fewer checked exceptions, including declaring no checked exceptions at all.
- Unchecked exceptions are not subject to this restriction.
- This rule applies to **overriding**, not to every method with the same name (overloading with a different parameter signature is a separate matter).

### 8.1. Compilable Java 17 Example

Create `ThrowsOverrideDemo.java`:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

public class ThrowsOverrideDemo {
    interface Source {
        String get() throws IOException;
    }

    static final class MemorySource implements Source {
        @Override
        public String get() {
            return "Bộ nhớ";
        }
    }

    static final class MissingSource implements Source {
        @Override
        public String get() throws FileNotFoundException {
            throw new FileNotFoundException("Không thấy tài liệu");
        }
    }

    public static void main(String[] args) {
        Source[] sources = {
                new MemorySource(),
                new MissingSource()
        };

        for (Source source : sources) {
            try {
                System.out.println("Dữ liệu: " + source.get());
            } catch (IOException e) {
                System.out.println("Lỗi: " + e.getMessage());
            }
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 ThrowsOverrideDemo.java
java ThrowsOverrideDemo
```

Stdout:

```text
Dữ liệu: Bộ nhớ
Lỗi: Không thấy tài liệu
```

`Source.get() throws IOException` defines the general contract. `MemorySource.get()` omits `throws` altogether because it raises no checked exception. `MissingSource.get() throws FileNotFoundException` is valid because `FileNotFoundException` is a subclass of `IOException`.

Even though the runtime object may be `MemorySource`, the loop variable has static type `Source`, so the call `source.get()` is still checked by the compiler against the interface's `throws IOException` contract. This shows how the **reference type used at the call site** also affects handling obligations.

### 8.2. Invalid Override Example

The following lines **illustrate a compile-time error**; do not place them into a runnable example file:

```java
interface Api {
    void execute() throws java.io.IOException;
}

class BadImplementation implements Api {
    @Override
    public void execute() throws java.sql.SQLException {
        // Invalid: SQLException is not a subclass of IOException.
    }
}
```

A caller that only knows about `Api` must not be unexpectedly forced to handle an entirely different checked exception because an implementation widened the contract. Java prevents this at compile time.

Do not equate the overriding rule with saying a method **cannot** throw an unchecked exception at runtime. An override can still `throw new IllegalStateException(...)` even if the interface signature does not declare that type.

## 9. `throws` With Lambdas and Functional Interfaces

A common pitfall in modern Java: a lambda must conform to the signature of its **functional interface**. You cannot add a checked exception to a lambda just because you want to write `throw`.

Illustrative code snippet:

```java
Runnable task = () -> {
    // throw new java.io.IOException("I/O"); // Invalid here.
    throw new IllegalStateException("Tác vụ không hợp lệ");
};
```

`Runnable.run()` does not declare `throws IOException`; therefore, the lambda cannot let a checked `IOException` escape its body without handling it locally. However, the unchecked `IllegalStateException` is allowed.

A callback with its own interface can declare a checked exception:

```java
@FunctionalInterface
interface CheckedJob {
    void run() throws java.io.IOException;
}
```

When a lambda is assigned to `CheckedJob`, it is allowed to throw `IOException` in accordance with the abstract method's contract. This is an example of using a `throws` signature to pass handling responsibility through an interface, not a special privilege of lambdas.

In Java 17+ code, do not switch to `throws Exception` for every callback just to "get past the compiler"; choose an exception type that is meaningful to API consumers.

## 10. `throws` and try-with-resources: Errors Can Come From `close()`

The `throws` clause is not only related to `throw` statements you write yourself. Many APIs declare checked exceptions due to I/O operations or resource cleanup. With `AutoCloseable`, `close()` can declare a checked exception, and try-with-resources can cause that exception to escape when exiting the block.

Illustrative method example:

```java
static void openAndClose() throws java.io.IOException {
    try (java.io.BufferedReader reader =
                 new java.io.BufferedReader(
                         new java.io.StringReader("abc"))) {
        System.out.println(reader.readLine());
    }
}
```

The method **has no `throw` statement**. However, `BufferedReader.readLine()` and `BufferedReader.close()` declare `IOException`, so the `throws IOException` signature is appropriate. With concrete `StringReader` data, the example normally runs without error, yet the type contract does not infer behavior from specific input values.

If both the block body and `close()` throw an exception, try-with-resources keeps the body's exception as the primary exception and records the closing exception in `getSuppressed()` according to the corresponding rules. Do not confuse "having `throws`" with "automatically closing resources", or "being closed" with "rolling back changes made before the error".

## 11. Common Misconceptions

| Misconception | Reality to remember |
| --- | --- |
| "`throw` and `throws` are two ways to write the same feature." | `throw` executes the throw action; `throws` declares the possibility of errors escaping a method/constructor. |
| "Just adding `throws` makes an exception happen automatically." | No; an actual exception must be created by a `throw` statement or another operation/call. |
| "Having a `throw` statement requires adding `throws`." | Only checked exceptions that can escape require catching or declaring. Unchecked exceptions do not. |
| "A method with `throws` definitely contains a `throw` line." | The exception can come from a callee method, constructor, resource `close()`, library, or JVM. |
| "`throws` is used with an object like `new IOException(...)`." | `throws` takes **type names**, whereas `throw` takes an **expression** of type `Throwable`. |
| "`throws IOException` means only `IOException` can be thrown." | Unchecked exceptions and `Error`s can still occur; the signature does not guarantee exclusivity. |
| "`throws Exception` is always more convenient than specific declarations." | It increases the burden on callers and hides information about which error types can be handled. |
| "`RuntimeException` is unchecked, so it cannot be caught with `catch`." | Unchecked means handling is not enforced at compile time; it can still be caught by a compatible type. |
| "`throw null` throws a null object." | At runtime, Java creates/throws a `NullPointerException` instead. |
| "`throw new Exception("x")` in a method without `throws` is always allowed." | `Exception` is checked; it must be caught or declared if it escapes. |
| "Overriding a method can add any checked `throws`." | An override must not broaden checked exceptions against the parent/interface method's contract. |
| "Adding `throws` automatically rolls back state." | Java does not automatically undo side effects when an exception occurs. |
| "Changing a checked exception to `RuntimeException` fixes the bug." | It only changes the compiler constraint; the root error, cause, state, and handling policy still matter. |
| "`throw e` creates a new exception." | `throw e` rethrows the object referenced by `e`. |

### 11.1. Common Compiler Messages

- **"unreported exception ...; must be caught or declared to be thrown"**: a method calls an API with a checked exception or executes `throw` with a checked exception, without catching or declaring it.
- **"incompatible types ... cannot be converted to Throwable"**: the expression after `throw` is not in the `Throwable` type hierarchy.
- **"overridden method does not throw ..."**: an overriding method attempts to add a checked exception beyond the parent/interface contract.
- **"exception ... has already been caught"**: a specific handler is shadowed by a broader handler placed before it.

Exact messages depend on the compiler/JDK; read the cause and fix the contract or handling flow rather than arbitrarily adding `throws Exception`.

## 12. Decision Process: When to Use `throw` vs. `throws`

### Step 1 — Identify the Failure Condition

For example, a method receives a quantity and must ensure `quantity > 0`. When an invalid condition is detected, `throw new IllegalArgumentException(...)` expresses a contract violation.

### Step 2 — Choose an Appropriate Exception Type

If the failure is due to invalid caller arguments or an invalid state, an unchecked exception may be appropriate. If an API reads files or communicates with an I/O source using checked `IOException`, preserve its declaration mechanism. There is no rigid rule such as "all user errors are checked" or "all business errors are unchecked".

### Step 3 — Identify the Layer Capable of Handling It

If a low-level method does not know whether to prompt for re-entry, try another source, or abort the operation, it can let the checked exception propagate upward via `throws`. Only a layer with real context should `catch` it to respond appropriately.

### Step 4 — Write a Clear Signature

Declare expected checked exceptions using meaningful types. Avoid `throws Throwable` and `throws Exception` when you can narrow them. For unchecked exceptions important to the contract, document them with Javadoc `@throws` and test the failure conditions.

### Step 5 — Test Both Success and Failure Paths

Do not only check for "the right exception type". Test boundary inputs, propagation paths, data/resource state after failure, wrappers/causes, and appropriate handler placement.

## 13. Javadoc: `@throws` Is Not the `throws` Keyword

A Java API often has both a `throws` clause in the signature and `@throws` tags in the documentation. These two are also **different**:

```java
/**
 * Reads a code from a data source.
 *
 * @param input data must not be null
 * @return the code read
 * @throws IllegalArgumentException if input violates the contract
 * @throws java.io.IOException if the data source cannot be read
 */
static String readCode(String input) throws java.io.IOException {
    if (input == null) {
        throw new IllegalArgumentException("input không được null");
    }
    return input;
}
```

This is an illustrative method. `@throws` in Javadoc is **documentation for human readers and doc-generation tools**; it does not directly alter compiler obligations. `throws IOException` in the signature is the language-level declaration for a checked exception that may escape. `throw new IllegalArgumentException(...)` in the body is the statement that actually throws.

In this example snippet, `IOException` is declared to represent a source-reading API variant; the concrete implementation returns `input` and does not itself raise `IOException`. The Java compiler allows a method to **declare a checked exception that the current execution path does not yet throw**; however, writing an overly broad contract without a practical reason can still inconvenience callers.

## 14. Practice Exercises

### Exercise 1 — Identify the Role of Each Line

Consider the following method:

```java
static void verify(boolean valid) throws java.io.IOException {
    if (!valid) {
        throw new java.io.IOException("Không hợp lệ");
    }
}
```

Answer:

1. Which keyword appears in the **signature**?
2. Which line **actually creates and throws** the exception?
3. Does calling `verify(true)` automatically raise an `IOException` because of `throws`?
4. If a caller invokes `verify(false)` without catching or declaring the checked exception, what does the compiler report?

**Guidance:** `throws` is in the signature; `throw` is in the body. With `true`, the method completes normally; the caller must still satisfy the compile-time obligation announced by the signature.

### Exercise 2 — Fix a Compile-Time Error

The following snippet is intentionally wrong:

```java
static void reject() {
    throw new java.io.IOException("Đọc thất bại");
}
```

Fix it in two ways: add `throws IOException` to the method and update the caller; or use `try/catch` inside the method to genuinely handle it. Describe the difference in handling responsibility.

### Exercise 3 — No `throw` Visible, Yet `throws` Is Still Needed

Write `readFirstLine(BufferedReader reader)` that simply calls `reader.readLine()` and returns the result. Explain why the method may need `throws IOException` even though it does not call `throw` itself. Then write `main` to catch `IOException` and display a contextual message.

### Exercise 4 — Preserve the Cause

In `WrapCauseDemo`, replace `new IllegalStateException("...", e)` with `new IllegalStateException("...")` and run it again. `getCause()` is then `null`; code printing `getCause().getClass()` will cause a `NullPointerException`. Explain why preserving the cause is important when wrapping errors and why you must not assume every exception has a cause.

### Exercise 5 — Overriding and Reference Types

In `ThrowsOverrideDemo`, try declaring `Source source = new MemorySource();`. Even though the implementation declares no checked exception, why must `source.get()` still obey the interface's `throws IOException` contract at compile time? Change the variable type to `MemorySource` and compare the compile-time obligations.

### Exercise 6 — Design Your Own API

Create two methods: `parseAge(String input)` and `loadAgeFromFile(Path path)`. The first validates non-negative input and throws an appropriate unchecked exception; the second reads a file, can declare checked `IOException`, and then calls the first method. Write Javadoc describing each error; test the success path, negative numbers, non-numeric strings, non-existent files, and data state after failure.

## 15. Review Checklist

- [ ] Write `throw expression;` and `method(...) throws Type1, Type2` in the correct forms.
- [ ] Know that `throw` is an executable statement while `throws` is a declaration clause.
- [ ] Distinguish an object expression after `throw` from **type names** after `throws`.
- [ ] Explain why `throw "error";` does not compile, while `throw new IOException("error");` has a valid type but requires checked-exception handling.
- [ ] Explain why throwing an unchecked exception with `throw` does not require `throws`.
- [ ] Explain why a method can have `throws IOException` even without a direct `throw` statement.
- [ ] Accurately predict the stdout of `ThrowVsThrowsDemo` and `ThrowsPropagationDemo`.
- [ ] Understand how `catch` handles a checked exception after it propagates across multiple call layers.
- [ ] Distinguish `throw e;` from `throw new WrapperException("...", e);` and preserving the cause.
- [ ] State the restrictions on checked exceptions in overriding, interfaces, and lambdas.
- [ ] Distinguish Javadoc `@throws` from the Java `throws` clause.
- [ ] Do not treat `throws` as a mechanism for automatic rollback, automatic logging, or automatic recovery.
- [ ] Know how to choose where to handle exceptions based on contracts and actual recovery capability.

**Key takeaway:** **`throw` makes an error occur on a specific execution path; `throws` announces which error types can escape a method and helps the compiler and callers fulfill their obligations for checked exceptions.** Using both properly keeps the success path clear, the failure path accountable, and call layers coordinated predictably.