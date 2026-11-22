# IllegalArgumentException and IllegalStateException in Java

`IllegalArgumentException` and `IllegalStateException` are two important **unchecked** exceptions in Java, both extending `RuntimeException`. They can both occur when a method call cannot be accepted, but they describe **two different contract-violation causes**:

- **`IllegalArgumentException`**: *an argument supplied by the caller is invalid* according to the method's preconditions. For example, `setAge(-2)` when age must be non-negative, or `setPort(70000)` when ports are only allowed in 1–65535.
- **`IllegalStateException`**: *the state of the object/system at the time of the call does not allow performing the operation*. For example, `send()` before `connect()`, `write()` after `close()`, or `confirm()` when an order has already been cancelled.

The two are not different "severity levels"; **the difference lies in why the call violates the contract**. If the caller only needs to fix the passed value for the call to be valid, `IllegalArgumentException` is usually more accurate. If that same argument could be valid at another time after the state changes, `IllegalStateException` usually expresses it better.

This lesson covers the class hierarchy, checked/unchecked characteristics, selection criteria, overlapping cases, compilable/runnable Java 17 examples, constructors/message/cause, JavaDoc, testing, and notes that not every input error or business error should be represented by an exception.

## 1. Position in the Java Exception Hierarchy

Simplified diagram:

```text
java.lang.Object
└── java.lang.Throwable
    ├── java.lang.Error
    └── java.lang.Exception
        └── java.lang.RuntimeException
            ├── java.lang.IllegalArgumentException
            │   └── java.lang.NumberFormatException
            ├── java.lang.IllegalStateException
            ├── java.lang.NullPointerException
            └── java.lang.IndexOutOfBoundsException
```

Key points to know:

1. `IllegalArgumentException` and `IllegalStateException` are **two sibling classes directly under `RuntimeException`**, not parent/child of each other.
2. `NumberFormatException` is a subclass of `IllegalArgumentException`. When `Integer.parseInt("abc")` fails, the caller can catch it with `catch (NumberFormatException e)` or a broader handler `catch (IllegalArgumentException e)`.
3. `NullPointerException` and `IndexOutOfBoundsException` are also unchecked exceptions, but they are **not** subclasses of `IllegalArgumentException`. They have their own meanings.
4. `catch (RuntimeException e)` can catch both `IllegalArgumentException` and `IllegalStateException`, but because it is so broad, the handler must actually have an appropriate policy if it wants to handle both.
5. `catch (Exception e)` also catches both because `RuntimeException extends Exception`; this does not make them checked exceptions.

Both `IllegalArgumentException` and `IllegalStateException` are provided in `java.lang`, so normal Java code does not need an `import` to use them.

## 2. Why Are They Unchecked Exceptions?

A **checked exception** is in the part of the `Exception` branch that does not belong to `RuntimeException`. When a method can throw a checked exception, Java requires calling code to catch or declare it (`catch-or-declare`) according to compile-time checking rules.

The two exceptions we are studying are **unchecked**:

```java
static void checkQuantity(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException(
                "quantity phải lớn hơn 0");
    }
}
```

This is an **illustrative method**, without `main`. It is not necessary to write:

```java
static void checkQuantity(int quantity)
        throws IllegalArgumentException {
    // ...
}
```

The `throws IllegalArgumentException` clause is valid, but **not required**, and it does not force callers to write a `catch`. The same is true for `IllegalStateException`.

**Unchecked does not mean Java handles it automatically.** When either exception is thrown, execution flow is abnormally interrupted and the exception propagates up the call stack until a compatible handler is found. If there is no appropriate handler, the execution thread may terminate with a failure; how the program and environment react also depends on where the exception is thrown.

Distinguish three things:

- **Required by the compiler:** no, for both.
- **Can be actively caught:** yes, when the current layer knows how to recover or respond.
- **Needs contract design and error monitoring:** yes, even without writing `throws`.

## 3. Decision Question: Invalid Argument or Invalid State?

When weighing the two exceptions, ask:

**(A) Did the caller pass a value outside the method's valid domain?**

If yes, `IllegalArgumentException` is the natural candidate. For example, a method `setRetryCount(int count)` specifies `count >= 0` and receives `-1`.

**(B) Was the call rejected primarily because of the object's current state or the order of operations?**

If yes, `IllegalStateException` is usually appropriate. For example, `write()` may only be called after `open()` and before `close()`.

**(C) Could both conditions be wrong at the same time?**

Determine **which contract is checked first**, which is the primary cause to report, and keep the check order stable and easy to understand. Do not turn exception selection into a judgment about error severity; express what the caller needs to fix.

Quick table:

| Call | Violated condition | Usually appropriate choice |
| --- | --- | --- |
| `setVolume(-1)` | Negative, outside allowed domain | `IllegalArgumentException` |
| `setPort(70000)` | Port out of bounds | `IllegalArgumentException` |
| `connect(null)` | Missing required object | Usually `NullPointerException` / `Objects.requireNonNull` |
| `send(data)` before `connect()` | No active connection yet | `IllegalStateException` |
| `commit()` twice when only allowed once | Called in wrong execution phase | `IllegalStateException` |
| `Iterator.remove()` before `next()` | Operation in wrong iterator state | `IllegalStateException` per Iterator contract |
| `Integer.parseInt("x")` | String not in valid number format | `NumberFormatException`, a kind of `IllegalArgumentException` |
| `list.get(100)` when only a few elements exist | Index out of range | `IndexOutOfBoundsException`, not `IllegalArgumentException` |
| `requireNonNull(null)` | Null reference violates precondition | `NullPointerException` |
| UI reports product out of stock | Normal business branch | Usually a business result type; do not default to either one |

The examples above illustrate **contract semantics**; with real library APIs, prefer the exact exception specified by that API's JavaDoc.

## 4. Runnable Example: Checking Arguments with `IllegalArgumentException`

Save **`IllegalArgumentDemo.java`**:

