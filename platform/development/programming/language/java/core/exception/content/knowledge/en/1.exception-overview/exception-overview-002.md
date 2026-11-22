# Distinguishing Compile-Time Errors, Runtime Failures, and Business Outcomes in Java

A Java program can **fail to compile**, **compile successfully but fail at runtime**, or **run properly and return a business outcome that is not what the user hoped for**. These three situations differ in when they occur, their causes, how they are represented, and whose responsibility it is to handle them. In the Java Core – Exception topic, distinguishing them is the first step in deciding when to fix source code, when to handle an exception, and when to simply check a normal result.

## 1. Three Types of Situations Seen from the Program Lifecycle

| Perspective | Compile-time error | Runtime failure | Business outcome |
| --- | --- | --- | --- |
| Timing | When `javac` checks/compiles source code | While the program is executing | When business logic makes a decision at runtime |
| Example | Assigning a `String` to an `int`; using an undeclared variable; not handling a checked exception | `NullPointerException`; unreadable configuration file; database connection failure | Order out of stock; wrong login password; application ineligible |
| Can a new compiled build be produced? | No, for the failing source part | Possibly yes; the error appears during execution | Yes; the program can run completely properly |
| Does Java require throwing an exception? | No: the compiler reports an error | Not every failure throws an exception; many errors have an exception or `Error` | No: can be represented by a return value or status |
| Primary response | Fix code, data types, syntax, declarations, or dependencies | Diagnose cause, recover if feasible, or propagate the error across an appropriate boundary | Handle the business branch and notify the user appropriately |
| Is it always a bug? | Usually a code/compile-setup error that needs fixing | Can be a bug, invalid data, environment incident, or anticipated situation | No: "out of stock" can be a completely correct decision by the system |

It is also necessary to distinguish a **business outcome** from a **logic bug**: if the system is supposed to deduct 10 points but deducts 100 points without throwing an exception, the program may still run to completion. That is a runtime correctness bug, not a valid business outcome simply because no exception was thrown.

A simplified cycle:

1. Write `.java` source code and run `javac`. If compilation fails, fix the code or build configuration before you can run a new build.
2. Run the bytecode with `java`. At runtime, exceptions, environment errors, program hangs, or wrong values can occur.
3. If the technical operation succeeds, business rules can still return "accepted", "rejected", "out of stock", "not eligible", etc.

A real-world application can compile successfully, process thousands of requests normally, and then encounter a runtime error on just one specific request. Conversely, a request rejected due to a business rule can be processed completely successfully.

## 2. Compile-Time Errors: The Program Is Rejected Before Running

The Java compiler checks syntax and many static rules: variable names, data types, member accessibility, certain return paths, and the obligation to handle or declare **checked exceptions**. For example, the file `CompileDemo.java`:

```java
public class CompileDemo {
    public static void main(String[] args) {
        int quantity = "3"; // Wrong: String does not automatically convert to int
        System.out.println(quantity);
    }
}
```

Run:

```bash
javac CompileDemo.java
```

The command fails with a message about **incompatible types**; the exact wording and diagnostic formatting depend on the `javac` version. This is not a `ClassCastException` at runtime. The error occurs because the compiler detected an invalid assignment. One fix is `int quantity = 3;`; if the value actually comes from text, a conversion such as `Integer.parseInt(text)` can instead encounter an exception **at runtime** if the text is not a valid integer.

A situation related to exceptions:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

class CheckedExample {
    static String load(Path file) throws IOException {
        return Files.readString(file);
    }

