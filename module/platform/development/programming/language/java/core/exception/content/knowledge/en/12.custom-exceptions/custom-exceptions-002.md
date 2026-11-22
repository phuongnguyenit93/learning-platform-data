# Choosing `extends Exception` or `extends RuntimeException` When Creating Custom Exceptions in Java

When designing a *custom exception* in Java, the two common declaration patterns are `class MyException extends Exception` and `class MyException extends RuntimeException`. Both create an exception type that can be thrown (`throw`), caught (`catch`), carry a `cause`, and record a stack trace. The most important difference is the **compile-time checking obligation** placed on the caller:

- **Directly `extends Exception`** (or inheriting through a checked subclass) creates a **checked exception**: calling code must catch it or declare its propagation according to the **catch-or-declare** rule.
- **`extends RuntimeException`** creates an **unchecked exception**: calling code is not forced by the compiler to catch or declare it, even though the exception can still cause the operation to fail at runtime.

This is a decision about **API contracts, caller responsibility, software evolution, and error expression**, not merely about adding or omitting the `throws` keyword. There is no mechanical rule such as "business errors are checked, technical errors are unchecked" or "recoverable is checked, unrecoverable is unchecked" that applies accurately to every system.

This article covers the language mechanism, situational selection criteria, runnable Java 17 examples, inheritance/overriding contracts, wrapping and causes, handling at application boundaries, API compatibility impacts, testing, and common design mistakes.

## 1. Understanding the `Throwable` Hierarchy

Simplified diagram:

```text
java.lang.Throwable
├── java.lang.Error                         (unchecked)
│   └── ...
└── java.lang.Exception
    ├── YourCheckedException                 (checked)
    ├── java.io.IOException                  (checked)
    └── java.lang.RuntimeException           (unchecked)
        ├── YourUncheckedException           (unchecked)
        ├── java.lang.IllegalArgumentException
        └── java.lang.IllegalStateException
```

Classification in Java:

| Base class of the new exception | Classification | Is the caller required to `catch` or `throws`? |
| --- | --- | --- |
| Directly `extends Exception` | Checked | Yes, if the call path can throw that exception |
| `extends SomeCheckedException` | Checked | Yes |
| `extends RuntimeException` | Unchecked | No |
| `extends SomeRuntimeException` | Unchecked | No |
| `extends Error` | Unchecked | No, but usually **not** appropriate for business errors |
| Directly `extends Throwable` | Checked | Yes, but usually discouraged because it separates from the standard `Exception` branch |

Note: **`RuntimeException` is itself a subclass of `Exception`**. Therefore, the statement "every subclass of `Exception` is checked" is false; exceptions in the `RuntimeException` branch are not subject to the catch-or-declare requirement.

Most application exceptions should belong to one of the two branches: `Exception` (checked) or `RuntimeException` (unchecked). `Error` is reserved primarily for serious JVM/system-level conditions; you should not choose it just to avoid writing `throws`.

## 2. The Difference Is at **Compile Time**, Not in Runtime Throwing

Minimal declaration syntax:

```java
class DataImportException extends Exception {
    DataImportException(String message) {
        super(message);
    }
}

class InvalidImportRequestException extends RuntimeException {
    InvalidImportRequestException(String message) {
        super(message);
    }
}
```

These are **two illustrative classes**, without a `main` method. Both can be thrown:

```java
throw new DataImportException("Không đọc được dữ liệu");
// or in another scenario:
throw new InvalidImportRequestException("Sai tham số");
```

These are **two independent options**, not placed consecutively in the same code flow.

For the checked `DataImportException`, a method containing the `throw` statement must **catch or declare** it; otherwise, the compiler reports an error. For the unchecked `InvalidImportRequestException`, Java does not require adding `throws` to the signature. However, when thrown, both cause **abrupt completion** of the current execution path and both search for a compatible `catch` handler on the call stack.

**There is no such thing as an unchecked exception being "lighter," "not a real exception," or "not stopping the program."** The difference is a static constraint on calling code; runtime consequences still must be designed and handled.

## 3. Complete Example: Checked Custom Exception That Must Be Handled

Save the file **`CheckedCustomDemo.java`**:

```java
class MissingConfigException extends Exception {
    MissingConfigException(String message) {
        super(message);
    }
}

public class CheckedCustomDemo {
    static String loadConfig(boolean present)
            throws MissingConfigException {
        if (!present) {
            throw new MissingConfigException(
                    "Thiếu cấu hình bắt buộc");
        }
        return "ready";
    }

    public static void main(String[] args) {
        try {
            System.out.println("Kết quả: " + loadConfig(true));
            System.out.println("Kết quả: " + loadConfig(false));
        } catch (MissingConfigException e) {
            System.out.println("Không thể tiếp tục: " + e.getMessage());
        }
        System.out.println("Đã xử lý ở ranh giới main");
    }
}
```

Compile/run on Java 17+:

```bash
javac -encoding UTF-8 --release 17 CheckedCustomDemo.java
java CheckedCustomDemo
```

**Exact stdout** on a UTF-8 console:

```text
Kết quả: ready
Không thể tiếp tục: Thiếu cấu hình bắt buộc
Đã xử lý ở ranh giới main
```

Analysis:

1. `MissingConfigException extends Exception`, so it is **checked**.
2. `loadConfig` has a `throw new MissingConfigException(...)` path, so it declares `throws MissingConfigException`.
3. `main` catches the declared type, decides not to perform the next loading step, and then executes the code after the handler.
4. When the second call throws the exception, `System.out.println("Kết quả: " + loadConfig(false))` is **not** printed: the right-hand expression does not complete.
5. The exception type helps the caller distinguish missing configuration from other failures that the API might report.

If you remove `throws MissingConfigException` from `loadConfig` without catching it there, the code **will not compile**. If you remove `catch` in `main` without adding an appropriate `throws`, `main` will not compile either. `throws` does not catch errors; it only allows the exception to propagate to the caller as part of the contract.

## 4. Complete Example: Unchecked Custom Exception Without Forcing Callers to Write `throws`

Save **`UncheckedCustomDemo.java`**:

```java
class InvalidQuantityException extends RuntimeException {
    InvalidQuantityException(String message) {
        super(message);
    }
}

public class UncheckedCustomDemo {
    static int calculateTotal(int quantity, int unitPrice) {
        if (quantity <= 0) {
            throw new InvalidQuantityException(
                    "quantity phải lớn hơn 0");
        }
        return quantity * unitPrice;
    }

    public static void main(String[] args) {
        System.out.println("Hợp lệ: " + calculateTotal(2, 50));

        try {
            calculateTotal(0, 50);
            System.out.println("Không tới dòng này");
        } catch (InvalidQuantityException e) {
            System.out.println("Không hợp lệ: " + e.getMessage());
        }

        System.out.println("Đã xử lý đầu vào");
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 UncheckedCustomDemo.java
java UncheckedCustomDemo
```

**Exact stdout:**

```text
Hợp lệ: 100
Không hợp lệ: quantity phải lớn hơn 0
Đã xử lý đầu vào
```

`calculateTotal` has no `throws InvalidQuantityException` and still compiles because this exception is unchecked. `main` can still **proactively `catch`** it to turn the error into an appropriate message. Catching an unchecked exception is not forbidden; it is simply **not required by the compiler**.

This is an example of a method precondition. In a system receiving user input, the input layer should generally validate upfront and return a validation result rather than letting input-error exceptions travel across layers. Choosing an exception type does not replace validation flow design.

## 5. The Most Important Design Question: Who Is Responsible for Handling It?

Instead of asking "which error type is more serious?", ask:

**Must the caller be forced by a Java contract to recognize and decide on a declared failure type, or do we want it to propagate and be handled at an appropriate boundary?**

When an API performs an operation with an expected, well-described failure and the caller has valid ways to handle it, a **checked exception can make the contract explicit**. For example, a data reader that must distinguish read errors so it can switch to a fallback source.

When an error represents a precondition violation or invalid state caused by improper calling, an **unchecked exception is usually more appropriate**, allowing code to fail clearly without forcing every intermediate layer to declare or catch a programming error it does not know how to fix.

However, keep in mind:

- An `IOException` is checked even when there are situations that cannot be recovered from.
- An `IllegalArgumentException` is unchecked even though the UI layer might ask the user to fix the input.
- Many frameworks choose unchecked domain exceptions to enable a centralized error-handling boundary.
- A batch system might use checked exceptions for conditions that require the caller to decide whether to retry or skip a record.
- An expected business outcome may be better returned as a **value/result with status**, rather than an exception—whether checked or unchecked.

Therefore, **"whether it is recoverable" is a design signal, not the sole test.**

## 6. When Should You Consider `extends Exception`?

A checked custom exception is useful when the following conditions make sense for the API:

1. **The failure type is a declared part of the method contract.** API users need to recognize a specific condition to decide the next flow.
2. **The caller is responsible for making a choice.** For example, trying a fallback configuration, stopping a task, requesting another option, or reporting an error to the communication layer.
3. **Catching/declaring provides real value**, rather than resulting in empty `catch` blocks written just to silence the compiler.
4. **The error type is stable enough** to be included in API signatures and versioned documentation.
5. **The API scope is controlled.** Propagating the checked exception across multiple abstraction layers does not introduce excessive unnecessary coupling.

Contract example:

```java
static Report importReport(Path file)
        throws ReportFormatException, IOException {
    // Read file; detect invalid format or I/O error.
}
```

This is an **illustrative signature**, without the definitions of `Report`, `ReportFormatException`, or the method body. `ReportFormatException extends Exception` can be a good choice if the caller is expected to distinguish malformed data from I/O errors in order to respond appropriately.

If the caller can only fail and all intermediate layers must catch and rethrow without adding anything, the benefit of a checked exception may be lower than the cost of propagating the contract everywhere.

## 7. When Should You Consider `extends RuntimeException`?

An unchecked custom exception is often useful when:

1. **Programming preconditions are violated**, such as a required input being `null`, a disallowed negative quantity, or calling methods in the wrong sequence.
2. **The current state is unsuitable for performing the operation**, often an invariant or an application-layer meaningful `IllegalStateException`.
3. **Typical callers have no useful local handling action**; the error is forwarded to a monitoring boundary or fixed at the API call site.
4. **The architecture prefers centralized exception handling**, for example at the HTTP/job/controller layer, rather than forcing every service/repository to propagate `throws`.
5. **Internal APIs or callbacks** have constraints regarding checked exceptions; an appropriate unchecked contract is needed instead of misdeclaring or swallowing errors.