```java
public class IllegalArgumentDemo {
    static int percentOf(int value, int percent) {
        if (percent < 0 || percent > 100) {
            throw new IllegalArgumentException(
                    "percent phải thuộc [0, 100]: " + percent);
        }
        return value * percent / 100;
    }

    public static void main(String[] args) {
        System.out.println("Hợp lệ: " + percentOf(200, 25));

        try {
            percentOf(200, 120);
            System.out.println("Không tới dòng này");
        } catch (IllegalArgumentException e) {
            System.out.println("Bắt: " + e.getMessage());
        }

        System.out.println("Kết thúc");
    }
}
```

Compile and run with Java 17+:

```bash
javac -encoding UTF-8 --release 17 IllegalArgumentDemo.java
java IllegalArgumentDemo
```

**Exact stdout** on a UTF-8 capable console:

```text
Hợp lệ: 50
Bắt: percent phải thuộc [0, 100]: 120
Kết thúc
```

Analysis:

1. The value `percent = 25` is within the valid domain, so the method returns `50`.
2. `percent = 120` violates a precondition independent of the object's state.
3. The method throws `IllegalArgumentException` before computing.
4. `catch` catches the error, prints the message, and continues after the handler block.
5. The line `"Không tới dòng này"` is not printed because `percentOf(200, 120)` terminates abnormally.

What the caller needs to fix is the **parameter value**, not calling `open()` or transitioning state phases.

Note that the example uses `int` to illustrate preconditions; financial systems should not default to integer multiplication/division formulas as production business logic due to rounding and overflow issues.

## 5. Runnable Example: Object State with `IllegalStateException`

Save **`IllegalStateDemo.java`**:

```java
public class IllegalStateDemo {
    static class Session {
        private boolean connected;

        void connect() {
            if (connected) {
                throw new IllegalStateException(
                        "Phiên đã kết nối");
            }
            connected = true;
            System.out.println("Đã kết nối");
        }

        void send(String message) {
            if (!connected) {
                throw new IllegalStateException(
                        "Phải connect trước khi send");
            }
            System.out.println("Đã gửi: " + message);
        }

        void disconnect() {
            if (!connected) {
                throw new IllegalStateException(
                        "Phiên chưa kết nối");
            }
            connected = false;
            System.out.println("Đã ngắt kết nối");
        }
    }

    public static void main(String[] args) {
        Session session = new Session();

        try {
            session.send("hello");
        } catch (IllegalStateException e) {
            System.out.println("Bắt: " + e.getMessage());
        }

        session.connect();
        session.send("hello");
        session.disconnect();

        try {
            session.send("again");
        } catch (IllegalStateException e) {
            System.out.println("Bắt: " + e.getMessage());
        }
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 IllegalStateDemo.java
java IllegalStateDemo
```

**Exact stdout**:

```text
Bắt: Phải connect trước khi send
Đã kết nối
Đã gửi: hello
Đã ngắt kết nối
Bắt: Phải connect trước khi send
```

The message `"hello"` is completely valid. The problem with the first call is that **the session is not connected yet**. After `connect()`, the exact same call `send("hello")` succeeds. Once `disconnect()` is called, `send("again")` is once again disallowed.

This is the signature of `IllegalStateException`: **call validity depends on the object's lifecycle/state**. In the example, state is simplified to a `boolean` field; real networking code may also have I/O errors, timeouts, unexpected disconnects, and multithreaded synchronization issues.

## 6. One Method Can Use Both Exception Types

Many APIs need to validate both **arguments** and **state**. For example, a configuration utility that only allows changing parameters before being activated:

```java
void setMaxConnections(int value) {
    if (value <= 0) {
        throw new IllegalArgumentException(
                "maxConnections phải dương");
    }
    if (started) {
        throw new IllegalStateException(
                "Không thể đổi sau khi start");
    }
    maxConnections = value;
}
```

This is an **illustrative method** in a class with fields `started` and `maxConnections`. The two branches have different reasons:

- `value <= 0`: invalid parameter; the caller must choose a positive number.
- `started == true`: invalid state; the caller must change the configuration before starting or use a supported hot-reconfiguration API.

The check order in the example prioritizes catching invalid arguments first. If it is already running and the caller calls `setMaxConnections(-5)`, the exception received is `IllegalArgumentException`. If the check order were reversed, the caller would receive `IllegalStateException` for the same situation. **Java does not decide the priority order automatically**; it is part of contract design.

Choose the order intentionally, especially for public APIs. When multiple conditions are wrong, documentation and tests should reflect which condition is reported first if that matters to callers.

## 7. Complete Program: Arguments and State Coexisting

Save **`ArgumentAndStateDemo.java`**:

```java
public class ArgumentAndStateDemo {
    static class Job {
        private int priority = 1;
        private boolean submitted;

        void changePriority(int priority) {
            if (priority < 1 || priority > 5) {
                throw new IllegalArgumentException(
                        "priority phải từ 1 đến 5");
            }
            if (submitted) {
                throw new IllegalStateException(
                        "Job đã submit");
            }
            this.priority = priority;
        }

        void submit() {
            if (submitted) {
                throw new IllegalStateException(
                        "Không submit hai lần");
            }
            submitted = true;
        }

        int priority() {
            return priority;
        }
    }

    public static void main(String[] args) {
        Job job = new Job();

        try {
            job.changePriority(0);
        } catch (IllegalArgumentException e) {
            System.out.println("Đối số: " + e.getMessage());
        }

        job.changePriority(3);
        job.submit();

        try {
            job.changePriority(4);
        } catch (IllegalStateException e) {
            System.out.println("Trạng thái: " + e.getMessage());
        }

        System.out.println("Priority hiện tại: " + job.priority());
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 ArgumentAndStateDemo.java
java ArgumentAndStateDemo
```

**Exact stdout**:

```text
Đối số: priority phải từ 1 đến 5
Trạng thái: Job đã submit
Priority hiện tại: 3
```

The first time, `priority = 0` is outside the allowed domain even though the job has not been submitted yet. Next, `priority = 3` is valid and updates successfully. After `submit()` transitions the state, `changePriority(4)` uses a **domain-valid** value, but it cannot be applied in the submitted state. The old value `3` is preserved.

