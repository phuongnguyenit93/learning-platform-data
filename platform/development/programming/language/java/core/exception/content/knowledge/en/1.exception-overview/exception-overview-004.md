# Components in the Java Exception Flow: Throw Site, Call Site, and Handler

When an operation in Java fails, understanding **where the exception starts, which methods it passes through, and where it is handled** helps you read stack traces, choose where to place `try-catch`, and design responsibilities across layers. The three core roles are:

1. **Throw site (origin):** the statement or operation where the exception is thrown into the execution flow.
2. **Call site (caller):** the statement calling the method where the error occurs; there may be one or more nested call levels.
3. **Handler:** the nearest matching `catch` block according to the JVM's search order along the active call chain; this block decides whether to recover, translate the error, or terminate the request.

Importantly: **the throw site and the handler do not necessarily reside in the same method**. A method may simply propagate the exception upward without a `catch` block.

## 1. The Three Roles at a Glance

Consider the call chain `main() → processRequest() → parseQuantity()`. When `parseQuantity()` encounters a string that cannot be converted to a number, the exception can propagate backward through unfinished calls:

```text
main()                     ← handler: catch in main
  └── processRequest()     ← call site for parseQuantity; may propagate
        └── parseQuantity()← throw site
              throw
              ↓
        no matching catch
              ↓
  exception propagates back up to main()
              ↓
      matching catch → handle
```

This is a **dynamic call chain at the time the error occurs**, not an inheritance relationship or simply the order in which methods are declared in a file. Two methods calling the same `parseQuantity()` can route the exception to two different handlers.

| Component | What it is doing | Example | Question to answer |
| --- | --- | --- | --- |
| Throw site | Detects an error condition and throws an exception | `throw new IllegalArgumentException(...)` | Why cannot the operation continue? |
| Call site | Calls a method that may throw; receives the result or is interrupted | `int n = parseQuantity(text);` | Should it be handled here or left to a higher level? |
| Handler | Catches a compatible exception type and takes action | `catch (IllegalArgumentException ex) { ... }` | Can we fix the input, retry, respond to the user, or translate the error? |

A single method can **take on multiple roles at the same time**: it calls another method, catches the resulting exception, and throws a new exception to add context. Separating the three roles is for reading the execution flow clearly, not to force a program into three separate classes.

## 2. Throw Site: How Are Exceptions Created and Thrown?

### Explicitly throwing with `throw`

When a condition violates a contract, code can explicitly create and throw an exception object:

```java
static int requirePositive(int value) {
    if (value <= 0) {
        throw new IllegalArgumentException("Số phải lớn hơn 0");
    }
    return value;
}
```

This is an **illustrative method snippet** and must be placed inside a Java class to compile standalone. When `value <= 0`, the `throw` statement stops the normal execution path right there; `return value` does not run. The `IllegalArgumentException` type indicates that the argument does not satisfy the precondition, while the message states the specific reason.

Distinguish between two operations:

- `new IllegalArgumentException(...)` **creates** the exception object.
- `throw exception` **throws** that object into the exception-handling mechanism.

Both operations often appear on the same line, but they are semantically distinct. When rethrowing an already-caught object with `throw ex;`, we do not create a new exception.

### Exceptions raised by operations/APIs

Not every exception comes from a `throw` statement you write directly:

- `Integer.parseInt("abc")` throws `NumberFormatException` because the string does not represent a valid integer.
- Integer division `10 / 0` throws `ArithmeticException`; floating-point division follows different IEEE 754 rules and should not be assumed to behave identically.
- Accessing an array element at an out-of-bounds index throws `ArrayIndexOutOfBoundsException`.
- Calling a method on a `null` reference can throw `NullPointerException`.
- Reading a file can throw `IOException` per the API contract.

For errors detected by the JVM or library code, the throw site is **the point where the operation actually throws the exception**. The API call site is where application code can observe the exception being propagated out; it is not necessarily the deepest place in the library where the error was detected.

### When should a situation be treated as an error?

Not finding an element in a search designed to allow "no result" can be represented with `Optional.empty()` or an empty list. Conversely, a method whose contract requires "configuration must exist" but cannot read the file needs to report an error clearly. Before using `throw`, determine **whether it is truly a contract violation or simply an expected outcome**.