Example:

```java
class InvalidWorkflowStateException extends RuntimeException {
    InvalidWorkflowStateException(String message) {
        super(message);
    }
}
```

If an order has already been canceled yet code attempts to complete it, this class can signal a **workflow state violation**. Callers can catch it specifically, but usually the error should be handled at a boundary that understands the overall state.

You should distinguish an **invalid state caused by a bug** from a **normally rejected business request**. For instance, insufficient balance or out-of-stock products can be designed as a stateful domain result instead of throwing an exception. An unchecked exception does not by itself turn an expected outcome into a system error.

## 8. Quick Decision Table

| Scenario | Initial suggestion | Considerations |
| --- | --- | --- |
| Method declares I/O failure and caller needs to decide on fallback | Checked or keep `IOException` | Does catching/declaring at the caller make sense? |
| Utility function receives arguments violating its contract | Unchecked | Should you use the built-in `IllegalArgumentException` or a custom class? |
| Object state is used in the wrong sequence | Unchecked | Is `IllegalStateException` expressive enough? |
| Parser receives an invalid file and caller must handle it specifically | Checked may be appropriate | Is an invalid format an exception or an expected result? |
| User input flow has frequent invalid values | Structured validation result | Avoid using exceptions for normal control flow when unnecessary |
| Service layer converts `IOException` into a domain error | Depends on service contract | Preserve `cause` and choose checked/unchecked based on the API |
| Request handler needs to turn all unexpected errors into safe responses | Usually handled at boundary, may use unchecked | Do not expose stack traces or turn bugs into successes |
| Public library needs to promise specific stable error types | Checked has value in some APIs | Cost of signature evolution / compatibility |
| Incident that may corrupt the JVM / cannot continue | Do not create a custom domain `Error` | Separate recovery/operational policy; do not swallow `Error` |
| Cancellation via `InterruptedException` | Usually propagate the original checked exception | Do not break the interrupt signal for handling convenience |

The table above is a **decision framework**, not a rigid rule. The exception type should reflect **API semantics**, recovery policies, and consistent conventions across the system.

## 9. How Does `throws` on a Checked Exception Affect Callers?

Suppose an API is:

```java
static void exportData() throws ExportFailedException {
    // ...
}
```

with `ExportFailedException extends Exception`. A caller invoking `exportData()` can choose:

**Handle locally:**

```java
try {
    exportData();
} catch (ExportFailedException e) {
    showExportError(e);
}
```

**Propagate:**

```java
static void runExport() throws ExportFailedException {
    exportData();
}
```

These are **independent illustrative snippets**, missing helper method definitions. The first branch fits if the current layer knows how to handle it. The second branch fits if a higher-level caller is responsible. Both demonstrate **catch-or-declare**.

If `ExportFailedException` is changed to `extends RuntimeException`, the compiler no longer forces callers to write a handler or `throws`. However, **the exception can still occur**. API documentation needs to state its meaning and how to respond, rather than relying solely on whether the compiler warns about it.

Do not assume that writing `throws` makes an exception "bubble up" while omitting `throws` makes it "disappear": both checked and unchecked exceptions propagate along the execution path when uncaught; `throws` is checked contract information for checked exceptions.

## 10. Do You Need to Write `throws MyRuntimeException`?

It is not required:

```java
static void validate(int amount)
        throws InvalidQuantityException {
    if (amount <= 0) {
        throw new InvalidQuantityException("amount <= 0");
    }
}
```

This is an **illustrative method** assuming `InvalidQuantityException extends RuntimeException` already exists. The signature `throws InvalidQuantityException` is valid, but **it does not make the compiler force callers to catch it**.

You may choose to include an unchecked exception in `throws` so readers notice special conditions, though this can mislead callers into thinking they must catch it. A clearer option is often **JavaDoc `@throws`** to describe preconditions and semantics:

```java
/**
 * @throws InvalidQuantityException if amount is not positive
 */
static void validate(int amount) {
    if (amount <= 0) {
        throw new InvalidQuantityException("amount <= 0");
    }
}
```

This is an **illustrative snippet**. For public APIs, you should also document unchecked exception types if callers need to know about them for proper usage or boundary handling.

## 11. Should You Create a Custom Class or Use an Existing Exception?

Not every error needs a custom exception. Before choosing between the two inheritance branches, ask: **"Do we need a new type?"**

Existing exceptions may already suffice:

| Meaning | Usually suitable built-in class |
| --- | --- |
| Invalid argument | `IllegalArgumentException` |
| Required argument is `null` | `NullPointerException`, often via `Objects.requireNonNull` |
| Unsuitable object state | `IllegalStateException` |
| String value cannot be parsed as a number | `NumberFormatException` |
| I/O operation failure | `IOException` and specific subclasses |
| Invalid number format entered by user | Can catch `NumberFormatException` at the boundary and convert to a validation result |

Custom exceptions are useful when you need to **distinguish by type** among conditions important to callers, provide stable error codes, or attach module semantics distinct from generic Java types.

Avoid creating classes that differ only by message without routing or testing value—such as `BadInput1Exception` and `BadInput2Exception` with no clear contract. Conversely, if two errors require different recovery policies, separate types can help avoid fragile `if (e.getMessage().contains(...))` checks.