The example also shows **not letting an exception occur after partially mutating important state**, when it can be checked beforehand. This is an API design principle worth noting.

## 8. A Tricky Question: A "Well-Formed" Argument That Is Invalid in the Current State?

For example, calling `moveTo("PAID")` when an order is in `CANCELLED`. `"PAID"` may be a valid state name in the system, but **transitioning from CANCELLED to PAID** is forbidden.

There are two perspectives:

- If the contract states that **the `targetState` argument may only be in the set of states reachable from the current state**, then the argument can be considered invalid.
- If the contract states that **the object is already in a state that disallows any such transition**, `IllegalStateException` may be the more natural choice.

A useful convention is to distinguish:

1. **Value invalid in every state** → leans toward `IllegalArgumentException`. For example, a state name that does not exist.
2. **Valid value, but the operation is forbidden due to current state** → leans toward `IllegalStateException`.
3. **Expected business outcome such as "order cannot be paid because it is cancelled"** → consider returning a domain result type instead of throwing an unchecked exception.

This is an area with **design choices**, not one where Java imposes a single answer. More important than debating the type name are **consistency, contract clarity, and practical response policy**.

## 9. `NumberFormatException` Is a Specific Case of `IllegalArgumentException`

A common JDK example:

```java
int value = Integer.parseInt("123");
```

When the string cannot be parsed into an integer, `Integer.parseInt` throws `NumberFormatException`, which is a **subclass of `IllegalArgumentException`**.

Standalone Java 17 example **`NumberFormatHierarchyDemo.java`**:

```java
public class NumberFormatHierarchyDemo {
    public static void main(String[] args) {
        try {
            Integer.parseInt("abc");
        } catch (IllegalArgumentException e) {
            System.out.println("Loại: "
                    + e.getClass().getSimpleName());
            System.out.println("Là NumberFormatException: "
                    + (e instanceof NumberFormatException));
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 NumberFormatHierarchyDemo.java
java NumberFormatHierarchyDemo
```

**Exact stdout**:

```text
Loại: NumberFormatException
Là NumberFormatException: true
```

Even though the handler declares `IllegalArgumentException`, the actual runtime object is still `NumberFormatException`. This is useful if the current layer wants to respond uniformly to any invalid argument.

If different handling is needed, the more specific handler must come before the parent handler:

```java
try {
    parseInput();
} catch (NumberFormatException e) {
    handleNumberFormat(e);
} catch (IllegalArgumentException e) {
    handleOtherInvalidArgument(e);
}
```

This is an **illustrative skeleton**; the helper methods must be defined. You must not reverse the two handlers, as placing the parent handler first makes the child handler unreachable.

## 10. Do Not Use `IllegalArgumentException` for Every Input Error

Some JDK APIs use **specialized unchecked classes**:

- A required reference being `null` may result in `NullPointerException`, especially when using `Objects.requireNonNull`.
- An out-of-range index in a collection may be `IndexOutOfBoundsException`.
- An invalid numeric string is usually `NumberFormatException` (a branch of `IllegalArgumentException`).
- A method may choose a **custom exception** so callers can distinguish specific business errors.

Example with `Objects.requireNonNull`:

```java
String normalized(String value) {
    java.util.Objects.requireNonNull(
            value, "value không được null");
    if (value.isBlank()) {
        throw new IllegalArgumentException(
                "value không được rỗng");
    }
    return value.trim();
}
```

This is an **illustrative method**. `null` is distinguished from an empty string in the contract: the former throws `NullPointerException` with a clear message, while a whitespace-only string is rejected with `IllegalArgumentException`.

There is no Java rule forcing every application codebase to use the exact combination above. However, using semantically accurate JDK types helps callers read APIs and anticipate errors better.

## 11. "Invalid Argument" Errors Can Come from User Data

An invalid parameter is not necessarily a programmer bug. Input from HTTP, forms, files, or CLI can be invalid in an **expected** way. `IllegalArgumentException` can still be thrown in an API that enforces strict preconditions, but the layer receiving external data should consider how to **translate it into a valid response**.

For example, a user enters `-5` for quantity. If this is a common branch in the UI, a better solution may be:

1. Validate the value at the **input boundary**.
2. Return a structured set of validation errors indicating which field is invalid.
3. Only pass valid objects into the domain service.
4. Use `IllegalArgumentException` as a **guardrail protecting API invariants**, not as the control mechanism for every normal UI branch.

An unchecked exception should not accidentally turn a bad user request into a generic server error. HTTP systems often need to map it to a 4xx response or an appropriate business message by design, but **a single HTTP status code right for every situation cannot be inferred from the superclass alone**.

What to avoid is catching `IllegalArgumentException` at the boundary and always assuming "it must be a user error." It could originate from an **internal code bug**, a library, or another wrong call inside the service.

## 12. `IllegalStateException` Does Not Apply Only to a Single Object

"State" can be:

- Object lifecycle: created → open → closed.
- Transaction phase: new → active → committed/rolled back.
- Workflow status: draft → approved → published.
- Resource state: connected/disconnected, initialized/uninitialized.
- Coordination state in a component: the system is not ready to accept tasks yet.
- An invariant has been violated so the current action cannot be performed.

Data reader example:

```java
class DataReader {
    private boolean open;

    void open() {
        if (open) {
            throw new IllegalStateException("Đã mở");
        }
        open = true;
    }

    String read() {
        if (!open) {
            throw new IllegalStateException(
                    "Chưa mở hoặc đã đóng");
        }
        return "data";
    }

    void close() {
        open = false;
    }
}
```

This is an **illustrative class without `main`**. The `open` and `read` methods have state-dependent contracts. `close` in the example is designed to be idempotent (calling it multiple times does not throw); this is a **design choice**, not that every Java resource must reject or accept closing twice in the same way.

When a real API implements `AutoCloseable` or `Closeable`, follow the specific resource-closing contract—including checked `IOException` if declared—rather than replacing all closing errors with `IllegalStateException` by default.

## 13. A State Machine Model Makes Rules Clearer