## 3. Call Site: The Handoff Point for a Result or Exception

Example:

```java
int quantity = parseQuantity(input);
System.out.println("Số lượng: " + quantity);
```

The first statement is the **call site**. If `parseQuantity(input)` returns normally, the `quantity` variable receives the value and the print statement runs. If the call throws an exception that is not handled inside that method:

1. The call does not complete normally, so the assignment to `quantity` does not complete.
2. The `println` line after it does not run on that execution path.
3. The JVM searches for a compatible `catch` enclosing the call site; if none is found, it continues searching in the method that called the current method.
4. This process continues through active calls until a handler is found, or the exception becomes *uncaught*.

**A call site does not need to contain a `try-catch`**. Depending on the application layer, letting the exception propagate upward is often more sensible than catching it just to print a line and ignore it.

### `throws` and `throw` are not interchangeable

```java
static String readConfig() throws java.io.IOException {
    return java.nio.file.Files.readString(
            java.nio.file.Path.of("config.txt"));
}
```

This is an illustrative method snippet; exact behavior depends on file existence and access permissions.

- `throws IOException` on the method declaration states that a call **may let this checked exception propagate out**. The declaration itself does not create or throw an exception.
- `throw new IOException(...)` inside the method body is a statement that **actually throws an exception**.
- A caller of `readConfig()` must catch `IOException` or also declare `throws IOException` (except in special cases permitted by the language). There is no similar requirement when propagating most unchecked exceptions such as `IllegalArgumentException`.

How to read the signature: `throws` describes part of the compile-time checked contract; `throw` affects the runtime execution flow.

## 4. Handler: The Nearest Matching `try-catch`

Typical syntax:

```java
try {
    // Call code that may throw an exception.
} catch (NumberFormatException ex) {
    // Handle number conversion error.
} catch (IllegalArgumentException ex) {
    // Handle other argument errors.
} finally {
    // Clean up or record the end of the operation.
}
```

This snippet illustrates the structure only, not a standalone runnable file.

- `try` defines the block of code monitored for exceptions.
- `catch (Type ex)` is selected when the exception object's type is **the same type or a subclass** of `Type`. An exception is handled by **the first matching `catch` block in source-code order within the `try` region being evaluated**.
- When there are multiple `catch` blocks, place **specific types before general types**. `NumberFormatException` extends `IllegalArgumentException`; swapping the two blocks in the example would make the specific block unreachable and cause a compile error.
- `finally` normally runs when exiting `try`/`catch` whether it succeeds, throws an error, or executes `return`. It is used for necessary cleanup; for `AutoCloseable` resources, prefer `try-with-resources`.

Saying "nearest handler" refers to **an active handling region along the current call path**, not the `catch` block closest in line numbers in the file. The JVM first checks handlers in effect at the throw point, and only propagates to the caller if none match.

If a `catch` finishes handling and **does not rethrow**, that exception stops propagating; execution continues after the `try-catch-finally` structure (if the thread can continue). If `catch` rethrows or throws another exception, the search for a new handler begins again.

## 5. Complete Java 17+ Example: Observing Each Layer A → B → C

Save the code as **`ExceptionFlowDemo.java`**:

```java
public class ExceptionFlowDemo {

    // C: throw site; may throw directly or via the parseInt API.
    static int parseQuantity(String input) {
        System.out.println("C: bắt đầu kiểm tra");
        int number = Integer.parseInt(input);

        if (number <= 0) {
            throw new IllegalArgumentException("số lượng phải > 0");
        }

        System.out.println("C: trả kết quả");
        return number;
    }

    // B: call site for C; does not catch or alter the exception itself.
    static int prepareOrder(String input) {
        System.out.println("B: gọi C");
        int quantity = parseQuantity(input);
        System.out.println("B: đã nhận số lượng");
        return quantity;
    }

    // A: call site for B and also the error handler.
    static void handleRequest(String input) {
        System.out.println("A: nhận yêu cầu " + input);
        try {
            int quantity = prepareOrder(input);
            System.out.println("A: tạo đơn với " + quantity + " sản phẩm");
        } catch (NumberFormatException ex) {
            System.out.println("A: lỗi định dạng số");
        } catch (IllegalArgumentException ex) {
            System.out.println("A: " + ex.getMessage());
        } finally {
            System.out.println("A: kết thúc yêu cầu");
        }
    }

    public static void main(String[] args) {
        handleRequest("3");
        System.out.println("---");
        handleRequest("0");
        System.out.println("---");
        handleRequest("abc");
    }
}
```

