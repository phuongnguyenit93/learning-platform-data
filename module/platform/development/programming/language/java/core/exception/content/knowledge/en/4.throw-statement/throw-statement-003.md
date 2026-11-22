# Distinguishing Creating an Exception from Throwing an Exception in Java

In Java, **creating an exception object** and **throwing that object** are two different actions. These two actions often appear together in a `throw new ...` statement, so they are easily mistaken for one. Distinguishing between them helps you read execution flow accurately, understand why an `Exception` object can exist while the program continues running normally, why an object can be rethrown, and why a stack trace sometimes records the point of exception creation rather than the `throw` line.

This lesson focuses on the **`throw` statement**, the moment an exception object is created, how that object enters the exception-handling mechanism, the implications for checked exceptions, and diagnostic information.

## 1. Two actions with different meanings

| Action | Example | Immediate result |
| --- | --- | --- |
| **Creating an exception** | `new IllegalArgumentException("Sai tuổi")` | Creates a Java object of a subclass of `Throwable`; this expression itself **does not cause the method to exit due to the newly created exception**. |
| **Holding an exception in a variable** | `IllegalArgumentException ex = new IllegalArgumentException("Sai tuổi");` | The variable `ex` references the object; subsequent statements continue to run normally. |
| **Throwing an existing exception** | `throw ex;` | Triggers exception control flow using the object `ex`; the `throw` statement completes abruptly and searches for a matching handler. |
| **Creating and throwing immediately** | `throw new IllegalArgumentException("Sai tuổi");` | Evaluates `new` to create the object, then `throw`s the newly created object. |
| **Declaring the ability to throw** | `void read() throws IOException` | Describes the method's contract at compile time; **neither creates nor throws** an exception by itself. |

Classes such as `IOException`, `IllegalArgumentException`, or `RuntimeException` are ultimately subclasses of `java.lang.Throwable`. From the language's perspective, an exception is an object with a type, a reference, a message, a cause, and stack trace information. The special behavior occurs when **that object is thrown**.

Example:

~~~java
// Illustration snippet inside a method.
IllegalArgumentException problem =
        new IllegalArgumentException("Số tuổi âm");

System.out.println("Đã tạo ngoại lệ");
System.out.println(problem.getMessage());
System.out.println("Vẫn chạy bình thường");
~~~

Output when the snippet above is executed:

~~~text
Đã tạo ngoại lệ
Số tuổi âm
Vẫn chạy bình thường
~~~

There is no `throw` line, so `problem` remains just an object. Calling `getMessage()`, passing the object to another method, or returning the exception object is also **not equivalent to throwing** it.

**Note on accuracy:** a `new` expression may still fail to complete normally if the constructor or class initialization raises another error; normally, a `new IOException("...")` expression that succeeds only creates the object. You must not infer that every `new` expression is strictly incapable of throwing any exception.

## 2. In what order does Java execute `throw new ...`?

Consider the statement:

~~~java
throw new IllegalStateException("Không kết nối được");
~~~

Semantically, there are two phases:

1. **Evaluating the expression to the right of `throw`:** Java instantiates the `IllegalStateException` object with the given message string (and executes the corresponding constructor logic).
2. **Executing the `throw` statement:** if the expression evaluates to a non-`null` exception object reference, Java throws that object; the statement completes abruptly, leaving the normal execution flow.

The two snippets below behave identically in throwing the same exception type if creation completes:

~~~java
// Approach 1: create and throw in the same statement.
throw new IllegalStateException("Không kết nối được");
~~~

~~~java
// Approach 2: create first, then throw the existing object.
// Both lines are inside a method.
IllegalStateException error =
        new IllegalStateException("Không kết nối được");
throw error;
~~~

However, **the time of creation** can differ. In approach 2, other processing can occur between `new` and `throw`; the exception object may have already been passed elsewhere, stored, and had its stack trace recorded beforehand. Creating a new object on each `throw new` is also different from rethrowing the same existing object.

## 3. Complete Java 17+ program: create first, throw later

Create the file `CreateVsThrowDemo.java`:

~~~java
public class CreateVsThrowDemo {
    static IllegalArgumentException prepare() {
        System.out.println("1. Tạo ngoại lệ");
        return new IllegalArgumentException("tuổi phải >= 0");
    }