    static void show() {
        String data = load(Path.of("config.txt")); // Compile-time error
        System.out.println(data);
    }
}
```

`Files.readString` can throw `IOException`, which is a checked exception. The `show()` method must either **catch** it with `try/catch` or **declare** `throws IOException` (or an appropriate supertype). If you change the signature to `static void show() throws IOException`, the code can compile; that **does not guarantee** the file exists or that reading will succeed. `throws` only clarifies the exception propagation contract; it does not handle the cause at runtime.

**Limitations of the compiler:** successful compilation does not prove business logic is correct, does not guarantee valid input data, does not guarantee network availability, and does not eliminate `NullPointerException`. Conversely, compiler warnings are not equivalent to errors that force `javac` to stop. Errors caused by missing libraries on the compile classpath or an incompatible JDK version can also cause a build to fail, even though they are not logic errors in individual Java statements.

## 3. Runtime Failures: Valid Code That Does Not Complete as Intended

Example file `RuntimeDemo.java`:

```java
public class RuntimeDemo {
    public static void main(String[] args) {
        System.out.println("Bắt đầu chuyển đổi");
        int quantity = Integer.parseInt("abc");
        System.out.println("Số lượng: " + quantity);
    }
}
```

Compile and run with Java 17 or later:

```bash
javac -encoding UTF-8 RuntimeDemo.java
java RuntimeDemo
```

`javac` compiles successfully. When run, **stdout** prints:

```text
Bắt đầu chuyển đổi
```

Then `Integer.parseInt("abc")` throws `NumberFormatException` because the string does not represent a valid decimal integer. There is no `catch` handling it, so the exception escapes `main`; the JVM prints the exception details and stack trace to **stderr**, and the `"Số lượng"` print statement is not executed. You do not need to predict every line of the stack trace because details may vary by JDK version.

Common forms of runtime failure:

- **Data or precondition errors:** `NumberFormatException`, `IllegalArgumentException`, many `NullPointerException` cases. The cause may lie in unexpected data or a caller bug.
- **I/O and external resources:** `IOException` when reading/writing, connection failures, timeouts. You need to know whether the operation can be safely retried.
- **State/concurrency:** `IllegalStateException`, resource contention, deadlocks, race conditions. A deadlock can cause a program to hang **without throwing an exception**.
- **Environment limits:** running out of memory can lead to `OutOfMemoryError`; `Error` usually indicates a problem that normal business flow cannot safely handle on its own.
- **Silent logic errors:** ordinary `int` integer overflow does not automatically throw an exception; the program can still return a wrong value.

In Java, `Throwable` is the root of `Exception` and `Error`. Two common groups within `Exception` are **checked exceptions** (such as `IOException`) and **unchecked exceptions** (subclasses of `RuntimeException`, such as `NumberFormatException`). Subclasses of `Error` are also not checked exceptions. You should not infer that "checked = always recoverable" or "unchecked = always a bug": recoverability is determined by context and the method's contract.

`try/catch` only works when the program has reached a corresponding exception at runtime. It does not catch syntax or type errors rejected by `javac`; nor does it automatically detect deadlocks, wrong results that throw no exception, or every severe JVM failure.

## 4. Business Outcomes: A Rejection Can Still Be Successful Processing

Consider an order placement operation. If a customer requests 7 items but the warehouse only has 5 left, "insufficient stock" is an **expected state** of the business rule. It does not require a Java error; the caller needs to know whether to suggest reducing the quantity, report out of stock, or stop the checkout flow. Similarly: wrong password, order exceeding limit, expired coupon, or ineligible account are foreseeable business branches.

A clear way to represent this is to return a result object with a status code. The `CheckoutDemo.java` file below runs standalone on Java 17+:

```java
public class CheckoutDemo {
    enum Status {
        PLACED, OUT_OF_STOCK, INVALID_QUANTITY
    }

    record CheckoutResult(Status status, String message) {}

    static CheckoutResult placeOrder(int quantity, int stock) {
        // stock is managed by the system: a negative value violates a technical precondition.
        if (stock < 0) {
            throw new IllegalArgumentException("Tồn kho không được âm");
        }

        // quantity comes from the user request: reject according to business rules.
        if (quantity <= 0) {
            return new CheckoutResult(
                    Status.INVALID_QUANTITY, "Số lượng phải lớn hơn 0");
        }
        if (quantity > stock) {
            return new CheckoutResult(
                    Status.OUT_OF_STOCK, "Không đủ tồn kho");
        }
        return new CheckoutResult(Status.PLACED, "Đặt hàng thành công");
    }