Run with JDK 17 or later:

```bash
javac -encoding UTF-8 ExceptionFlowDemo.java
java ExceptionFlowDemo
```

**Exact stdout:**

```text
A: nhận yêu cầu 3
B: gọi C
C: bắt đầu kiểm tra
C: trả kết quả
B: đã nhận số lượng
A: tạo đơn với 3 sản phẩm
A: kết thúc yêu cầu
---
A: nhận yêu cầu 0
B: gọi C
C: bắt đầu kiểm tra
A: số lượng phải > 0
A: kết thúc yêu cầu
---
A: nhận yêu cầu abc
B: gọi C
C: bắt đầu kiểm tra
A: lỗi định dạng số
A: kết thúc yêu cầu
```

### Analysis of the three execution paths

**Request `"3"` — success:** `main` calls A; A calls B; B calls C; C returns `3`. The flow finishes normally in reverse order C → B → A. Since no exception occurs, no `catch` runs; A's `finally` still runs.

**Request `"0"` — C throws explicitly:** `Integer.parseInt("0")` converts successfully, but `number <= 0` violates the business rule. `throw new IllegalArgumentException(...)` in C causes the line `"C: trả kết quả"` to be skipped. B also does not print `"B: đã nhận số lượng"` because the call to C did not return a result. A has `catch (IllegalArgumentException)`, so it receives the error, prints the message, and then runs `finally`.

**Request `"abc"` — API throws an error:** `NumberFormatException` is thrown inside `Integer.parseInt` called at C, before the `if` statement runs. B has no handler, so it propagates to A. Because `NumberFormatException` matches the first, more specific `catch` block, A prints `"A: lỗi định dạng số"`. The program produces no stack trace on stderr because the exception was caught and not rethrown.

From the example, we see that **the throw site holds the technical/business reason**, **the call site decides whether to intervene at the current layer**, and **the handler decides what action to take for the ongoing request**. These roles do not require every layer to catch the same error.

## 6. Exception Propagation and Call Stack Unwinding

When an exception is not handled in the current method, the JVM exits that method via abrupt completion and looks for a matching handler in its caller. This is **exception propagation**; the process of exiting active call frames is commonly called **stack unwinding**.

Suppose:

```text
main()  →  A()  →  B()  →  C()
                         |
                         throw X
             ← X ← X ← X |
```

If C and B have no matching `catch`, but A does, then A handles X. Afterward, A can continue from **after the `try-catch` block**, rather than "resuming at the exact interrupted statement" in B or C. Statements after the failed call in B and C have already been skipped.

### `finally` and cleanup during propagation

`finally` blocks along the unwinding path are executed according to Java rules. If B has a `try-finally` enclosing the call to C, B's `finally` block runs before the exception reaches A's handler.

```java
static void middle() {
    try {
        fail();
    } finally {
        System.out.println("B: dọn dẹp");
    }
}

static void fail() {
    throw new IllegalStateException("thất bại tại C");
}
```

These are illustrative methods, not a standalone program. If caller A catches `IllegalStateException`, the order is: error at C → B's cleanup line prints → handler at A. `finally` **does not automatically swallow errors**; the exception continues propagating after cleanup. However, if `finally` itself throws a new exception or uses `return`, it can alter or obscure the original cause; therefore, avoid overriding the error flow inside `finally`.

Not every `finally` block is guaranteed to run in abnormal JVM termination scenarios (for example, `Runtime.halt` or a forcibly killed process). For resource objects, `try-with-resources` is generally safer and easier to read.

### What if there is no handler at all?

An *uncaught* exception escaping to the top of a thread is handled by the thread's uncaught-exception handler mechanism (which typically prints the exception name and stack trace to stderr under default configuration), and that thread terminates. An uncaught error in one thread **does not automatically mean the entire Java process stops immediately**: other threads may still keep running. Therefore, do not rely on uncaught exceptions as a way to return business errors to users.