When there are multiple states, instead of several booleans that can easily conflict, you can use an `enum` and a state transition table:

| Current state | Action | Next state / Result |
| --- | --- | --- |
| `NEW` | `start()` | `RUNNING` |
| `RUNNING` | `finish()` | `DONE` |
| `NEW` | `finish()` | `IllegalStateException` |
| `DONE` | `start()` | `IllegalStateException` |
| `RUNNING` | `start()` | `IllegalStateException` |

If an action takes arguments, you can add separate rules for the valid argument domain and use `IllegalArgumentException` when appropriate.

Runnable example **`StateMachineDemo.java`**:

```java
public class StateMachineDemo {
    enum Phase {
        NEW, RUNNING, DONE
    }

    static class Task {
        private Phase phase = Phase.NEW;

        void start() {
            if (phase != Phase.NEW) {
                throw new IllegalStateException(
                        "start chỉ hợp lệ ở NEW");
            }
            phase = Phase.RUNNING;
        }

        void finish() {
            if (phase != Phase.RUNNING) {
                throw new IllegalStateException(
                        "finish chỉ hợp lệ ở RUNNING");
            }
            phase = Phase.DONE;
        }

        Phase phase() {
            return phase;
        }
    }

    public static void main(String[] args) {
        Task task = new Task();

        try {
            task.finish();
        } catch (IllegalStateException e) {
            System.out.println("Bắt: " + e.getMessage());
        }

        task.start();
        task.finish();
        System.out.println("Phase: " + task.phase());

        try {
            task.start();
        } catch (IllegalStateException e) {
            System.out.println("Bắt: " + e.getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 StateMachineDemo.java
java StateMachineDemo
```

**Exact stdout**:

```text
Bắt: finish chỉ hợp lệ ở RUNNING
Phase: DONE
Bắt: start chỉ hợp lệ ở NEW
```

An explicit state machine makes it easier to decide when an error is an **inappropriate state** and prevents operations that break invariants. In complex applications, transactions, timeouts, and concurrency must also be considered, but the core remains **checking the state before transitioning**.

## 14. Constructors and Writing Messages for Both Exceptions

Both `IllegalArgumentException` and `IllegalStateException` have the familiar constructors:

```java
new IllegalArgumentException();
new IllegalArgumentException("Sai giá trị");
new IllegalArgumentException(new RuntimeException("gốc"));
new IllegalArgumentException("Không thể nhận giá trị", cause);

new IllegalStateException();
new IllegalStateException("Chưa khởi tạo");
new IllegalStateException(new RuntimeException("gốc"));
new IllegalStateException("Không thể đổi trạng thái", cause);
```

These are **illustrative expressions**, assuming a variable `cause` of type `Throwable` is already declared. Both classes allow passing a detail message and a cause via constructors.

Purpose:

- **Message** explains which contract was violated, what was expected, and what the current value/state is if allowed to be disclosed.
- **Cause** preserves an earlier `Throwable` when you intentionally translate abstractions.
- **Stack trace** helps identify where the new exception object was created.
- **Suppressed exceptions** are separate data on `Throwable`, not automatically attached just by choosing one of these two classes.

The message can be `null` if a constructor is called without providing details. However, in public APIs with many failure branches, clear messages reduce diagnostic time.

Avoid messages that only say `"invalid"` or `"bad state"` without context.

## 15. Writing Messages So Callers and Maintainers Know How to Fix Them

A good message usually includes:

1. **Parameter name or operation name**: `timeoutMillis`, `priority`, `send`.
2. **Expected valid condition**: must be positive, within range, must call `open` first.
3. **Relevant actual data**: for example `-1` or phase `CLOSED`.
4. **No sensitive information**: tokens, passwords, identifying data, or confidential request payloads.
5. **Do not use message text as a stable error code**; the text may change or be localized.

Example message for `IllegalArgumentException`:

```java
throw new IllegalArgumentException(
        "pageSize phải thuộc [1, 100], nhận: " + pageSize);
```

Example message for `IllegalStateException`:

```java
throw new IllegalStateException(
        "Không thể send khi phase=" + phase
        + "; cần phase=CONNECTED");
```

These are **two illustrative statements**, assuming `pageSize` and `phase` are in scope. They provide clearer remediation conditions than just writing `"error"`.

In user-facing error APIs, exceptions should be translated into curated error codes/display statuses rather than exposing unreviewed technical messages.

## 16. `IllegalArgumentException`, `NullPointerException`, and Null Contracts

Choices around null need to be consistent. If an API does not accept `null`, Java provides:

```java
import java.util.Objects;

class NameService {
    static String normalize(String name) {
        Objects.requireNonNull(name, "name không được null");
        if (name.isBlank()) {
            throw new IllegalArgumentException(
                    "name không được chỉ có khoảng trắng");
        }
        return name.strip();
    }
}
```

This is an **illustrative class without `main`**, using Java 17. `Objects.requireNonNull` throws `NullPointerException` if `name == null`. A whitespace-only string throws `IllegalArgumentException` per its own contract.

If a codebase has chosen `IllegalArgumentException` for all invalid inputs including null, that may be an internal convention; however, when using a JDK API with a specific contract, **do not override documented exception expectations**.

Important: `Objects.requireNonNull` only validates non-nullness; it does not automatically guarantee a non-empty string, valid data format, or valid object state.

## 17. Should `IllegalStateException` Be Used to Wrap System Errors?

`IllegalStateException` has a constructor with `cause`, so it can be used to describe "the component is not ready because of a lower-level error." But that should **fit the semantics** of the API.

For example, service-level code might not want to expose checked `IOException` and wants to indicate it cannot proceed due to initialization state:

```java
try {
    initializeFromFile();
} catch (java.io.IOException e) {
    throw new IllegalStateException(
            "Không thể khởi tạo cấu hình", e);
}
```

This is an **illustrative snippet**, requiring `initializeFromFile()` to be defined.

Notes:

- The new `IllegalStateException` has its stack trace where the wrapper is created.
- `getCause()` retains the original `IOException`, including its own message/trace.
- The wrapper is unchecked, so the caller's checked exception contract has changed.
- This choice is only appropriate if the error genuinely represents a state in which the current layer cannot perform the operation.
- If the I/O error is an important part of the contract that callers need to handle specifically, continuing to declare `IOException` or using a checked domain exception may be more appropriate.

Do not write `throw new IllegalStateException(e.getMessage())` if the goal is to preserve the cause: that approach **does not attach `cause`**.

## 18. Java 17 Example: Wrapping Cause and Inspecting Runtime Type

Save **`CauseDemo.java`**:

```java
import java.io.IOException;

public class CauseDemo {
    static void readConfig() throws IOException {
        throw new IOException("Tệp cấu hình hỏng");
    }

    static void startService() {
        try {
            readConfig();
        } catch (IOException e) {
            throw new IllegalStateException(
                    "Service chưa sẵn sàng", e);
        }
    }

    public static void main(String[] args) {
        try {
            startService();
        } catch (IllegalStateException e) {
            System.out.println("Loại: "
                    + e.getClass().getSimpleName());
            System.out.println("Message: " + e.getMessage());
            System.out.println("Cause: "
                    + e.getCause().getClass().getSimpleName());
            System.out.println("Cause message: "
                    + e.getCause().getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 CauseDemo.java
java CauseDemo
```

**Exact stdout**:

```text
Loại: IllegalStateException
Message: Service chưa sẵn sàng
Cause: IOException
Cause message: Tệp cấu hình hỏng
```

The wrapper allows the service layer to add context without losing the root cause. However, wrapping a technical error into `IllegalStateException` must consider API compatibility; callers that previously caught `IOException` will no longer receive it directly.

If an exception is wrapped and re-wrapped across multiple layers, avoid creating redundant wrappers that repeat information without adding context. Cause chains are helpful, but too many wrapping layers make traces long and diagnostics hard to read.

## 19. Specific `catch` and Handler Ordering

The two types are sibling classes: `IllegalArgumentException` does not extend `IllegalStateException` and vice versa. They can be caught separately:

```java
try {
    doWork();
} catch (IllegalArgumentException e) {
    reportInvalidArgument(e);
} catch (IllegalStateException e) {
    reportInvalidState(e);
}
```

This is an **illustrative skeleton**; the methods must be defined. Two handlers allow choosing different responses according to the **operation's contract**.

If you want to handle them the same way, multi-catch is also valid:

```java
catch (IllegalArgumentException | IllegalStateException e) {
    System.out.println("Không thực hiện được: " + e.getMessage());
}
```

This is an **illustrative handler snippet**. The multi-catch parameter is implicitly `final` and cannot be reassigned.

Since both are `RuntimeException`, a `catch (RuntimeException e)` can catch them along with other runtime exceptions. Choose a broad handler only when that boundary truly has the responsibility to handle every caught type; do not swallow all exceptions just to keep the program running.

If `catch (RuntimeException e)` is present alongside specific catches, **the specific handlers must come before** the parent handler to avoid an unreachable catch.

## 20. Connecting with Existing JDK APIs

Look at a few typical contracts:

- `Iterator.remove()` can throw `IllegalStateException` when `next()` has not been called yet or `remove()` has already been called after the most recent `next()`.
- `java.util.Scanner` can throw `IllegalStateException` if the scanner is closed and disallowed operations are called.
- `Integer.parseInt` uses `NumberFormatException` for unparseable strings.
- `Objects.requireNonNull` uses `NullPointerException` when an argument is missing.
- `List.get(index)` usually throws `IndexOutOfBoundsException` if the index is invalid.

However, do not assume that **every "closed" JDK class must throw `IllegalStateException`**. For example, some stream or file APIs may throw `IOException`, `UncheckedIOException`, or a specialized type according to their own contracts.

The right way to learn is to understand the **general meaning** of the two exceptions, then read the exact JavaDoc of each API to know the conditions and exception types that API commits to.

## 21. Example: `Iterator.remove()` and Iterator State

`Iterator.remove()` is an example with a clear meaning of method-call state.

Save **`IteratorStateDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;

public class IteratorStateDemo {
    public static void main(String[] args) {
        List<String> values =
                new ArrayList<>(Arrays.asList("A", "B"));
        Iterator<String> it = values.iterator();

        try {
            it.remove();
        } catch (IllegalStateException e) {
            System.out.println("remove trước next: IllegalStateException");
        }

        System.out.println("next: " + it.next());
        it.remove();
        System.out.println("Sau remove: " + values);

        try {
            it.remove();
        } catch (IllegalStateException e) {
            System.out.println("remove hai lần: IllegalStateException");
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 IteratorStateDemo.java
java IteratorStateDemo
```

**Exact stdout** with `ArrayList` on Java 17:

```text
remove trước next: IllegalStateException
next: A
Sau remove: [B]
remove hai lần: IllegalStateException
```

Before `next()`, the iterator does not yet have a valid current element to remove. After `next()`, one `remove()` call is valid. If `remove()` is called again without a new `next()`, the iterator state does not allow further removal.

This is an **API usage-order error**, not a parameter value error, because `remove()` takes no parameters.

## 22. Do Not Use Exceptions to Replace Every Business Outcome

Suppose a user tries to buy a quantity greater than available stock. An API might choose:

- Return a result type such as `InsufficientStock`, `Rejected`, or `Result<Success, Failure>` in the project's idiom.
- Throw a custom domain exception when the system treats this as an exceptional failure that should propagate to a common handler.
- Use an unchecked exception when the behavior is a **violation of a published precondition**, not a common business branch.

`IllegalArgumentException` or `IllegalStateException` does not always express "out of stock" well; for example, "order quantity is valid, but inventory changed" carries a different business meaning than "negative argument" or "session not open."

Choose exceptions according to the **intended contract**:

| Case | Usually appropriate response |
| --- | --- |
| Caller programmatically passes wrong value per precondition | `IllegalArgumentException` |
| Caller calls in wrong phase/lifecycle | `IllegalStateException` |
| User frequently enters invalid data | Return structured validation errors at the boundary |
| Expected business rejection | Domain result or clearly designed exception |
| System I/O failure | `IOException` or wrapper/domain exception per contract |
| Task interruption | Preserve `InterruptedException`/interrupt flag per contract |
| Internal bug causing NPE | Fix the cause; do not convert NPE to either of the two types by default |

There is no rule that "every unchecked exception is a bug" or "every checked exception is recoverable." Context and contract decide.

## 23. Validation Order and Atomicity of State Changes

A well-designed method should validate **before** performing side effects that are hard to undo, if possible:

```java
void update(int newLimit) {
    if (newLimit < 1) {
        throw new IllegalArgumentException(
                "newLimit phải dương");
    }
    if (closed) {
        throw new IllegalStateException(
                "Không thể update sau close");
    }
    limit = newLimit;
}
```

This is an **illustrative method**, with fields `closed` and `limit`.

If the order were changed to write `limit` first and then check `closed`, the method could throw `IllegalStateException` **after already mutating state**, misleading the caller into thinking the operation had no effect at all. In simple cases, checking before assignment helps maintain invariants.

However, in systems with transactions or I/O, "checking first" is not enough to guarantee absolute atomicity. Side effects can occur externally, transactions can fail midway, and multiple threads can race to change state. Appropriate synchronization/transaction tools are needed.

## 24. Concurrency: State Checks and Mutations Must Coordinate

A common mistake is checking the state of a shared object and then mutating it without synchronization:

```java
if (!closed) {
    // Another thread may call close() here.
    doWork();
}
```

This is an **illustrative skeleton**, not a thread-safe design. Between the check and `doWork()`, another thread could change the state. This is called a **check-then-act** race window.

Depending on the contract, you can:

- Guard the check and state transition region with `synchronized` or a lock.
- Use an atomic state transition with `AtomicReference` and `compareAndSet`.
- Allow only a single thread to own the object; document that the class is not thread-safe.
- Use transactions or appropriate synchronization primitives when state lives outside Java memory.

Throwing `IllegalStateException` must not be treated as solving concurrency by itself. It only **reports a violated invariant or a rejected operation** at the moment the code checks.

A `volatile boolean closed` variable can improve visibility of updates across threads, but **does not automatically turn a check-then-act sequence into an atomic operation**.

## 25. Example of Atomizing a State Transition

The program **`AtomicStateDemo.java`** uses `AtomicReference` to allow transitioning from `NEW` to `STARTED` only once:

```java
import java.util.concurrent.atomic.AtomicReference;

public class AtomicStateDemo {
    enum State {
        NEW, STARTED
    }

    static class SingleStart {
        private final AtomicReference<State> state =
                new AtomicReference<>(State.NEW);

        void start() {
            if (!state.compareAndSet(State.NEW, State.STARTED)) {
                throw new IllegalStateException(
                        "Đã start trước đó");
            }
        }

        State state() {
            return state.get();
        }
    }

    public static void main(String[] args) {
        SingleStart task = new SingleStart();
        task.start();
        System.out.println("State: " + task.state());

        try {
            task.start();
        } catch (IllegalStateException e) {
            System.out.println("Bắt: " + e.getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 AtomicStateDemo.java
java AtomicStateDemo
```

**Exact stdout**:

```text
State: STARTED
Bắt: Đã start trước đó
```

`compareAndSet` checks and updates the reference in a single atomic operation at the scope of the `state` variable, preventing two calls from both successfully transitioning from `NEW`. This is **not** proof that all side effects of a task are synchronized; if `start()` also opens connections or writes files, they must be controlled under their own contract.

The `IllegalStateException` type still reflects a repeated operation disallowed in the **current state**.

## 26. Using JavaDoc `@throws` to Publish Contracts

Because the two exceptions are not forced to appear in the method signature, **documentation** plays an important role:

```java
/**
 * Configures the connection limit before the server starts.
 *
 * @param limit number of connections, from 1 to 500
 * @throws IllegalArgumentException if limit is outside [1, 500]
 * @throws IllegalStateException if the server has already started
 */
public void configure(int limit) {
    if (limit < 1 || limit > 500) {
        throw new IllegalArgumentException(
                "limit ngoài [1, 500]");
    }
    if (started) {
        throw new IllegalStateException(
                "Server đã khởi động");
    }
    maxConnections = limit;
}
```

This is an **illustrative method** in a class with fields `started` and `maxConnections`. JavaDoc `@throws` describes **the conditions under which errors occur**. It is not required in the signature:

```java
public void configure(int limit)
        throws IllegalArgumentException, IllegalStateException
```

This is an **illustrative declaration line**. Listing unchecked exceptions in `throws` is valid, but it does not impose a catch-or-declare obligation on callers. JavaDoc is usually the more appropriate place to describe preconditions and state conditions.

If a project's codebase has a policy of declaring `throws` for certain unchecked exceptions, clearly distinguish that as a **documentation/design convention**, not a compiler checked-exception requirement.

## 27. Catch Ordering and Propagation Behavior

When a method throws `IllegalArgumentException` or `IllegalStateException`, Java transfers control to the matching handler according to `try/catch` rules. If the handler finishes normally, the program continues **after the `try/catch` block**, without automatically re-running the failed call.

```java
try {
    setPort(70000);
    System.out.println("Không tới đây");
} catch (IllegalArgumentException e) {
    System.out.println("Giá trị cổng sai");
}
System.out.println("Tiếp tục sau catch");
```

This is an illustrative code snippet requiring `setPort` to be declared. If there is no matching handler, the exception continues propagating to the caller. Any associated `finally` blocks still follow their own completion rules; a `finally` throwing a new error can mask the propagating error, while `try-with-resources` can retain `close()` errors as suppressed exceptions. Those rules apply **to all exception types**, not as behavior specific to the two classes being compared.

An important takeaway of this lesson: catching an `IllegalStateException` **does not mean** the state has been recovered. The handler must ensure valid postconditions or continue reporting failure to the boundary that owns the policy.

## 28. Broad Catches Can Hide Bugs

Dangerous example:

```java
try {
    processOrder();
} catch (RuntimeException ignored) {
    return "SUCCESS";
}
```

This is an **anti-pattern skeleton**, without defining `processOrder` and the enclosing method. The handler catches precondition errors, state errors, `NullPointerException`, index errors, and other runtime errors, then returns a **false success** result.

Instead, an HTTP/CLI/job boundary needs to:

- Determine whether the failure belongs to **caller input** or an **internal bug/state**.
- Log appropriate information for diagnostics without leaking sensitive data.
- Return a failure status per contract, without treating catching an exception as successful recovery.
- Preserve `cause`/stack trace when translating abstractions.
- Choose specific handling when recovery is genuinely possible; unexpected errors may need to be reported to a monitoring system.

**Do not automatically map every `IllegalArgumentException` to "user entered invalid input."** An internal library might throw it because the service computed a bad parameter, which is a server-side bug.

## 29. When to Create a Custom Exception Instead of Using These Two?

`IllegalArgumentException` and `IllegalStateException` express common contract violations well. If callers genuinely need to **distinguish a specialized condition**, a custom exception can be useful:

```java
class InvalidWorkflowStateException
        extends IllegalStateException {
    InvalidWorkflowStateException(String message) {
        super(message);
    }
}
```

This is an **illustrative class**, without `main`. The new type is still unchecked and still belongs to the `IllegalStateException` branch, so callers can catch it specifically or catch the parent.

Similarly, an application can build:

```java
class InvalidCommandArgumentException
        extends IllegalArgumentException {
    InvalidCommandArgumentException(String message) {
        super(message);
    }
}
```

However, there is no need to create a separate class if the difference only lies in a message string and callers do not need to classify by type. Too many pointless exception classes make an API harder to learn.

If the new condition is an **expected business failure** (for example, insufficient balance), consider a result/domain error type or a dedicated custom exception with a clear contract, rather than forcing everything into two core Java types.

## 30. Testing Should Verify Exception Type and Invariants

Simply checking that "an exception was thrown" is not enough. You should verify:

- **Exact type** `IllegalArgumentException` for invalid arguments.
- **Exact type** `IllegalStateException` for invalid order/state.
- **Expected message/error code** if that is part of the tested contract, avoiding reliance on unstable wording.
- **No unintended state mutation** after a failed call.
- **Valid calls still succeed**.
- **Retrying after a valid state transition** works according to the rules.
- **Cause** is preserved if the code wraps another exception.
- Boundary cases: 0, -1, maximum value, closed/completed state, duplicate calls.

JUnit provides `assertThrows` to verify the exception type and inspect `getMessage()` and `getCause()`. Without JUnit, you can write plain Java checks to prove it.

## 31. Java 17 Program Self-Testing Both Exception Types

Save **`ArgumentStateAssertionsDemo.java`**:

```java
public class ArgumentStateAssertionsDemo {
    static class Counter {
        private boolean closed;
        private int value;

        void add(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException(
                        "amount phải dương");
            }
            if (closed) {
                throw new IllegalStateException(
                        "Counter đã đóng");
            }
            value += amount;
        }

        void close() {
            closed = true;
        }

        int value() {
            return value;
        }
    }

    public static void main(String[] args) {
        Counter counter = new Counter();

        try {
            counter.add(0);
            throw new AssertionError("Thiếu IllegalArgumentException");
        } catch (IllegalArgumentException e) {
            if (!"amount phải dương".equals(e.getMessage())) {
                throw new AssertionError("Sai message đối số");
            }
            System.out.println("PASS argument");
        }

        counter.add(5);
        counter.close();

        try {
            counter.add(3);
            throw new AssertionError("Thiếu IllegalStateException");
        } catch (IllegalStateException e) {
            if (!"Counter đã đóng".equals(e.getMessage())) {
                throw new AssertionError("Sai message trạng thái");
            }
            System.out.println("PASS state");
        }

        if (counter.value() != 5) {
            throw new AssertionError("Đã sửa trạng thái sai");
        }
        System.out.println("PASS invariant");
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 ArgumentStateAssertionsDemo.java
java ArgumentStateAssertionsDemo
```

**Exact stdout**:

```text
PASS argument
PASS state
PASS invariant
```

The example intentionally uses `AssertionError` to fail the test without depending on the `-ea` flag. The output proves both paths throw the right exception type and **`counter` remains equal to 5** after the invalid call is rejected.

In real projects, testing multithreading, transactions, or resources may require additional specialized tools; this sample only demonstrates the argument/state contract of a simple object.

## 32. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "The two exception types are the same because both are RuntimeExceptions." | Both are unchecked, but they have different meanings: invalid argument vs. disallowed state. |
| "`IllegalArgumentException` is checked because its name contains Exception." | False. It extends `RuntimeException`, so it is unchecked. |
| "`IllegalStateException` only appears when an object is completely broken." | No. It can report wrong-phase operations such as `send` before `connect`. |
| "Every invalid input must throw `IllegalArgumentException`." | No. There are specialized JDK types, and expected validation errors can use structured results. |
| "Every unwanted business state must throw `IllegalStateException`." | No. A valid domain result may be more appropriate than an exception. |
| "You must write `throws IllegalStateException` for the compiler to allow throwing it." | No. It is an unchecked exception. |
| "A `catch (IllegalArgumentException)` handler catches `IllegalStateException` too." | No. They are sibling classes. |
| "`NumberFormatException` is unrelated to `IllegalArgumentException`." | False. It is a subclass of `IllegalArgumentException`. |
| "`NullPointerException` is a subclass of `IllegalArgumentException`." | False. It is a separate branch under `RuntimeException`. |
| "Catching the exception means the operation succeeded." | No. The handler still needs recovery logic or proper failure reporting. |
| "If arguments are valid, the method will always succeed." | Not if state, I/O, or other conditions are unsuitable. |
| "Replacing one exception type with the other does not affect callers." | It can affect handlers, logs, tests, documentation, and recovery code. |
| "Messages can be used as business control codes." | Not recommended. Messages can change or be localized. |
| "`volatile` makes checking and updating state atomic." | No. Proper synchronization or atomic state transitions are required. |
| "Unchecked exceptions never need logging/documentation." | False. Contracts and diagnostics are still very important. |
| "An invalid value in HTTP input is always a server-side bug." | No. Distinguish user validation errors from invariant violations in internal code. |