## 12. Designing Constructors Properly: Message, Cause, and Both

A good custom exception typically has minimal constructors matching its contract. Checked example:

```java
public class ReportFormatException extends Exception {
    public ReportFormatException(String message) {
        super(message);
    }

    public ReportFormatException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

This is an **independent class** that must be placed in `ReportFormatException.java` if declared `public`. The key part is that constructors call `super(...)` to preserve the **detail message** and, when present, the **cause**.

Unchecked example:

```java
public class OrderStateException extends RuntimeException {
    public OrderStateException(String message) {
        super(message);
    }

    public OrderStateException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

This is the standalone class `OrderStateException.java`. Whether checked or unchecked, **a cause is not automatically created** if only a message is passed. With `super(message, cause)`, callers can trace it via `getCause()`.

You are not required to provide all four constructors (`()`, `(String)`, `(Throwable)`, `(String, Throwable)`) for every class. Provide only the constructors needed to avoid confusing exception states. If you want to preserve an underlying technical cause, the `(String, Throwable)` form should generally be provided.

## 13. Practical Example: Wrapping `IOException` into a Checked Custom Exception

If a file-reading layer encounters an I/O error but the report-processing API wants to expose **its own error type**, a checked exception wrapper can be used. Save **`CheckedWrappingDemo.java`**:

```java
import java.io.IOException;

class ReportLoadException extends Exception {
    ReportLoadException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class CheckedWrappingDemo {
    static String readRaw() throws IOException {
        throw new IOException("Không đọc được nguồn");
    }

    static String loadReport() throws ReportLoadException {
        try {
            return readRaw();
        } catch (IOException e) {
            throw new ReportLoadException("Không tải được báo cáo", e);
        }
    }

    public static void main(String[] args) {
        try {
            loadReport();
        } catch (ReportLoadException e) {
            System.out.println("Lỗi báo cáo: " + e.getMessage());
            System.out.println("Nguyên nhân: "
                    + e.getCause().getClass().getSimpleName());
            System.out.println("Cause message: "
                    + e.getCause().getMessage());
        }
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 CheckedWrappingDemo.java
java CheckedWrappingDemo
```

**Exact stdout:**

```text
Lỗi báo cáo: Không tải được báo cáo
Nguyên nhân: IOException
Cause message: Không đọc được nguồn
```

The `loadReport` method exposes a checked `ReportLoadException` instead of `IOException`. Callers are required to handle or declare the exposed domain type; `cause` still retains the original exception for diagnostics.

**Wrapping is an abstraction-changing decision**, not merely a trick to "rename an error." If callers still need to handle `IOException` specifically to switch to a fallback source, hiding that type behind a wrapper may not be appropriate. You might choose to keep `throws IOException` or provide structured error codes.

## 14. Practical Example: Wrapping Checked into Unchecked at an Appropriate Boundary

A service layer can expose an unchecked exception by contract so intermediate layers are not forced to propagate a checked exception.

Save **`UncheckedWrappingDemo.java`**:

```java
import java.io.IOException;

class ServiceUnavailableException extends RuntimeException {
    ServiceUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class UncheckedWrappingDemo {
    static void connect() throws IOException {
        throw new IOException("Kết nối bị từ chối");
    }

    static void performService() {
        try {
            connect();
        } catch (IOException e) {
            throw new ServiceUnavailableException(
                    "Dịch vụ chưa sẵn sàng", e);
        }
    }

    public static void main(String[] args) {
        try {
            performService();
        } catch (ServiceUnavailableException e) {
            System.out.println("Service: " + e.getMessage());
            System.out.println("Cause: "
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 UncheckedWrappingDemo.java
java UncheckedWrappingDemo
```

**Exact stdout:**

```text
Service: Dịch vụ chưa sẵn sàng
Cause: IOException
```

`performService` does not need to declare `throws` because it throws `ServiceUnavailableException extends RuntimeException`. Even though the compiler does not force `main` to catch it, a boundary handler can still decide how to report it or fail safely.

Do not overuse **`throw new RuntimeException(e)`** meaninglessly at every layer. Wrapping an exception is only valuable when it expresses a new contract, adds useful context, or satisfies a specific API boundary; preserve `cause` so the original stack trace is not lost.

## 15. A Custom Exception with a Stable Error Code

Messages may change by language or wording; **never use the message text to branch program logic**. A custom exception can provide a stable `errorCode`.

Save **`ErrorCodeDemo.java`**:

```java
enum OrderError {
    INVALID_STATE,
    DUPLICATE_REQUEST
}

class OrderException extends RuntimeException {
    private final OrderError code;

    OrderException(OrderError code, String message) {
        super(message);
        this.code = code;
    }

    OrderError getCode() {
        return code;
    }
}

public class ErrorCodeDemo {
    static void commit(boolean alreadyCommitted) {
        if (alreadyCommitted) {
            throw new OrderException(
                    OrderError.DUPLICATE_REQUEST,
                    "Yêu cầu đã được xử lý");
        }
    }

    public static void main(String[] args) {
        try {
            commit(true);
        } catch (OrderException e) {
            System.out.println("Code: " + e.getCode());
            System.out.println("Message: " + e.getMessage());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 ErrorCodeDemo.java
java ErrorCodeDemo
```

**Exact stdout:**

```text
Code: DUPLICATE_REQUEST
Message: Yêu cầu đã được xử lý
```

An enum enables callers to route handling via **structured error types/codes**, rather than `e.getMessage().contains(...)`. However, business error codes still need to fit the right contract: a valid duplicate request might be better represented by an **idempotent result** or a result type rather than an exception, depending on the system.

Stability of an error code does not mean you can arbitrarily change the semantics of a code without affecting callers. Document the set of supported codes.

## 16. Checked Custom Exceptions and Inheritance / Method Overriding Rules

The checked/unchecked choice affects how interfaces are implemented and methods are overridden:

- When overriding a method, you **cannot declare new or broader checked exceptions** than the checked exception contract of the overridden method.
- You can declare **narrower checked exception types** or declare none at all.
- You can throw **unchecked exceptions** (the `RuntimeException` branch) without the same restriction from the `throws` clause.
- Whether an override is valid is determined by Java's **static types and signatures**, not by whether a caller intends to catch the error.

Runnable example **`OverrideContractDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

interface Source {
    String read() throws IOException;
}

class LocalSource implements Source {
    @Override
    public String read() throws FileNotFoundException {
        throw new FileNotFoundException("Không thấy tệp");
    }
}

public class OverrideContractDemo {
    public static void main(String[] args) {
        Source source = new LocalSource();

        try {
            System.out.println(source.read());
        } catch (IOException e) {
            System.out.println("Bắt: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 OverrideContractDemo.java
java OverrideContractDemo
```

**Exact stdout:**

```text
Bắt: FileNotFoundException
```

`Source.read()` allows `IOException`. `LocalSource.read()` declares `FileNotFoundException`, a checked subclass of `IOException`, so the override is valid.

If an interface has `void run();` **declaring no checked exceptions**, an implementation cannot add `throws MyCheckedException` to the overridden method. This is a practical factor when designing callbacks, framework APIs, or methods provided to third parties.

**Design point:** If an API is intended to require callers to handle a checked exception, that contract must be declared properly at the interface/base method level. It cannot be fixed by simply adding checked `throws` in an implementation override.

## 17. Checked Exceptions in Lambdas and Functional Interfaces

Checked exception constraints also appear in lambdas. For example, `Runnable.run()` declares no checked exceptions:

```java
Runnable r = () -> {
    // throw new MyCheckedException("Lỗi"); // Invalid.
};
```

This is **illustrative code**, assuming `MyCheckedException extends Exception`. If you write the actual `throw` statement without handling the checked exception inside the lambda, the code fails to compile because `Runnable.run()` does not allow that checked exception.

Valid options include:

1. Handle the checked exception **inside the lambda**, if recovery is possible there.
2. Use a **custom functional interface with an appropriate `throws` clause** when you own the API.
3. Convert to an unchecked exception with a `cause`, **only when the callback contract accepts the conversion**.
4. Redesign the call site so checked exceptions are handled at an appropriate layer instead of forcing a callback to do work outside its responsibility.

Custom functional interface example:

```java
@FunctionalInterface
interface CheckedTask {
    void run() throws DataImportException;
}
```

This is an **illustrative interface**, requiring `DataImportException extends Exception` to be declared. When a lambda has target type `CheckedTask`, it can throw the declared checked type. Choose the exception type for the **API contract**, not as a quick syntax workaround to get code to compile.

## 18. Changing Between Checked and Unchecked Affects Callers and API Compatibility

This is not a purely private decision of a class. When publishing a library or module, API users may write:

```java
try {
    client.execute();
} catch (YourCheckedException e) {
    recover(e);
}
```

This is **illustrative skeleton code**. If the API or inheritance structure changes:

- **Adding a new checked exception** to a method's exit paths can force caller source code to modify `catch` or `throws` to recompile.
- **Changing a checked exception to unchecked** can affect `catch` blocks, documentation, and caller expectations; sometimes a dedicated `catch` for a checked type that can no longer be thrown from the `try` block becomes invalid code at compile time.
- **Changing the exception type** even while keeping it unchecked can break handlers catching by specific class.
- **Changing the superclass** of an exception can affect `instanceof` relationships, catch ordering, serialization, and public contracts.
- **Preserving binary signatures** alone is not enough to guarantee behavior and source compatibility, because checked-exception checking happens at compile time and applications may depend on the previous handling rules.

Therefore, choose and document this early for public APIs, and design an **evolvable error classification**. Do not switch between `Exception` and `RuntimeException` just to clean up `throws` clauses without checking the impact on consuming modules.

## 19. Relationship Between Checked/Unchecked and Recovery Behavior

An error can be **recoverable** yet unchecked. For example, `NumberFormatException` can be caught by an input UI to ask the user to re-enter a value. Conversely, a checked `IOException` might occur because a disk failed or a data source no longer exists; the caller may have no choice other than stopping the operation.

Thus, analysis should follow these questions:

- Does the current layer **have enough information** to recover?
- Should the caller **be forced** by the compiler to consider this error type?
- Does the system have a recovery policy at a **top-level boundary**?
- Is this an **abnormal failure** or an **expected business outcome**?
- Does recovery genuinely preserve valid **invariants/side effects**?

For example, a payment API reporting "amount exceeds limit" can be designed as a valid rejection result object rather than a `PaymentException`. Meanwhile, "cannot connect to banking service" is a technical incident that can use an exception, with checked/unchecked classification depending on the contract.

**Recoverability depends on context, not on the superclass itself.**

## 20. Why You Should Not Catch Every `Exception` and Continue

One way people try to "reduce annoyance" with checked exceptions is writing:

```java
try {
    doWork();
} catch (Exception ignored) {
    // Do nothing.
}
```

This is an **anti-pattern skeleton**, with `doWork()` undefined. `catch (Exception)` catches both checked exceptions and `RuntimeException`. Swallowing errors can make callers believe an operation succeeded even though data is incomplete or state is corrupted.

Similarly, an unchecked exception should not be blindly suppressed just to keep the system running. A boundary layer may need to catch broadly to prevent one request from crashing a serving loop, but it must **record the failure, return an accurate status, and apply an appropriate policy**.

Distinguish three behaviors:

1. **Genuine recovery**: a valid fallback exists, and the outcome is acceptable.
2. **Rethrow/wrap**: the current layer cannot recover, so it propagates the signal with proper context.
3. **Swallow**: no handling, no failure reporting, misleading the caller—usually a bug.

Choosing `extends RuntimeException` does not excuse skipping the design of a handling policy.

## 21. Managing `InterruptedException`: A Special Checked Exception

`InterruptedException` is a checked exception commonly used in waiting or interruptible operations such as `Thread.sleep`. It also carries the meaning of a **signal requesting to stop/cancel** a waiting task.

When converting `InterruptedException` into a custom unchecked exception, you should not erase the interrupt semantics. For a synchronous API, propagating `throws InterruptedException` is the clearest option if the contract allows it.

If the API boundary does not allow checked `throws InterruptedException`, a common pattern is:

```java
try {
    Thread.sleep(1000);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Thao tác bị ngắt", e);
}
```

This is **illustrative in-method code**. Calling `Thread.currentThread().interrupt()` restores the interrupt flag that operations like `sleep` typically clear when throwing the exception. Wrapping with a cause preserves the original trace.

However, **do not apply this pattern mechanically to every API**. If the caller needs to distinguish interruption to stop a task, letting the checked `InterruptedException` propagate may be more accurate. What matters is not swallowing or treating an interrupt as an ordinary error that can be ignored.

## 22. Do Not Extend `Error` for Business Exceptions

`Error` and its subclasses are unchecked, but that does not make `extends Error` an alternative to `extends RuntimeException`. `Error` typically represents serious environment/JVM conditions or issues that normal business code is not expected to handle as a routine failure.

Example of what not to do:

```java
// Not recommended for business errors:
class ProductUnavailableError extends Error {
    ProductUnavailableError(String message) {
        super(message);
    }
}
```

This is an illustrative class for **a design to avoid**. For an unavailable product, you can choose a domain result, or an appropriate exception under `Exception`/`RuntimeException` if truly needed.

Similarly, you should generally avoid directly `extends Throwable`: API user handlers written as `catch (Exception e)` will **not catch** a type that extends `Throwable` directly without being under `Exception`. Keep the hierarchy aligned with standard conventions.

## 23. Custom Exception Hierarchy for a Module

When a module has multiple error types and callers need to distinguish them by type, you can create a base class with an error code and have specific types inherit from it. However, **keep the checked/unchecked policy consistent within each branch**, and avoid overly deep trees.

Unchecked design example:

```java
class ApplicationException extends RuntimeException {
    ApplicationException(String message, Throwable cause) {
        super(message, cause);
    }
}

class ConfigurationException extends ApplicationException {
    ConfigurationException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

These are **illustrative classes**. `catch (ApplicationException e)` catches `ConfigurationException` as well; `catch (ConfigurationException e)` allows more specific handling. If both `catch` branches are written in the same construct, the specific branch must come before the parent class.

Another design could use a checked base `ApplicationException extends Exception`, in which case checked subclasses enter the `throws` contracts of methods that can throw them. **Do not choose a checked base just because it sounds "more serious"**; evaluate whether callers need the catch-or-declare obligation for the entire error branch.

If an error does not share the same handling policy, do not force it into the same inheritance tree. You can use an existing exception or a separate class branch and map it to an error code at the boundary.

## 24. Using Multi-Catch When the Caller Has a Common Policy

A caller may want to handle multiple exceptions in a single branch, even when one is checked and one is unchecked:

```java
try {
    execute();
} catch (ReportLoadException | IllegalArgumentException e) {
    System.out.println("Thất bại: "
            + e.getClass().getSimpleName());
}
```

This is **illustrative skeleton code**, assuming `ReportLoadException extends Exception` and `execute()` can throw both listed types. `ReportLoadException` and `IllegalArgumentException` have no subtype relationship, so the multi-catch syntax is valid.

The multi-catch parameter is **implicitly `final`** and cannot be reassigned. It receives **one exception object at runtime**; the actual runtime type of the object is preserved.

If the handling policies for the two errors differ, use **two separate handlers** to preserve intent, rather than merging them just to save lines. Do not combine a parent type and a subtype in the same multi-catch, as the compiler rejects overlapping types.

## 25. Testing Checked/Unchecked: Don't Rely Only on Compilation

For checked exceptions, the compiler helps verify throw paths against signatures, but **does not guarantee proper recovery**. For unchecked exceptions, tests also need to verify behavior because callers are not forced to catch them.

A valuable test suite should verify:

| Case | What to verify |
| --- | --- |
| Success path | No exception thrown, correct result |
| Invalid precondition | Specific unchecked type, contract message or error code |
| Declared checked failure | Caller must catch/declare; runtime throws the exact type |
| Exception wrapping | Wrapper has the right type; `getCause()` preserves the original object |
| Rethrowing | Caller still receives the original exception if required by contract |
| No handler | Operation genuinely fails; does not return a fake success value |
| Boundary handler | Final response is safe; no sensitive data leaked |
| Cleanup alongside failure | Primary, cause, and suppressed exceptions are preserved properly |
| API changes | Sample caller code still compiles against the new version |
| Callbacks and overrides | No checked `throws` violating inheritance contracts |

You can use JUnit `assertThrows` in projects, though external libraries are not required for basic checks. Below is a Java 17 self-checking example for both branches.

## 26. Self-Checking Program for Both Checked and Unchecked

Save **`CustomExceptionAssertionsDemo.java`**:

```java
class CustomChecked extends Exception {
    CustomChecked(String message) {
        super(message);
    }
}

class CustomUnchecked extends RuntimeException {
    CustomUnchecked(String message) {
        super(message);
    }
}

public class CustomExceptionAssertionsDemo {
    static void checked() throws CustomChecked {
        throw new CustomChecked("checked");
    }