## 7. Checked Exceptions: Call Sites Must Choose to Catch or Declare

Some exceptions, such as `IOException`, are **checked exceptions**. When calling a method that can throw them, the compiler requires the caller to handle them or continue declaring `throws`. That helps API authors surface situations that need attention early, though it does not mean every `catch` can provide a meaningful recovery.

The following standalone program demonstrates a middle layer simply forwarding the error. Save it as **`CheckedExceptionFlowDemo.java`**:

```java
import java.io.IOException;

public class CheckedExceptionFlowDemo {

    // C: intentionally simulates an I/O failure so the example does not depend on the filesystem.
    static String readConfig() throws IOException {
        System.out.println("C: đọc cấu hình");
        throw new IOException("không đọc được cấu hình");
    }

    // B: caller of C; does not catch, but must declare throws IOException.
    static String prepareConfig() throws IOException {
        System.out.println("B: gọi C");
        return readConfig();
    }

    // A: caller of B and handler of IOException.
    public static void main(String[] args) {
        try {
            System.out.println("A: gọi B");
            String config = prepareConfig();
            System.out.println("A: đã đọc " + config);
        } catch (IOException ex) {
            System.out.println("A: xử lý " + ex.getMessage());
        }
        System.out.println("A: tiếp tục");
    }
}
```

Run:

```bash
javac -encoding UTF-8 CheckedExceptionFlowDemo.java
java CheckedExceptionFlowDemo
```

Stdout:

```text
A: gọi B
B: gọi C
C: đọc cấu hình
A: xử lý không đọc được cấu hình
A: tiếp tục
```

Notes:

- C **actually throws** using `throw new IOException`.
- B **calls C and propagates** by declaring `throws IOException`, without creating another error; `return readConfig()` does not complete because C threw.
- A **catches and handles** at a boundary that can decide the response, after which the program continues.
- If you remove `throws IOException` from B while keeping the call without `try-catch`, the code will not compile. Conversely, `RuntimeException` types are not required to be declared this way.

## 8. What If the Middle Layer Needs to Add Context?

Sometimes B knows useful information that C does not have: the operation name, request ID, or the type of data being processed. B can catch the exception from C and throw **another exception wrapping the original cause**:

```java
static int parseAmount(String raw) {
    try {
        return Integer.parseInt(raw);
    } catch (NumberFormatException cause) {
        throw new IllegalArgumentException(
                "Không đọc được số lượng đơn hàng từ chuỗi: " + raw,
                cause);
    }
}
```

This is an illustrative method and must be placed inside a Java class. In this case:

1. `Integer.parseInt` is the original throw site of `NumberFormatException`.
2. `parseAmount` is both the caller and has the handler for the original error.
3. `throw new IllegalArgumentException(..., cause)` creates **a new exception** for the outer caller to handle; `cause` keeps the link to the original failure. The outer handler can call `ex.getCause()` for diagnostics.

Only **wrap** when the context or contract at the new layer genuinely needs a different error type. Otherwise, letting the original exception propagate keeps code concise and avoids obscuring the root cause. Avoid reflexively catching and throwing `new RuntimeException("Error")` without preserving `cause`.

Regarding stack traces, a typical exception object has its stack trace recorded upon instantiation (or when `fillInStackTrace()` is called), so the top frame usually reflects where the object was created, whereas an exception rethrown with `throw ex` may still retain its original trace. The trace of a newly wrapped exception reflects where the wrapper was created; the `Caused by` chain points to the underlying cause. Do not infer that the top line of a stack trace is always every location where the object was ever thrown.

## 9. Choosing Where to Handle Based on Layer Responsibility

A Java system often consists of multiple layers. For example: a controller receives requests, a service enforces rules, and a repository accesses data. These are **illustrative architectural roles**, not a constraint that Java requires a framework or strictly three layers.

| Layer / Call Point | Usually should do | Example |
| --- | --- | --- |
| Code detecting the error | Detect and throw an exception type that accurately expresses the failure | Argument violates a rule → `IllegalArgumentException` |
| Middle layer | Handle only if it can recover, translate with context, or needs to release resources | Retry connection per policy, wrap cause to preserve context |
| Communication boundary | Translate the error into a response suited to the caller/user; log where designated | UI reports invalid input; API maps error to an appropriate HTTP status code |
| Thread or background task boundary | Feed the error into task reporting, monitoring, or retry policy | `Future.get()` can report `ExecutionException` containing the cause of the task failure |