## 33. Self-Check Questions

**1. Which type should be considered for `setRate(-1)` when rate must be non-negative?**  
`IllegalArgumentException`, because the parameter value is outside the allowed domain.

**2. `start()` called again when the process is already `STARTED` and may only start once?**  
`IllegalStateException` is usually appropriate, because the call is in the wrong state/lifecycle.

**3. `send("hi")` fails when not connected, while the string itself is valid?**  
`IllegalStateException`, because the primary cause is the connection state.

**4. Is `NumberFormatException` checked or unchecked? Which class studied here is it a subclass of?**  
Unchecked, under the `IllegalArgumentException` branch.

**5. Do you have to declare `throws IllegalArgumentException` in the method signature?**  
No. You can document it with JavaDoc `@throws`.

**6. Does `catch (IllegalArgumentException e)` catch `IllegalStateException`?**  
No, because the two classes do not inherit from each other.

**7. If you use `catch (RuntimeException e)`, does it catch both?**  
Yes, but it can also catch many other runtime exceptions; avoid overly broad handlers without a proper policy.

**8. What does `Objects.requireNonNull(null)` usually throw?**  
`NullPointerException`.

**9. When the value is valid but the object is already `CLOSED`, which type should you lean toward?**  
`IllegalStateException`, if the contract specifies the operation is not allowed in that state.

**10. If the argument value is invalid and the object is also `CLOSED`, does Java automatically prioritize one error?**  
No. The check order and contract are decided by the API designer.

**11. When wrapping `IOException` into `IllegalStateException`, how do you preserve the cause?**  
Use the constructor `new IllegalStateException("...", e)` and keep `e` in `getCause()`.

**12. Can `IllegalStateException` be thrown after an object has had `close()` called?**  
Yes, if the class contract specifies subsequent operations are forbidden and that type fits; many specific APIs may use a different exception.

**13. Why should we not treat every `IllegalArgumentException` on a server as a user error?**  
It could be caused by internal code passing a wrong parameter; only the boundary that knows the data source can classify it accurately.

**14. Does `IllegalStateException` prevent race conditions?**  
No. The exception only reports an error; synchronization/atomic transitions are needed if state is shared across threads.

**15. If a method throws IAE and is caught by the caller, does Java automatically re-run that call?**  
No. The caller decides whether to retry with different arguments.

**16. How should JavaDoc be written for an API that has both types?**  
Write `@throws IllegalArgumentException` for value preconditions and `@throws IllegalStateException` for state/lifecycle conditions.

**17. Which type name makes more sense when `Iterator.remove()` is called before `next()`?**  
`IllegalStateException` per the `Iterator` contract.

**18. If out-of-stock is a normal branch in a feature, are you required to use one of these two exceptions?**  
No. You can return a business result with a status or an appropriate custom domain error.

**19. Why not catch all `RuntimeException` and return success?**  
Because it can hide real errors, break invariants, and mislead callers into thinking the operation completed.

**20. In a method with both input and state validation, why validate before side effects?**  
To avoid partially mutating the object and then throwing an error, leaving the state and returned signal inconsistent.

## 34. Design and Review Checklist

When deciding between `IllegalArgumentException` and `IllegalStateException`:

1. **Identify argument preconditions:** valid domain, null, range, format, relationships between parameters.
2. **Identify object invariants/state:** active phase, opened/closed resource, connection, workflow.
3. **Distinguish value errors from lifecycle errors:** would the same value succeed if the state changed?
4. **Check if the standard API has a more specialized exception type:** `NumberFormatException`, `IndexOutOfBoundsException`, `NullPointerException`, etc.
5. **Check if this is an expected business branch:** do you need a result type/domain status instead of an exception?
6. **Define validation order:** when multiple conditions are wrong, which error is reported first?
7. **Check before side effects if possible:** do not mutate part of the state and then throw an easily avoidable error.
8. **Use helpful, safe messages:** parameter/state names and non-sensitive values.
9. **Do not use messages for logic routing:** use exception types or structured error codes.
10. **Publish contracts with JavaDoc `@throws`:** even though not required in the signature.
11. **Do not force callers to catch unchecked exceptions at every layer:** only handle them where real responsibility lies.
12. **At input boundaries, separate user errors from internal bugs:** do not map blindly.
13. **If wrapping another error, preserve the cause:** use the `(String, Throwable)` constructor.
14. **If using multiple threads, protect check-then-act:** lock/atomic/ownership by design.
15. **Test both invalid arguments and invalid state:** along with valid paths and boundary cases.
16. **Verify invariants after failure:** exceptions must not mask bad state updates.
17. **Consider API compatibility impact:** changing an exception type can break caller handlers.
18. **Do not swallow `RuntimeException` and report false success.**
19. **Do not use `Error` to express application argument/state errors.**
20. **Consider custom exceptions only when genuinely needing to distinguish situations.**

## 35. Summary

`IllegalArgumentException` and `IllegalStateException` are both **unchecked `RuntimeException`s**, not forcing callers to catch-or-declare. The deciding difference is the **origin of the invalid call**:

- **`IllegalArgumentException`** is for **caller-supplied parameters that do not satisfy preconditions**, such as negative values, out-of-range values, or rejected formats.
- **`IllegalStateException`** is for **operations disallowed by the current state**, such as using an object before initialization, after closing, or repeating an invalid transition.

An API may need both: validate arguments, then validate state, then mutate data. Java does not automatically decide priority order if both are violated. When a more specific JDK type exists—such as `NullPointerException`, `IndexOutOfBoundsException`, or `NumberFormatException`—follow the contract of the API being used.

More important than the exception name itself are **clear contracts, handling at the right boundary, safe messages, preserving causes, testing invariants, and distinguishing abnormal failures from expected business outcomes**.