    public static void main(String[] args) {
        System.out.println(placeOrder(2, 5));
        System.out.println(placeOrder(7, 5));
        System.out.println(placeOrder(0, 5));

        try {
            placeOrder(1, -1);
        } catch (IllegalArgumentException e) {
            System.out.println("Lỗi dữ liệu hệ thống: " + e.getMessage());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 CheckoutDemo.java
java CheckoutDemo
```

**Exact stdout** in a UTF-8 display environment:

```text
CheckoutResult[status=PLACED, message=Đặt hàng thành công]
CheckoutResult[status=OUT_OF_STOCK, message=Không đủ tồn kho]
CheckoutResult[status=INVALID_QUANTITY, message=Số lượng phải lớn hơn 0]
Lỗi dữ liệu hệ thống: Tồn kho không được âm
```

Points to note:

- All three initial outcomes return normally from `placeOrder`, including `OUT_OF_STOCK` and `INVALID_QUANTITY`. The caller handles them via `status()` without needing `catch`.
- In this example, `stock` is internal data assumed to be valid. A negative value represents a **violation of the caller/system data contract**, so `IllegalArgumentException` is a deliberate choice. If negative stock were an allowed business case in another system, the classification and representation would be different.
- Using `record` simply creates a concise result data type that is immutable at the reference level of its components for the example; it is not a rule that every business outcome must use `record`.
- Running successfully does not mean "order placed successfully": a successful **technical operation** can return a rejected **business decision**.

If a quantity input screen is a place where users can mistype, invalid data should usually be validated and returned as a structured result. If a library API specifies that an argument must be positive and a programmer calls it violating the contract, `IllegalArgumentException` may be appropriate. **The data source, expectations, and contract between layers** determine how to handle it; not the exception type alone.

## 5. Do Not Equate Exceptions with "Business Errors"

The name of a class does not by itself determine how the system interprets it. For example, `NumberFormatException` is an exception that occurs at runtime, yet:

- When a user enters `"abc"` into a "quantity" field, the input layer can catch the conversion error and return the message "Quantity must be an integer" as an **expected validation outcome**.
- When a service reads `"abc"` from a configuration file that must contain a number, the same exception can indicate **corrupted configuration data**, causing the technical operation to fail.
- If code already validated the data as numeric earlier yet still fails to parse it, there may be a **bug or contract mismatch between layers**.

Similarly, "record not found" can be a normal outcome of a search feature, or an abnormal error if the application is updating a record whose existence was just confirmed. Some projects use `Optional`, status codes, `Result`/`Either`, or a **domain exception** for this case; what matters is a consistent contract so the caller knows exactly how to handle it.

A custom-defined business exception **is still a Java exception raised at runtime** when thrown; it does not turn into a "compile-time error", nor does it prove the program hit a technical failure. You must distinguish the **signaling mechanism** (throw/catch vs. return) from the **event meaning** (expected outcome vs. abnormal failure).

## 6. Choosing the Representation and Handling Location

Common options:

| Situation | Usually reasonable representation | Reason |
| --- | --- | --- |
| Expected business condition: out of stock, expired discount, missing eligibility | Typed result, status, or explicit domain branch | The caller must make a normal decision |
| Search operation that may yield no data | `Optional<T>` if only presence/absence is needed; a dedicated result type if a reason is needed | Avoids using exceptions as ordinary control flow |
| Programmer-supplied argument violating API precondition | `IllegalArgumentException` or `NullPointerException` per contract | Signals that the caller misused the API |
| Unable to read file, external service call failure | Appropriate exception with context; handled where a recovery strategy exists | The error cannot be ignored as a successful outcome |
| Violation of internal invariant or disallowed state | `IllegalStateException` or corresponding exception type | Signals the program is in an invalid state |
| Business logic needs both success and multiple rejection reasons | `enum` + `record`, sealed hierarchy, or explicit result type | Helps callers handle all branches exhaustively |

There is no rule saying "every failure must throw an exception" or "never use domain exceptions". When rejection is a frequent branch, using a return value is often easier to read, easier to test, and less likely to make callers mistake it for an infrastructure error. When a method cannot fulfill its contract or wants to abort an abnormal flow quickly, an exception can be appropriate. If you choose a domain exception, document clearly which types may occur, where they are caught, how they are translated into responses, and whether the system needs to roll back.

For checked exceptions, `catch` when the current layer can genuinely recover, take an alternative path, or translate it into a meaningful error. If the current layer lacks sufficient information, it can declare `throws` (if the contract allows) or wrap and rethrow with the cause:

```java
try {
    return Files.readString(path);
} catch (IOException cause) {
    throw new IllegalStateException("Không thể nạp cấu hình: " + path, cause);
}
```

This is an **illustrative snippet inside a method** that already has a `path` variable of type `Path` and the necessary `import`s; it is not a standalone program. Preserving `cause` helps diagnose the root cause. Translating to an unchecked exception is only appropriate if this layer cannot handle it locally and the API contract permits it; do not use it merely to evade the obligation to handle checked exceptions.

Do not catch and ignore an exception, return `null`, or return a fake "success":

```java
// Anti-pattern: data reading error is hidden.
try {
    return Files.readString(path);
} catch (IOException e) {
    return ""; // Cannot tell whether the file is actually empty or reading failed.
}
```

If an empty string is a **clearly specified and safe** fallback in the business logic, it may be used; otherwise, this approach erases the distinction between valid data and a failure.

## 7. Layer Boundaries and How to Report to Users

In a multi-layered application, where an exception **originates** may differ from where the **response** is decided:

1. **Input layer:** validates user data; returns a list of field errors if that is an expected branch.
2. **Business layer:** executes rules; returns `PLACED`/`OUT_OF_STOCK` or an equivalent domain outcome.
3. **Integration layer:** detects file, network, or database errors; throws an exception with sufficient context without leaking sensitive information.
4. **Interface/API layer:** translates results/exceptions into protocol responses, logs necessary diagnostic details, and preserves business meaning.

Example in an HTTP API (only a design suggestion, **not a Java rule**):

| Event | Potentially appropriate response |
| --- | --- |
| User submits invalid quantity | `400 Bad Request`, with input error description |
| Order rejected due to insufficient stock | `409 Conflict` or a domain status code in the response body, depending on the API contract |
| Lookup by ID returns no result | `404 Not Found` if the URI represents a nonexistent resource |
| Data store temporarily unreachable | `503 Service Unavailable` if transient, or an appropriate 5xx code |
| Unhandled internal bug | `500 Internal Server Error`, avoiding exposing stack traces to users |

`400`, `404`, `409`, `500` only describe the HTTP service contract; **they are not Java exception types**. An API can return a 4xx code even when Java throws no exception; conversely, an exception caught and translated into an appropriate input error does not need to crash the application.

Do not mechanically turn every exception into `500`, nor automatically turn every technical error into a "business rejection". A response can carry an error code for the user while keeping internal technical traces for investigation.

## 8. Practical Diagnostic Workflow

When you see an "error" message, follow these questions in order:

1. **Did `javac`/build fail?** Read the file, line, symbol name, data type, API, imports, and build configuration. If the error appears before running a new build, handle it in the compilation phase.
2. **Did the program run and throw an exception/`Error`?** Read the **exception type**, message, `cause`, and stack trace from the failure point to the call site. Identify the inputs, state, and resources at the time it occurred.
3. **No exception, yet behavior is still wrong?** Compare actual output against the specification; check boundary cases, data, and calculations. This may be a logic bug or concurrency bug; do not assume it is a valid business outcome.
4. **Did it return an expected rejection status?** Check against business rules: for example, `OUT_OF_STOCK` when `requested > available` is a correct outcome. Handle it in the caller with a message or next action.
5. **How is the event translated across layers?** An exception thrown internally may have been caught and converted into a result; trace both the original cause and the external contract before classifying.

Especially for runtime errors: retrying usually makes sense when the error is **transient** and the operation is **safe to repeat** (consider idempotency, transactions, and side effects). Do not automatically retry an order when you do not know whether the previous attempt was recorded successfully. An `OUT_OF_STOCK` result will not turn into a success just by retrying immediately multiple times.

## 9. Testing Three Different Layers of Behavior

- **Compilation checks:** run build/`javac` to catch syntax errors, type errors, missing libraries, and unhandled checked exceptions. A passing build is a necessary condition, not a sufficient one.
- **Runtime failure testing:** supply data or an environment that triggers expected errors (invalid numbers, missing files, temporarily unavailable external services) and verify the appropriate exception/handling path/logging. Distinguish expected exceptions in tests from exceptions that escape and fail the test.
- **Business testing:** verify multiple normal branches such as sufficient stock, out of stock, zero quantity, and boundary data; compare statuses and messages rather than only checking "no exception thrown".
- **Correctness testing:** check computed values, edge cases, and side effects, because wrong results may not produce exceptions.

With `CheckoutDemo`, the first three calls cover the three outcome branches; the call with `stock = -1` tests a violated precondition. In real production code, you also need tests for quantities near the stock boundary, invariants, and consistency under concurrent order requests.

## 10. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "If it compiles, the code has no bugs." | Java only checks part of the program statically; logic, resource, and data errors appear at runtime. |
| "Compile errors can be fixed with `try/catch`." | `try/catch` only works for runtime exceptions; you must fix code/configuration for `javac` to accept it. |
| "Adding `throws` means the error is handled." | `throws` declares propagation capability; the caller or top-level boundary still needs a handling policy. |
| "A rejected order means a server error." | If rejected according to expected rules, it can be a correct business outcome. |
| "Every exception is a programming bug." | Some exceptions stem from I/O, invalid input data, or environment conditions; evaluate according to the contract. |
| "No exception means success." | The program can hang, miscalculate, or return a valid rejection status. |
| "Catching `Exception` and returning `true` is safe." | It hides the error, loses the cause, and emits a false success signal. |
| "Use `catch (Throwable)` for everything." | It can swallow serious `Error`s; avoid using it as general control flow. |

## 11. Quick Self-Classification

1. `int x = "10";` → **Compile-time error** due to incompatible types.
2. Uncaught `Integer.parseInt("xyz")` → **Runtime exception**, type `NumberFormatException`.
3. Ordering 8 items when stock has only 3 left, method returns `OUT_OF_STOCK` → **Expected business outcome**.
4. Order placement returns "success" but the system did not record the order → **Runtime bug or hidden processing failure**, needs investigation; not a true success.
5. Calling a file-reading API declared with `throws IOException` without catching or declaring it → **Compile-time error** at the call site; if the contract is handled but the file still cannot be read, that is a **runtime failure**.
6. A screen asks for quantity, the user types letters; the converter throws `NumberFormatException` and the interface layer returns an input error → **Internal exception**, yet an **expected validation outcome** at the user boundary.

Remember the principle: identify the **phase of occurrence** (compile-time vs. runtime), the **signaling mechanism** (diagnostic, exception, return value), and the **meaning in the contract** (bug/failure vs. expected business branch). These three questions help you design easy-to-use APIs, handle errors at the right layer, and avoid reporting false errors to users.