"Catch as early as possible" is not the right rule. Catching right at the throw site and returning `null` can make outer layers think the result is valid but empty. Conversely, letting exceptions propagate indefinitely with no handling boundary leaves callers without a meaningful response.

A `catch` is considered **handling** only when it takes deliberate action: restoring state, prompting for re-entry, translating into an appropriate message, marking a task as failed, or translating the error to an outer layer's contract. An empty `catch` usually just hides bugs.

## 10. Common Conceptual and Programming Mistakes

### Confusing where an error was created with where it was detected or handled

When a stack trace has many methods, the top frame may be inside the Java standard library because the library detected invalid data; the call line in application code helps identify **what input you supplied**. Do not rush to blame the method that has the `catch`: it may simply be where the failure arrived.

### Thinking `throws` automatically catches or throws an exception

Declaring `throws IOException` only permits/expresses checked exception propagation; it does not create a `catch` and does not guarantee the method always throws. Only when code actually throws an exception does the abnormal path occur.

### Placing a superclass `catch` before a subclass `catch`

Putting `catch (Exception ex)` before `catch (NumberFormatException ex)` makes the subsequent `catch` block unreachable in the same `try` construct. Java will report a compile error. Place specific errors first and general errors after, if truly needed.

### Catching all errors and continuing as if successful

```java
try {
    process();
} catch (Exception ex) {
    // Ignore everything.
}
sendSuccess();
```

This is an illustrative snippet, not a standalone program. If `process()` fails and the program still calls `sendSuccess()`, the caller is misled. Continue as successful only when there is a **clearly defined recovery that actually succeeded**.

### Placing `catch` with the wrong scope

If `try` only encloses statements that cannot throw the target error, while the risky call sits outside `try`, that handler does not protect the call. Enclose the exact operation to be handled in `try` and keep the region small enough to pinpoint the error source accurately.

### Forgetting cleanup during propagation

If a stream or connection was opened before a call throws an exception, ordinary `close()` statements after the call may be skipped. Use `try-with-resources` for `AutoCloseable` objects to close them automatically when exiting the block; this mechanism also has rules for preserving **suppressed exceptions** if errors occur both during processing and during closing.

### Throwing a new exception while losing the cause

`catch (IOException ex) { throw new IllegalStateException("Không đọc được"); }` hides the `IOException` object from the `cause` relationship. Replace it with `new IllegalStateException("Không đọc được", ex)` if the current layer's policy requires converting to an unchecked exception.

### Misunderstanding what happens after `catch` finishes

Handling an error in A **does not mean** the JVM goes back and resumes the line right after the `throw` point in C. The failed calls have already terminated abruptly. If you want to retry, the handler code must **explicitly invoke the operation again** after ensuring retry conditions and an appropriate attempt limit.

## 11. Checklist for Reading and Designing Exception Flow

When encountering an error in Java code, determine in order:

1. **Where did the error start?** Find the direct `throw` or the Java/API call that raised the exception. Check the type, message, root cause, and related inputs.
2. **Who is calling whom?** Inspect the call stack / stack trace and which methods called one another. At each caller, statements after the failed call are skipped unless a handling construct in the same method brings execution back to a valid position.
3. **Where is the active handler?** Check `try` blocks enclosing the throw point and caller frames, then look for a `catch` with a compatible type. Check `catch` block order, `finally` blocks, and the effect of `try-with-resources`.
4. **Does the handler actually resolve the error?** If not, either let the exception propagate upward or translate the error deliberately while preserving `cause`. Do not turn a failure into data that looks valid.
5. **Is the contract accurately reflected?** For checked exceptions, declare `throws`/`catch` properly; for business errors, choose an appropriate exception type or explicit result type. At application boundaries, translate errors into useful responses.

**Remember the role chain:** the throw site tells you **what broke**, the call site determines **the path the exception travels**, and the handler decides **what the system will do with that failure**. Understanding these three roles helps you place `throw`, `throws`, `try`, `catch`, and `finally` in the right spots without losing diagnostic information.