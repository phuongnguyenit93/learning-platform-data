# Distinguishing Checked Rules from Actual Recoverability in Java

In Java, *checked exceptions* and *unchecked exceptions* describe how **the compiler enforces exception declaration or handling**. Meanwhile, **recoverability** is a runtime question: what concrete action can the program take to continue correctly after a failure?

These two concepts are related when designing APIs, but they are **not identical**:

- A *checked* exception can still represent a failure that the current method or the entire application cannot recover from.
- An *unchecked* exception can still represent an expected situation with a safe handling strategy, such as user input that cannot be parsed into a number.
- `catch` causes the program to **intercept and handle control flow** at a given point; merely catching an exception object **does not prove that recovery succeeded**.

The goal of this lesson is to distinguish language obligations from error-handling decisions based on business logic, state, and responsibility boundaries.

## 1. Exception Hierarchy and the Meaning of Checked/Unchecked

~~~text
java.lang.Throwable
├── java.lang.Error                           [unchecked]
│   └── java.lang.OutOfMemoryError            [unchecked]
└── java.lang.Exception                       [checked]
    ├── java.io.IOException                   [checked]
    ├── java.text.ParseException              [checked]
    └── java.lang.RuntimeException            [unchecked]
        ├── java.lang.IllegalArgumentException[unchecked]
        │   └── java.lang.NumberFormatException [unchecked]
        └── java.lang.IllegalStateException   [unchecked]
~~~

This is a subset of the tree, not the entire hierarchy. In particular, `NumberFormatException` is a **subclass of `IllegalArgumentException`**, not a sibling branch.

According to Java rules, classes that extend `Throwable` **except** `RuntimeException`, `Error`, and all subclasses of those two branches are *checked*. Therefore:

- `IOException` and `ParseException` are checked.
- `RuntimeException`, `NumberFormatException`, `IllegalStateException`, and `Error` are unchecked.
- `RuntimeException` **still extends `Exception`**, but is exempt from the checked rule.
- This classification is not a severity level and does not measure recoverability.

### Compiler Rules

When an operation **can throw a checked exception** according to the type information visible to the compiler, the enclosing code must handle or declare the exception under Java's rules. Two common approaches:

1. Catch the exception with `try/catch` at a layer capable of making a decision.
2. Allow propagation by declaring `throws` in the method signature.

Example:

~~~java
static String readConfig(java.nio.file.Path path) throws java.io.IOException {
    return java.nio.file.Files.readString(path);
}
~~~

This is an **illustrative method snippet**, not a standalone runnable program. `Files.readString` can throw `IOException`; the example allows forwarding it via `throws IOException`. If the caller neither catches nor declares the corresponding checked exception, the compiler may report `unreported exception ...; must be caught or declared to be thrown`.

Conversely:

~~~java
static int parsePort(String text) {
    return Integer.parseInt(text);
}
~~~

`Integer.parseInt` can throw `NumberFormatException`, yet adding `throws NumberFormatException` is not required. The exception still occurs and propagates **at runtime** if the input is invalid.

**`throws` is a static contract**, not a command that performs recovery. **`throw` is the statement that raises an exception**. **`catch` is the place where an exception can be handled**, but the action inside the `catch` block determines the outcome.

## 2. Two Independent Axes: Classification and Recoverability

You can think of each exception in terms of two separate questions:

1. **Compiler:** Does this exception type belong to checked or unchecked?
2. **Runtime and business logic:** At the location under consideration, is there a safe way to achieve the goal, restore valid state, or report the failure properly?

| | Appropriate recovery option exists | No recovery option here |
| --- | --- | --- |
| **Checked** | `IOException` when a valid backup configuration exists; re-reading a resource when policy permits | `IOException` due to a missing required file with no alternative source; `SQLException` when the transaction is no longer valid |
| **Unchecked** | `NumberFormatException` when the UI prompts the user to re-enter a valid number | `IllegalStateException` when an operation violates internal state; `NullPointerException` due to an unfixed logic bug |

**The cells in this table are context-dependent examples, not fixed properties of the exception class.** The same `IOException` may be recoverable on a screen with a file re-selection feature, yet unrecoverable during a mandatory startup step. The same `NumberFormatException` may be an expected data error in the UI, yet a programming bug if the string is a constant defined by the program itself that should always be valid.

It is also necessary to distinguish three outcomes:

- **Recovering to complete the goal:** Using a verified fallback source; prompting for re-entry and receiving a valid value; retrying under a safe policy.
- **Controlled failure handling:** Stopping the operation, returning a meaningful error, keeping transactions consistent, and releasing resources. This is proper *error handling*, **not necessarily recovery**.
- **Hiding failure:** Catching an exception and ignoring it, returning a fake value with no contract, or continuing when state is already corrupted. This approach can make the consequences harder to detect.