    static void unchecked() {
        throw new CustomUnchecked("unchecked");
    }

    public static void main(String[] args) {
        try {
            checked();
            throw new AssertionError("Thiếu checked exception");
        } catch (CustomChecked e) {
            if (!"checked".equals(e.getMessage())) {
                throw new AssertionError("Sai checked message");
            }
            System.out.println("PASS checked");
        }

        try {
            unchecked();
            throw new AssertionError("Thiếu unchecked exception");
        } catch (CustomUnchecked e) {
            if (!"unchecked".equals(e.getMessage())) {
                throw new AssertionError("Sai unchecked message");
            }
            System.out.println("PASS unchecked");
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 CustomExceptionAssertionsDemo.java
java CustomExceptionAssertionsDemo
```

**Exact stdout:**

```text
PASS checked
PASS unchecked
```

The program succeeds when both exceptions have the expected type and message. `AssertionError` is used to fail the test explicitly if no exception is thrown or the result is wrong, without depending on the `-ea` flag for the `assert` keyword.

Passing this run does not prove that a checked/unchecked design is always appropriate: the test only confirms the **chosen behavior**, while contract quality still needs review against caller responsibility, recoverability, and API evolution.

## 27. Common Mistakes

### 27.1. "Fixable errors should always `extends Exception`"

Not true. Invalid user input can be fixed, yet `NumberFormatException` is unchecked. Conversely, a checked `IOException` may stem from an infrastructure failure with no workaround. Design should consider **who decides and whether callers should be forced** to handle it at compile time.

### 27.2. "Unimportant errors should `extends RuntimeException`"

False. Unchecked exceptions can still be very serious; they simply are not required to be caught or declared. Do not use this to indicate handling priority.

### 27.3. "`extends Exception` will catch all caller bugs"

No. Checked exceptions are only checked by the compiler along **declared throw paths**. `RuntimeException` and `Error` can still occur without being declared. The compiler does not guarantee an application has no runtime bugs.

### 27.4. "`catch (Exception)` is the safest"

An overly broad handler can catch `RuntimeException` caused by bugs and hide them. If you only handle a specific failure, catch the **specific type**.

### 27.5. "Just using `throws Exception` is enough"

An overly broad clause deprives callers of information about the error type. Declare specific checked exceptions matching the contract when the API needs precision.

### 27.6. "To get rid of checked exceptions, just `throw new RuntimeException(e.getMessage())`"

This creates a new exception **without preserving the cause**, losing diagnostic information. If you must wrap, use a constructor that takes `cause`, such as `new ServiceException("...", e)`.

### 27.7. "Every custom exception needs four constructors, fields, and multiple subclasses"

Not required. Prefer a concise, meaningful API; add dedicated classes only when they improve error differentiation and management.

### 27.8. "Having a checked exception means the caller handled it properly"

A caller might just `catch` and ignore it, log duplicates, or return an incorrect result. The compiler checks syntactic obligation, not recovery quality.

### 27.9. "Unchecked exceptions don't need documentation"

False. API consumers still need to know preconditions, error codes, failure conditions, and handling expectations, typically via JavaDoc `@throws` and usage guides.

### 27.10. "Switching between checked and unchecked affects no one"

Such a change can break caller source code, `catch` logic, interface/override contracts, and framework handling. Evaluate compatibility before changing the superclass.

### 27.11. "Using `extends Error` to avoid `throws` is reasonable"

Do not do this. `Error` is not meant for ordinary business errors; choose `RuntimeException` if the contract calls for unchecked.

### 27.12. "Every business outcome should use a custom exception"

Not necessarily. Expected cases such as a search returning no results or a validly rejected request may fit `Optional`, `enum`, `sealed interface`, or a stateful result type.

## 28. Self-Check Questions

**Question 1.** Is `class DataException extends Exception` directly checked or unchecked?  
**Answer:** Checked; callers must catch or declare it when the call path can throw it.

**Question 2.** Can `class StateException extends RuntimeException` be caught with `catch (Exception e)`?  
**Answer:** Yes. `RuntimeException` is under the `Exception` branch, even though it is unchecked.

**Question 3.** Why can `StateException` be thrown without declaring `throws`?  
**Answer:** Because it is an unchecked exception; the compiler does not enforce catch-or-declare.

**Question 4.** If it `extends Exception`, does the exception recover on its own or do callers automatically handle it properly?  
**Answer:** No. The compiler only enforces catching/declaring. Recovery requires meaningful logic.

**Question 5.** Should you create `CustomInvalidArgumentException` to replace every `IllegalArgumentException`?  
**Answer:** Only when the new class adds real classification/contract value; otherwise, the built-in type may suffice.

**Question 6.** When wrapping `IOException` into a service exception, how do you preserve the cause?  
**Answer:** Provide a `(String, Throwable)` constructor and call `super(message, cause)` so `getCause()` retains the original exception.

**Question 7.** Can changing a custom checked exception to unchecked affect callers?  
**Answer:** Yes. Catch/declare obligations, handler validity, overrides, and API expectations can all change.

**Question 8.** Can an overriding method declare a broader checked exception than the base method?  
**Answer:** No, under Java's checked-exception rules; it may declare a narrower one if valid.

**Question 9.** Why can't a lambda with target type `Runnable` arbitrarily throw a custom checked exception?  
**Answer:** Because `Runnable.run()` does not declare that checked exception; it must be handled or a different suitable functional interface must be used.

**Question 10.** Should `getMessage()` be used to determine business error codes?  
**Answer:** No; messages can change or be localized. Use structured types or error codes instead.

**Question 11.** Can an unchecked exception be caught at an HTTP/CLI boundary?  
**Answer:** Yes. Not being mandatory does not mean it cannot be caught.

**Question 12.** Is `Error` checked or unchecked? Is it suitable for an "insufficient balance" error?  
**Answer:** `Error` is unchecked, but it is not suitable for such a business error.

**Question 13.** When is a stateful result better than an exception?  
**Answer:** When failure is an expected business branch and callers need to handle it frequently in normal control flow.

**Question 14.** Why must `InterruptedException` be handled carefully if you plan to wrap it as unchecked?  
**Answer:** It carries an interrupt/cancellation signal. Propagate it if the contract allows, or restore the interrupt status when appropriate.

**Question 15.** If a client always catches `catch (ApplicationException e)`, will a subclass of `ApplicationException` be caught?  
**Answer:** Yes, if it belongs to that inheritance branch and the exception is thrown within the handler's scope.

## 29. Decision Checklist for a New Custom Exception

Before creating `XxxException`, review:

1. **Is this actually an exception?** Or is it an expected business outcome that should be returned with a status?
2. **Is a built-in type clear enough?** For example, `IllegalArgumentException` or `IllegalStateException`.
3. **Must the caller be forced to consider this error type at compile time?** If yes and it adds clear value, consider checked.
4. **Are callers usually unable to handle it nearby and instead need a top-level boundary?** Consider unchecked and document it.
5. **Is the error type stable under the API contract?** Avoid repeatedly changing the superclass.
6. **Are different recovery variants needed?** If so, classify using specific types or error codes.
7. **Is `cause` preserved when translating errors from lower layers?** Ensure appropriate constructors.
8. **Is the message safe and useful?** Do not include passwords, tokens, or sensitive data.
9. **Is there a stable error code for the application?** Do not parse message text.
10. **Do any interfaces/callbacks affect checked `throws`?** Check overriding and functional interface rules.
11. **Are there cancellation/interrupt semantics?** Do not silently swallow interrupt signals.
12. **Could cleanup scenarios produce suppressed exceptions?** Preserve cause/suppressed exceptions for diagnostics.
13. **Where is the final handler?** HTTP, CLI, job scheduler, UI, or library caller.
14. **Have both success and failure behaviors been tested?** Do not rely solely on the compiler.
15. **Would changing the exception type break existing callers?** Consider both source and API compatibility.
16. **Are you writing `catch` just to silently ignore errors?** Avoid turning failures into fake successes.

## 30. Conclusion

**`extends Exception` and `extends RuntimeException` establish two different contracts for Java custom exceptions**:

- **Checked (directly `extends Exception`):** callers have an obligation to **catch or declare** if a method can throw the error; suitable when exposing and enforcing consideration of a specific failure is a valuable part of the API.
- **Unchecked (`extends RuntimeException`):** callers are **not forced** by the compiler; suitable for many precondition violations, state violations, and centralized handling designs, though errors must still be diagnosed and routed properly.

There is no single rule based on severity or recoverability. Choose based on **error semantics, caller responsibility, API stability, top-level handling policy, and user experience**. Preserve root causes via `cause` when wrapping, document unchecked exceptions, use stateful results for expected business branches, and avoid creating complex exception hierarchies without benefit.

The most concise rule of thumb: **use checked when forcing callers to handle or declare is a useful part of the contract; use unchecked when you do not want to impose that obligation; and create a new exception only when the new type expresses a condition that callers or the system genuinely need to distinguish**.