    static void validate(int age, IllegalArgumentException prepared) {
        System.out.println("3. Bắt đầu kiểm tra");
        if (age < 0) {
            throw prepared;
        }
        System.out.println("Tuổi hợp lệ");
    }

    public static void main(String[] args) {
        IllegalArgumentException prepared = prepare();
        System.out.println("2. Đã tạo, chương trình vẫn chạy");
        try {
            validate(-1, prepared);
            System.out.println("Không in dòng này");
        } catch (IllegalArgumentException ex) {
            System.out.println("4. Đã bắt: " + ex.getMessage());
            System.out.println("5. Cùng đối tượng: " + (ex == prepared));
        }
        System.out.println("6. Kết thúc bình thường");
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 CreateVsThrowDemo.java
java CreateVsThrowDemo
~~~

**Exact output:**

~~~text
1. Tạo ngoại lệ
2. Đã tạo, chương trình vẫn chạy
3. Bắt đầu kiểm tra
4. Đã bắt: tuổi phải >= 0
5. Cùng đối tượng: true
6. Kết thúc bình thường
~~~

Step-by-step analysis:

1. `prepare()` creates an `IllegalArgumentException` and **returns the exception object itself**. Returning a `Throwable` is valid in the language and does not cause the program to throw an exception.
2. `main()` still executes print statement number 2, proving the program has not transferred to exception handling yet.
3. `validate(-1, prepared)` starts; the condition `age < 0` is true, so `throw prepared;` is executed.
4. `validate()` completes abruptly at `throw`. The statement `System.out.println("Tuổi hợp lệ")` does not run; the print statement `Không in dòng này` in `main()` is also skipped.
5. The `catch (IllegalArgumentException ex)` block in `main()` receives **the exact prepared object**: the expression `ex == prepared` evaluates to `true`.
6. Because `catch` handled it and completed normally, the program continues after the `try/catch` construct.

If you change `validate(-1, prepared)` to `validate(18, prepared)`, the `throw` branch does not run; the created exception remains just an object. This shows that **creating an object is not synonymous with an error actually occurring**.

## 4. `throw` alters control flow; an ordinary `new` does not

The following snippets have different meanings:

~~~java
// A. Create an object and discard the returned reference.
new IllegalArgumentException("Sai dữ liệu");
System.out.println("Vẫn đến đây");
~~~

~~~java
// B. Throw, if the snippet is placed inside a method.
throw new IllegalArgumentException("Sai dữ liệu");
~~~

Case A compiles when placed in an appropriate method and still prints `Vẫn đến đây`. Case B causes the method to complete abruptly if there is no immediate handling mechanism in the enclosing context.

Another example illustrates that statements after `throw` are only skipped in **the branch that is actually taken**:

~~~java
// Illustration snippet inside a method.
if (age < 0) {
    throw new IllegalArgumentException("Tuổi âm");
}
System.out.println("Đã qua bước kiểm tra");
~~~

When `age < 0`, the print statement is not executed. When `age >= 0`, there is no `throw`, so the print statement runs normally.

If you place a normal statement immediately after an unconditional `throw` in the same block with no other branch, the compiler may report `unreachable statement`:

~~~java
// Invalid illustration; DOES NOT compile when placed in a method.
throw new IllegalArgumentException("Lỗi");
System.out.println("Không thể tới đây");
~~~

When an exception is thrown, Java searches for a matching `catch` in the dynamically enclosing `try` blocks. If none is found, the exception continues propagating up the active call stack. However, this is a consequence of **`throw`**, not of object creation.

## 5. What type must `throw` accept?

According to the Java Language Specification, the operand of a `throw` statement must be an expression of a reference type compatible with `Throwable`; the case of throwing a `null` reference is resolved according to specific runtime rules.

Valid examples:

~~~java
throw new IllegalArgumentException("Không hợp lệ");
~~~

~~~java
// Illustration snippet inside a method that has a Throwable variable problem.
throw problem;
~~~

Invalid case:

~~~java
// Does not compile: String is not a Throwable.
throw new String("Lỗi");
~~~

You cannot use `throw 5;`, `throw "Lỗi";`, or `throw new Object();` to trigger exception handling. You must throw an object belonging to a subclass of `Throwable`, such as a custom exception class extending `Exception` or `RuntimeException`.

**When the expression of `throw` evaluates to `null`:**

~~~java
// Illustration snippet inside a method.
RuntimeException problem = null;
throw problem;
~~~

The snippet above **compiles**; at runtime, executing `throw` with a `null` reference causes a `NullPointerException`. This is neither "throwing nothing" nor falling through past the `throw` line.

For clear error handling, you should ensure the reference to be thrown is non-`null`, or directly create an exception appropriate for the situation.

## 6. Do not confuse `throw` with `throws`

The two keywords differ by only one letter, yet serve two different purposes:

- `throw expression;` is an **executable statement**: it throws an exception object evaluated from the expression.
- `throws Type1, Type2` is a **declaration in a method/constructor signature**: it describes the checked exception types that the method may let escape, and may also list unchecked ones if desired.

Valid example with a checked exception:

~~~java
import java.io.IOException;

// Illustration snippet placed inside a class.
static void failRead() throws IOException {
    IOException failure = new IOException("Không đọc được tệp");
    throw failure;
}
~~~

Here:

1. `new IOException(...)` only creates the `IOException` object, even though its type itself is a checked exception.
2. `throw failure;` **throws a checked exception**, so the method must catch or declare `IOException` (or an appropriate supertype).
3. `throws IOException` on the signature communicates that requirement to the caller. The caller of `failRead()` must in turn catch or declare it when needed.

However, the following method **compiles without `throws IOException`**:

~~~java
import java.io.IOException;

// Illustration snippet placed inside a class.
static IOException prepareFailure() {
    return new IOException("Không đọc được tệp");
}
~~~

Because it **returns an `IOException` object**, it does not throw that object. A return type of `IOException` does not mean the method will complete abruptly.

Caller example:

~~~java
// Illustration snippet inside a method.
IOException prepared = prepareFailure();
System.out.println(prepared.getMessage()); // Only reads the message.
~~~

The caller does not have to declare `throws IOException` merely for receiving an object whose class is a checked exception. The catch-or-declare rule applies to **the possibility of a checked exception escaping**, not to every place where a variable of type `Exception` is instantiated.

## 7. Catching and rethrowing: same object or new object?

`catch` receives a reference to the thrown exception. You can:

1. Handle it and complete the `catch` block normally — propagation of that exception ends.
2. Rethrow the same object with `throw ex;`.
3. Create a new exception and throw it with `throw new ...;`, usually keeping the old exception as the **cause**.

Same-object example:

~~~java
// Illustration snippet inside a method compatible with unchecked exceptions.
try {
    performTask();
} catch (IllegalStateException ex) {
    System.err.println("Gặp sự cố trong performTask");
    throw ex; // Rethrows the same reference, without creating a new object.
}
~~~

Rethrowing with `throw ex` does not automatically add a `Caused by` layer; it is still the same `Throwable` object. If an upper layer catches it again, comparing references with `==` can still yield `true`.

In contrast:

~~~java
// Illustration snippet inside a method compatible with unchecked exceptions.
try {
    performTask();
} catch (IllegalStateException ex) {
    throw new IllegalStateException("Tác vụ không hoàn thành", ex);
}
~~~

The expression `new IllegalStateException(..., ex)` creates a **different object** and sets `ex` as its cause. The `throw` statement throws this new object; `getCause()` lets you trace back to the old exception. When printing the stack trace, there is typically a `Caused by:` section showing the root cause.

You should avoid catching an exception and creating a new one **without passing `cause`**, as doing so easily loses the diagnostic path to the original error.

For checked exceptions, compile-time rules still apply when rethrowing: the method must declare or handle the checked exception types that may escape. Java has **precise rethrow analysis** in certain `catch` cases since Java 7, allowing the compiler to infer the rethrown checked type more accurately; this does not change the fundamental difference between creating and throwing.

## 8. Which point in time is the stack trace attached to?

A subtle point: with standard `Throwable` constructors, **the stack trace is recorded when the exception object is created**, rather than being automatically recaptured at each `throw` line. Therefore, if you create it in method A and later throw it in method B, the default stack trace may start at A.

Standalone program `TraceCreationDemo.java`:

~~~java
public class TraceCreationDemo {
    static IllegalStateException createProblem() {
        return new IllegalStateException("sự cố");
    }

    static void throwProblem(IllegalStateException problem) {
        throw problem;
    }

    public static void main(String[] args) {
        IllegalStateException problem = createProblem();
        try {
            throwProblem(problem);
        } catch (IllegalStateException ex) {
            System.out.println("Cùng đối tượng: " + (problem == ex));
            System.out.println("Frame đầu: " + ex.getStackTrace()[0].getMethodName());
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 TraceCreationDemo.java
java TraceCreationDemo
~~~

Stdout for a standard `IllegalStateException` object:

~~~text
Cùng đối tượng: true
Frame đầu: createProblem
~~~

**Explanation:** `createProblem()` constructed the exception and recorded the stack trace; `throwProblem()` only threw the existing reference. The JVM does not automatically replace the trace with the call path to `throwProblem()` each time the object is thrown.

Cases to be aware of:

- `throw new IllegalStateException(...)` performs creation right next to the throw point, so the top of the trace usually matches the `throw new` statement.
- `throw oldException;` can retain the trace from when `oldException` was previously created. Reusing a single exception object to throw multiple times often produces inaccurate error-location information for subsequent occurrences.
- `Throwable.fillInStackTrace()` can update the trace information to the current stack; this is an explicit operation, not something that happens by default on every `throw`.
- Some custom `Throwable` types may disable a writable stack trace, or an application may actively modify the stack trace via APIs. Thus, the example above regarding the first element of `getStackTrace()` assumes a standard Java object with an enabled stack trace.

In application design, it is generally best to **create an exception when the error is actually detected**, so that the trace reflects a meaningful location. Separate creation and throwing only when there is a clear reason; do not pre-create a shared exception for multiple requests or threads and expect the stack trace to accurately reflect each error event.

## 9. Why sometimes only create, and not throw?

An exception can be created or stored as a data object in specialized scenarios:

- A code layer prepares context for an error and passes the object to another layer to decide whether to throw it.
- An asynchronous result may **store an exception object** as the cause of failure. The receiver observes the failure state or a wrapper exception when retrieving the result; you should not equate the time of storing the object with the time another thread throws an exception.
- A diagnostic API may hold a `Throwable` to capture the stack at a specific moment, though such creation has a cost and should be purposeful.

Even though valid, using `return new IOException(...)` instead of throwing an exception is usually **not idiomatic Java error-handling style**. It can mislead the caller into thinking the operation succeeded. If an API intends to return errors as data, the contract should clearly specify the result type and usage, rather than mixing `Exception` with success data.

Conversely, a method declaring `throws` does not necessarily throw an exception on every invocation. `throws` indicates possibility, whereas the `throw` statement only executes when the execution path actually reaches it.

## 10. Custom exceptions: a constructor does not replace `throw`

You can define your own exception class by extending `Exception` (checked) or `RuntimeException` (unchecked):

~~~java
// Illustration snippet is a standalone Java class.
class InvalidOrderException extends Exception {
    InvalidOrderException(String message) {
        super(message);
    }
}
~~~

The following two operations have different outcomes:

~~~java
// Illustration snippet inside a method.
InvalidOrderException problem = new InvalidOrderException("Đơn hàng trống");
// Only creates and stores; does not trigger exception-handling flow.
~~~

~~~java
// Illustration snippet inside a method with throws InvalidOrderException.
throw new InvalidOrderException("Đơn hàng trống");
// The method completes abruptly and the caller must catch or declare it.
~~~

The `InvalidOrderException(String)` constructor only prepares the object's state and calls `super(message)`. `extends Exception` by itself does not cause `new InvalidOrderException(...)` to be thrown automatically. Nor should you add `throw this` inside the constructor; that is not the proper way to define an exception class.

Name exceptions after meaningful failures and use checked/unchecked consistently with the API contract. Regardless of whether it is checked or unchecked, **successful instantiation** remains distinct from **throwing**.

## 11. Notes on error design and diagnostics

| Common mistake | Consequence | How to understand / fix |
| --- | --- | --- |
| Writing only `new Exception("Lỗi");` and believing the program reports an error | The object is created and may be discarded; execution continues. | Use `throw new ...` when you need to trigger exception flow. |
| Using `return new Exception(...)` and believing the caller must `catch` | Returning a value normally does not require `catch`. | Return errors as data only when the API explicitly specifies it; for a checked failure, use `throw`/`throws`. |
| Confusing `throw` with `throws` | Declaring a signature expecting the runtime to throw automatically. | `throw` is a statement; `throws` is a declaration. |
| Throwing `String`, `Object`, or a numeric type | Compilation error due to incompatibility with `Throwable`. | Use an object of a subclass of `Throwable`. |
| `throw null` thinking it skips throwing | Causes `NullPointerException` at runtime. | Ensure the reference is non-`null` or create an appropriate error. |
| Reusing a pre-created exception and throwing it multiple times | The trace may point to the creation time, making it hard to locate the new failure. | Typically create a new exception at the point where the error occurs. |
| Catching an old error and doing `throw new ...` while omitting `cause` | Loses the causal relationship needed for debugging. | Use the `(message, cause)` constructor when wrapping. |
| Logging and then `throw`ing at every layer | A single error can produce multiple duplicate and noisy logs. | Propagate appropriately, and log at a suitable monitoring boundary. |
| Placing a normal statement immediately after an unconditional `throw` | May trigger an `unreachable statement` error. | Reorganize conditional branches and return paths. |

A note on performance: creating a standard `Throwable` object may require collecting a stack trace, so it **should not be abused merely for normal control flow**. When invalid input is genuinely a failure condition under the contract, throwing a clear exception is appropriate; for predictable outcomes that occur frequently, consider an appropriate return type or conditional check.

## 12. Self-check questions

**Question 1.** For the snippet `IOException e = new IOException("x");`, is the method required to declare `throws IOException`?

**Answer:** No, if it only creates the object and there are no other calls that throw a checked exception. Creating an `IOException` object is not synonymous with throwing it.

**Question 2.** Are `throw e;` and `throw new IOException("x");` always identical?

**Answer:** Both throw an object if they succeed, but the first rethrows the referenced object, while the second creates a new object before throwing. They differ in object identity, time of creation, and stack trace information.

**Question 3.** An exception is created in `make()`, then thrown in `send()`. Where can the default stack trace start?

**Answer:** For a standard `Throwable`, at `make()` — where the object was created, unless the trace was refreshed or modified.

**Question 4.** If `throw new IllegalArgumentException(...)` executes, does a normal statement immediately after it in the same branch run?

**Answer:** No. `throw` completes abruptly, unless control flow is handled in an appropriate enclosing context and the program continues from the point after the handling construct.

**Question 5.** What does throwing a `null` reference do?

**Answer:** `throw null` causes a `NullPointerException` at runtime.

**Question 6.** Does `catch (Exception ex) { throw ex; }` create a new exception?

**Answer:** No; it is the same `ex` object. For checked exceptions, the compiler also applies the `throws` rules and may perform precise rethrow analysis.

**Question 7.** If you want to create new error context while preserving the original error, what should you write?

**Answer:** Use a constructor that accepts a cause, for example `throw new IllegalStateException("Nạp cấu hình thất bại", ex);`.

## References

- [Java Language Specification 17, §14.18 — The `throw` Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.18): thrown expression, semantics of throwing `null`, abrupt completion.
- [Java Language Specification 17, §11.2 — Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): checked exceptions and the catch-or-declare rules.
- [Java Language Specification 17, §15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): semantics of creating objects with `new`.
- [Java SE 17 API — `Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): constructors, cause, stack trace, `fillInStackTrace()`.
- [Java SE 17 API — `IllegalArgumentException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalArgumentException.html): illustrative unchecked exception.

**Key takeaway:** `new SomeException(...)` creates an object carrying error information; `throw exception;` is what uses that object to transfer control flow to the exception-handling mechanism. `throw new SomeException(...);` combines both, whereas `throws SomeException` only declares the method contract.