Recoverability belongs to **the caller layer's context and system policy**. You should not assign a fixed `recoverable=true/false` attribute to an entire exception class.

## 3. A Java 17+ Program Demonstrating All Four Cases

The example simulates a primary configuration source failing in a predictable way. One workflow has a backup so it can recover; another must halt the initialization step. Then the program handles an invalid user-entered age (unchecked but with a corrective path) and an object state error (unchecked, unable to continue that operation).

Create the file **`RecoveryDemo.java`**:

~~~java
import java.io.IOException;

public class RecoveryDemo {
    public static void main(String[] args) {
        System.out.println("1. Checked - có bản dự phòng");
        loadWithFallback();

        System.out.println("2. Checked - không có bản dự phòng");
        loadWithoutFallback();

        System.out.println("3. Unchecked - có giá trị nhập lại");
        int age = parseAgeWithCorrection("hai mươi", "20");
        System.out.println("Tuổi hợp lệ: " + age);

        System.out.println("4. Unchecked - trạng thái không hợp lệ");
        try {
            requireReady(false);
        } catch (IllegalStateException e) {
            System.out.println("Hủy thao tác: " + e.getMessage());
        }
    }

    // IOException remains checked even though the data is simulated for this example.
    static String readConfiguration(String source) throws IOException {
        if ("primary".equals(source)) {
            throw new IOException("nguồn chính không phản hồi");
        }
        if ("backup".equals(source)) {
            return "SAFE";
        }
        throw new IOException("nguồn cấu hình không tồn tại");
    }

    static void loadWithFallback() {
        try {
            String mode = readConfiguration("primary");
            System.out.println("Chế độ: " + mode);
        } catch (IOException primaryFailure) {
            try {
                String mode = readConfiguration("backup");
                System.out.println("Đã chuyển sang bản dự phòng: " + mode);
            } catch (IOException backupFailure) {
                backupFailure.addSuppressed(primaryFailure);
                System.out.println(
                        "Không tải được cấu hình: " + backupFailure.getMessage());
            }
        }
    }

    static void loadWithoutFallback() {
        try {
            readConfiguration("primary");
            System.out.println("Khởi tạo thành công");
        } catch (IOException e) {
            System.out.println("Dừng bước khởi tạo: " + e.getMessage());
        }
    }

    static int parseAgeWithCorrection(String first, String corrected) {
        try {
            return Integer.parseInt(first);
        } catch (NumberFormatException e) {
            System.out.println("Giá trị nhập sai: " + first);
            return Integer.parseInt(corrected);
        }
    }

    static void requireReady(boolean ready) {
        if (!ready) {
            throw new IllegalStateException("đối tượng chưa sẵn sàng");
        }
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac RecoveryDemo.java
java RecoveryDemo
~~~

Standard output:

~~~text
1. Checked - có bản dự phòng
Đã chuyển sang bản dự phòng: SAFE
2. Checked - không có bản dự phòng
Dừng bước khởi tạo: nguồn chính không phản hồi
3. Unchecked - có giá trị nhập lại
Giá trị nhập sai: hai mươi
Tuổi hợp lệ: 20
4. Unchecked - trạng thái không hợp lệ
Hủy thao tác: đối tượng chưa sẵn sàng
~~~

### Analysis of Each Branch

**Case 1 — checked and recoverable:** `readConfiguration("primary")` throws `IOException`. `loadWithFallback` has an accepted `"backup"` source, so it reads successfully and prints `SAFE`. What makes recovery possible is **the alternative source together with the policy to use it**, not the `checked` classification.

**Case 2 — checked and unrecoverable at the current step:** Same `IOException` type, same failure source. `loadWithoutFallback` has no alternative solution, so it reports the failure and halts the initialization step. The method has a `catch` block, yet **it does not complete the configuration-loading goal**. In a real application, the caller must understand the failed outcome; you can propagate the exception or return a result that clearly expresses the state instead of printing and continuing as in the demonstration example.

**Case 3 — unchecked and recoverable:** `Integer.parseInt("hai mươi")` throws `NumberFormatException`. The handler supplies the new value `"20"` and completes the goal. The program does not need to declare a checked exception to execute the recovery branch. The example simulates user re-entry; in a real application, you must validate the new value and allow safe re-entry rather than assuming every retry will be valid.

**Case 4 — unchecked and unrecoverable:** `requireReady(false)` detects that a state precondition is not met. The `catch` block cancels that operation and displays the reason. It does not turn the object's state into a valid one; to execute again, the initialization flow must be fixed at an authoritative layer.

In the branch where the backup source also fails, `backupFailure.addSuppressed(primaryFailure)` preserves the initial failure for diagnostics. This branch **does not execute during the demonstration run** because the `backup` source succeeds. The suppressed exceptions mechanism is useful when multiple related failures must be retained; in real systems, you typically propagate or record the aggregated error per contract rather than merely printing a message.

## 4. `catch/throws` Obligations Are Not Equivalent to Error Policy

Consider two ways of using a checked exception:

~~~java
static String load(java.nio.file.Path path) throws java.io.IOException {
    return java.nio.file.Files.readString(path);
}
~~~

The `load` method chooses to **delegate responsibility outward**. This can be a good choice because the caller layer knows whether a backup file exists or whether to show a prompt to select another file. Declaring `throws IOException` expresses the kind of failure the caller must consider, rather than promising that recovery is possible.

~~~java
static String loadOrDefault(java.nio.file.Path path)
        throws java.io.IOException {
    try {
        return java.nio.file.Files.readString(path);
    } catch (java.nio.file.NoSuchFileException e) {
        return "default";
    }
}
~~~

These are two **standalone method snippets**, without `main`. The second snippet is only business-correct if **the contract allows using a default value when the file does not exist**. Other I/O errors can still propagate via `throws IOException`. If the file holds required configuration secrets, silently using `"default"` can be dangerous or produce an invalid configuration.

When a checked exception propagates across multiple layers, you can choose to declare specific types; you should not default to `throws Exception` for every API. Some frameworks or architectural boundaries decide to translate low-level exceptions into domain exception types (*domain exceptions*) to express the contract at a higher layer. When translating, preserve the cause:

~~~java
static String loadRequired(java.nio.file.Path path) {
    try {
        return java.nio.file.Files.readString(path);
    } catch (java.io.IOException e) {
        throw new IllegalStateException(
                "Không thể nạp cấu hình bắt buộc", e);
    }
}
~~~

This is an illustrative method snippet. Converting `IOException` into `IllegalStateException` **changes the caller's compile-time checking requirement**; it does not make the error disappear and does not make it recover on its own. Calling `getCause()` on the new exception returns the original `IOException`.

## 5. Practical Criteria for Deciding Whether to Recover

Before catching an exception to continue execution, check:

1. **Is the goal still achievable?** Is there another file, a backup source, a way to re-validate data, or a way to re-run the operation?
2. **Are data and state still consistent?** If a transaction has already made partial changes, rollback or a compensating mechanism is needed before retrying.
3. **Is the operation safe to repeat?** Reading a resource can be retried; debiting money, sending requests, or creating records can cause duplicate side effects and require idempotency or transaction control.
4. **Is the error transient?** A network timeout may be transient; a malformed configuration file usually will not fix itself after a retry. You must bound retry counts, timeouts, and resource budgets.
5. **Does this layer have sufficient authority?** A file-reading function might not know whether to use a default or force startup to fail. Propagating the error to an orchestrating layer is often more accurate.
6. **Are the cause and context preserved?** Messages, causes, suppressed exceptions, error codes, or structured logs help diagnose issues when recovery is not possible.

These questions apply to **both checked and unchecked exceptions**.

### Examples by Application Boundary

| Boundary | Potential Exception | Appropriate Behavior |
| --- | --- | --- |
| Form input screen | `NumberFormatException` (unchecked) | Highlight the invalid input field, preserve other data, prompt for correction |
| Configuration loader | `IOException` (checked) | Use a backup source **if the contract permits**, or report inability to initialize |
| Business service | `IllegalArgumentException` (unchecked) | Return invalid-input information; do not retry infinitely with the same data |
| Resource access layer | `IOException` (checked) | Provide an error with context, close resources, let the upper layer decide |
| Task orchestrator | Unexpected unhandled exception | Log, cancel, or mark the task as failed; do not silently treat the task as succeeded |

"Appropriate handling" does not necessarily mean "keep running normally." A **transparent failure with safe state** is often better than hiding an error to return a false success.

## 6. Common Pitfalls

### Pitfall 1: "Checked means it is definitely recoverable"

No. `IOException` is checked even when a mandatory file is missing with no backup. A `catch` block might only add context and rethrow; a compiler requirement does not supply a business solution.

### Pitfall 2: "Unchecked is always a bug, never catch it"

No. `NumberFormatException` from user-entered data is a legitimate case to handle at the UI layer. `IllegalArgumentException` from external requests can also be mapped to validation errors. However, if the cause is an internal invariant violation, fix the code or workflow rather than treating every error as invalid input.

### Pitfall 3: "If it's caught, the system has recovered"

Bad example:

~~~java
try {
    saveImportantData();
} catch (Exception ignored) {
    // Continue and pretend the save succeeded.
}
~~~

This is an **anti-example of error policy**, not a standalone runnable program; `saveImportantData()` represents an application operation. Catching and ignoring can mislead the caller into thinking the data was saved. Handle failed outcomes per contract: controlled retry, rollback, returning an error status, or propagating the exception.

### Pitfall 4: "Converting checked to runtime solves the problem"

Wrapping `IOException` in `RuntimeException` removes the caller's `catch/throws` obligation, but **does not restore the resource**. If there is a design reason to convert, use a meaningful exception type and preserve `cause`.

### Pitfall 5: "Retrying every exception a few times is fine"

Retrying helps when the error is likely transient, the operation is safe to repeat, and time budget remains. Retrying `NumberFormatException` on the same string `"abc"` will not turn the string into a number. Retrying `IllegalStateException` without fixing state may just create a useless loop. Retrying a write command with side effects without idempotency protection can duplicate results.

### Pitfall 6: "`catch (Exception e)` is a safe recovery boundary"

`catch (Exception e)` catches most checked exceptions **and** `RuntimeException` due to inheritance. When used at a system boundary, avoid lumping programming bugs together with expected errors and applying a generic continuation strategy. It also does not catch `Error`. Catch specific types where a clear handling strategy exists, and only perform broad handling at boundaries with a defined error policy.

### Pitfall 7: "`InterruptedException` is a signal to just keep retrying"

`InterruptedException` is checked, but usually indicates an interruption or task cancellation request. You should not unconditionally swallow the exception and retry. When it cannot be propagated under the current contract, a common practice is to restore the interrupt flag via `Thread.currentThread().interrupt()` and terminate the current step according to application policy. The task-management context determines the right action.

## 7. A Short Decision Flow When Designing APIs

You can use the following sequence when encountering an operation that may fail:

~~~text
Operation fails
       │
       ▼
Is there a safe way to meet the goal allowed by the contract?
       ├── Yes → Execute fallback / re-entry / bounded retry
       │         └── Verify result and state after handling
       │
       └── No
             ▼
        Does the current layer have an obligation to report or translate?
             ├── Yes → Attach context, preserve cause, return error or rethrow
             └── No → Propagate error to the responsible boundary
~~~

This diagram describes **actual runtime policy**, independent of checked/unchecked. Only after choosing the behavior do you apply the necessary Java syntax: `try/catch`, `throws`, or `throw` according to the exception type and method contract.

When designing **custom exception types**:

- Choose a checked exception when you want Java callers to be forced to *consider* the failure scenario in the API contract. This does not guarantee they will have a way to recover.
- Choose an unchecked exception when the contract does not require mandatory handling at every call site—for example, precondition violations, state violations, or a domain error type per system convention.
- Prefer specific types and clear messages; document them in JavaDoc when the API has significant impact. Do not decide checked/unchecked solely based on labels like "external error" or "programming bug."

## 8. Self-Check Questions

1. `IOException` occurs while reading a file. Why can the same exception type be recoverable on a file-selection screen yet unrecoverable during a mandatory initialization phase?
2. `NumberFormatException` is unchecked. The user enters `"xyz"` into the age field. Can you catch it and prompt for re-entry? Does the compiler force you to catch it?
3. A method catches `IOException`, logs it, and returns `"OK"` even though data writing did not complete. Is this recovery? What are the risks?
4. When converting `IOException` into `IllegalStateException`, where should the original exception be stored? Does the conversion make the operation succeed?
5. Why shouldn't you retry a payment request that lacks duplicate-processing protection, even if a network error looks transient?
6. For `InterruptedException`, why is "catch and continue infinitely" usually a bad decision?
7. Distinguish: what two questions do "the compiler forces handling" and "the program can recover" answer?

**Answer hints:** (1) Because of whether a fallback option exists and policy permits it; (2) you can catch it to prompt for re-entry, the compiler does not require it; (3) no, this is hiding failure; (4) stored in `cause`, it does not fix the error; (5) it can create duplicate side effects; (6) it ignores the cancellation/interruption intent; (7) compile-time type obligations versus the ability to continue correctly at runtime.

**Key takeaway:** *Checked/unchecked is a property of the exception type in Java's compile-time checking system. Recoverability is a property of the situation, goal, and handling policy at a specific layer.* Evaluating these two axes separately helps you write APIs with clear contracts and handle errors without corrupting application state.