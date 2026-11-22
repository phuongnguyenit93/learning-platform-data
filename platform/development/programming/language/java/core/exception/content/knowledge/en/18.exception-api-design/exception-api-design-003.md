# Use Specific Exception Types Instead of `throws Exception` in Java API Design

> **Topic:** Java Core → Exception → API Design. The `throws` clause is part of the **method contract** for checked exceptions. Declaring `throws Exception` is syntactically valid, but it is usually **too broad** for application or library APIs: callers do not know exactly which failures they need to handle, struggle to branch recovery policies, and may inadvertently depend on a contract that permits too many kinds of failure. Prefer exception types that are **meaningful, at the right level of abstraction, and sufficiently narrow**, such as `IOException`, `ParseException`, or an appropriate custom checked exception—while also recognizing that not every API needs a checked exception.

## 1. What Does `throws Exception` Mean?

A declaration:

```java
public String load() throws Exception {
    // ...
}
```

tells the Java compiler that the method may complete abruptly with a **checked exception** belonging to `Exception`, including `IOException`, `SQLException`, `ReflectiveOperationException`, custom checked exceptions, and many others. It does **not** claim that the method always fails, nor does it mean that every subtype can actually occur.

Two ideas should be kept separate:

1. **The set of checked types permitted by the signature:** `throws Exception` is broader than `throws IOException`.
2. **The failures that can actually occur:** these depend on the executing code and the methods being called.

`Exception` is also the superclass of `RuntimeException`, but unchecked subclasses such as `IllegalArgumentException` do **not** need to be listed in `throws`, even though callers may still encounter them.

### 1.1. Related Exception Type Hierarchy

```text
Throwable
├── Error                         (unchecked)
└── Exception
    ├── IOException              (checked)
    │   └── FileNotFoundException (checked)
    ├── SQLException              (checked)
    ├── ParseException            (checked)
    ├── ReflectiveOperationException (checked)
    └── RuntimeException          (unchecked)
        ├── IllegalArgumentException
        └── IllegalStateException
```

A `throws IOException` declaration does not require listing every subtype such as `FileNotFoundException`: subtypes are already covered by the superclass contract. Conversely, `throws FileNotFoundException` only advertises the narrow branch and **does not allow the method to let arbitrary other `IOException` types escape under the checked contract**.

### 1.2. Direct Comparison

```java
// Broad but syntactically valid:
static String readConfig() throws Exception {
    return java.nio.file.Files.readString(
            java.nio.file.Path.of("config.txt"));
}

// Clearer when the operation primarily involves I/O:
static String readConfigSpecific() throws java.io.IOException {
    return java.nio.file.Files.readString(
            java.nio.file.Path.of("config.txt"));
}
```

These are **two illustrative methods**, not a standalone program; both can throw an error when the real file cannot be read. The second signature accurately states the failure category directly used by the API, helping callers understand that they can choose another source, report a file read error, or stop the task.

**There is no absolute rule** requiring you to declare the smallest conceivable subclass. Choose a type that is **specific enough for the caller's decisions** and stable enough across internal changes.

## 2. Why Overly Broad Declarations Make Handling Difficult for Callers

Consider the API:

```java
interface DocumentRepository {
    String load(String documentId) throws Exception;
}
```

A caller does not know whether `load` can throw checked `IOException`, `SQLException`, `ParseException`, or something else. Calling code must account for all of `Exception`.

```java
try {
    String text = repository.load("DOC-1");
    System.out.println(text);
} catch (Exception e) {
    // Handle generically or propagate upward.
}
```

This is a snippet that requires an initialized `repository` variable. `catch(Exception)` can turn into an overly broad branch covering multiple failures with **different meanings**:

- File does not exist: you might let the user pick another file.
- Timeout from a dependent service: you might retry **if the operation is safe to retry**.
- Invalid document: you need to report bad data, typically without retrying.
- Programming bug such as `NullPointerException`: should not be accidentally treated as a transient error that can be retried.

**A broad catch is not a syntax error**, but if the code "logs and returns null" or "retries in every case", it can mask bugs and break the result contract.

### 2.1. What Can the Compiler Help With?

With:

```java
void handle() throws Exception {
    repository.load("DOC-1");
}
```

the compiler sees that the calling method is covered, but it does not help maintainers know whether they need to handle file, database, parsing, or business errors.

If the signature is made specific:

```java
interface DocumentRepository {
    String load(String documentId)
            throws java.io.IOException, DocumentFormatException;
}
```

callers looking at the API can separate **I/O recovery** from **rejecting invalid format**. Here, `DocumentFormatException` is a custom checked exception that must be declared in the project (an example follows below).

### 2.2. Can You Still Write `catch(IOException)` When an API `throws Exception`?

There may be cases where `catch(IOException)` is valid at compile time because the API declares `throws Exception`—but that handler is **not enough** to handle all remaining checked `Exception` types.

```java
try {
    broadApi(); // Declares throws Exception.
} catch (java.io.IOException e) {
    System.out.println("I/O");
} catch (Exception e) {
    System.out.println("Other checked / other unchecked");
}
```

This is a snippet with a hypothetical `broadApi()`. The remaining `catch(Exception)` handler also catches `RuntimeException` subtypes, so if that code tries to "recover from all errors", it becomes very dangerous. **Narrowing the API signature** can reduce the need for overly broad generic handlers at the source.

## 3. Principles for Choosing Meaningful Exceptions

A good exception type helps callers answer:

1. **What failed?** File reading, parsing, connection, state validation, or a contract violation?
2. **Who can handle it?** The immediate caller, the service layer, a retry layer, the UI, or only a logging boundary?
3. **What can be done?** Try another input, fall back, retry conditionally, cancel the operation, or report an error to the user?
4. **Should internal details be exposed?** Does a domain service really need to expose `SQLException` publicly?
5. **Is the type stable when the implementation changes?** If storage changes from files to HTTP, does the API need to change `throws IOException`?

The answers can lead to:

- **An appropriate JDK type**, such as `IOException` when the API is inherently an I/O operation.
- **A custom checked exception**, such as `DocumentFormatException extends Exception` for data required to have a valid format.
- **A custom unchecked exception**, such as `InvalidTransitionException extends IllegalStateException` for state violations in an operation's contract.
- **A result type**, such as `ValidationResult` if multiple input issues are a normal expected outcome rather than something to throw.
- **No checked exception declared**, if the method has no checked failure path that needs to be exposed.

**Specificity does not mean creating a new class for every error line.** An exception type should reflect a **useful handling classification**, not just a technical name.

## 4. `throws Exception` vs `throws IOException`

Suppose a library provides a function to read text. The signature:

```java
static String readText(Path path) throws IOException;
```

clearly states that failures are I/O-related. Callers can catch `IOException`, inspect the cause/metadata, report an error, or switch to a fallback source.

By contrast:

```java
static String readText(Path path) throws Exception;
```

permits many more checked failures. When releasing an API, a broad choice can force callers to handle `Exception` even though the implementation only reads a file. Over the long term, a broad signature reduces the documentation value of the API.

### 4.1. Java 17 — Demo 1: Distinguishing `IOException` and Its Subtype

Create **`SpecificFileContractDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

public class SpecificFileContractDemo {
    static String read(String key) throws IOException {
        if ("missing".equals(key)) {
            throw new FileNotFoundException("Không thấy " + key);
        }
        if ("offline".equals(key)) {
            throw new IOException("Thiết bị không sẵn sàng");
        }
        return "data:" + key;
    }

    public static void main(String[] args) {
        for (String key : new String[] {
                "ok", "missing", "offline"
        }) {
            try {
                System.out.println("OK: " + read(key));
            } catch (FileNotFoundException e) {
                System.out.println("MISSING: "
                        + e.getClass().getSimpleName());
            } catch (IOException e) {
                System.out.println("IO: "
                        + e.getClass().getSimpleName());
            }
        }
    }
}
```

Compile/run on JDK 17+:

```bash
javac -encoding UTF-8 SpecificFileContractDemo.java
java SpecificFileContractDemo
```

Stdout:

```text
OK: data:ok
MISSING: FileNotFoundException
IO: IOException
```

Explanation:

- `read` declares **`throws IOException`**.
- Both `FileNotFoundException` and `IOException` are valid to escape, because the former is a subtype of the latter.
- Callers **are allowed** to place the specialized catch before the general catch.
- Reversing the order (catching `IOException` before `FileNotFoundException`) causes an unreachable handler compile error.
- This example intentionally creates a controlled `IOException`; no real file or I/O environment is needed to reproduce it.
- There is no reason to add `throws Exception` to `read` just because the method can fail.

### 4.2. Choosing a Supertype at the Right Level

You do not necessarily have to declare `throws FileNotFoundException` just because the current implementation only opens a file. An I/O API may be more sensible declaring `IOException` because in the future it may encounter other I/O errors of the same nature. That is a **more stable contract** while still being accurate about the failure category.

Conversely, if the API means "look up a filename and only expose the not-found case" and guarantees to catch/translate other I/O failures, `FileNotFoundException` or a dedicated domain type may make sense. The rule is to **match the promised behavior**, not mechanically pick the deepest subtype.

## 5. Two Independent Checked Failures: List Both Explicitly

A method may encounter **two genuinely different failure categories** that callers need to distinguish. In that case, instead of `throws Exception`, declare multiple specific types:

```java
String importDocument(String raw)
        throws IOException, DocumentFormatException;
```

This is an illustrative method signature. I/O errors may be transient; data format errors usually require fixing the input. They have no subtype relationship with each other.

### 5.1. Java 17 — Demo 2: I/O and Contract-Violating Data

Create **`TwoSpecificFailuresDemo.java`**:

```java
import java.io.IOException;

public class TwoSpecificFailuresDemo {
    static final class InvalidRecordException extends Exception {
        InvalidRecordException(String message) {
            super(message);
        }
    }

    static String load(String raw)
            throws IOException, InvalidRecordException {
        if ("offline".equals(raw)) {
            throw new IOException("Kho không truy cập");
        }
        if (!raw.startsWith("ID:")) {
            throw new InvalidRecordException("Sai định dạng");
        }
        return raw.substring(3);
    }

    public static void main(String[] args) {
        for (String value : new String[] {
                "ID:42", "oops", "offline"
        }) {
            try {
                System.out.println("OK: " + load(value));
            } catch (InvalidRecordException e) {
                System.out.println("FORMAT: " + e.getMessage());
            } catch (IOException e) {
                System.out.println("IO: " + e.getMessage());
            }
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 TwoSpecificFailuresDemo.java
java TwoSpecificFailuresDemo
```

Stdout:

```text
OK: 42
FORMAT: Sai định dạng
IO: Kho không truy cập
```

**Why this design is sound:**

1. `InvalidRecordException` is a **checked custom exception**, giving callers a dedicated handling branch for invalid data.
2. `IOException` represents data-access failures, not lumped together with format errors.
3. Method `load` does not declare `throws Exception`.
4. Callers can choose separate reactions for each failure category.
5. If malformed data is a very common response, consider a structured result type instead of a checked exception; the design in the example is solely to demonstrate the `throws` contract.
6. When `raw == null`, the current code will throw `NullPointerException` when calling `startsWith`. A real API should validate `null`/input invariants and document them; the demo uses non-null strings to focus on checked exceptions.

### 5.2. Multi-Catch When Handling Policies Overlap

If a caller genuinely wants to handle both checked exceptions the same way:

```java
try {
    importData();
} catch (IOException | InvalidRecordException e) {
    reportFailure(e);
}
```

This is an illustrative snippet requiring `importData`, `reportFailure`, and `InvalidRecordException` to be defined in the project. Multi-catch works when the two exception types **are not in a parent–child relationship**. You cannot write `catch(IOException | FileNotFoundException e)`, because `FileNotFoundException` is a subtype of `IOException`.

Even when handled together, **a specific signature is still useful**: API users know the exact failures that can occur and can choose separate handlers later.

## 6. When Not to Expose Infrastructure Exception Types

A domain API might use JDBC underneath:

```java
// Contract tightly couples the domain layer to the JDBC implementation:
Order loadOrder(String id) throws SQLException;
```

If the service switches from JDBC to REST or another source, should callers have to change their code even though the business contract "load an order" has not changed? That is a sign the API may be **leaking a lower-layer abstraction**.

One alternative:

```java
Order loadOrder(String id) throws OrderRepositoryException;
```

`OrderRepositoryException` is a custom checked exception meaning "the order storage layer failed". The repository/service layer **catches `SQLException`, passes it as the cause to the custom exception**, and exposes only a semantically stable contract to the domain.

### 6.1. Java 17 — Demo 3: Translating `SQLException` to a Domain Exception

Create **`ExceptionTranslationDemo.java`**:

```java
import java.sql.SQLException;

public class ExceptionTranslationDemo {
    static final class CatalogUnavailableException
            extends Exception {
        CatalogUnavailableException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static String readFromDatabase() throws SQLException {
        throw new SQLException("Database down", "08001");
    }

    static String loadCatalog()
            throws CatalogUnavailableException {
        try {
            return readFromDatabase();
        } catch (SQLException e) {
            throw new CatalogUnavailableException(
                    "Không tải được catalog", e);
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println(loadCatalog());
        } catch (CatalogUnavailableException e) {
            System.out.println("Boundary: "
                    + e.getClass().getSimpleName());
            System.out.println("Cause: "
                    + e.getCause().getClass().getSimpleName());
            SQLException sql = (SQLException) e.getCause();
            System.out.println("SQLState: " + sql.getSQLState());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 ExceptionTranslationDemo.java
java ExceptionTranslationDemo
```

Stdout:

```text
Boundary: CatalogUnavailableException
Cause: SQLException
SQLState: 08001
```

**Significance:**

- `readFromDatabase()` keeps the `throws SQLException` contract, appropriate for the infrastructure level.
- `loadCatalog()` translates the error at the **abstraction boundary** and declares `CatalogUnavailableException`.
- The `super(message, cause)` constructor preserves the real `SQLException` as the cause; do not throw an exception containing only `e.getMessage()` and lose the cause chain.
- Service callers only need to know about catalog failure, without being forced to depend directly on the JDBC package in the signature.
- The demo casts `SQLException` in `main` to prove the cause; a general caller **should not** cast every `getCause()` to `SQLException` if the implementation might change. Classify using `instanceof` or an appropriate diagnostic policy.

### 6.2. Exception Translation Is Not Hiding Errors

An anti-pattern:

```java
try {
    saveToDatabase();
} catch (SQLException ignored) {
    return true; // INTENTIONALLY WRONG: fakes success when the operation failed.
}
```

This is an illustrative snippet without `saveToDatabase`. Unless there is a designed fallback/compensation, **do not swallow errors**. Translating errors must preserve the failure state and serve the abstraction, not turn an error into success.

## 7. Checked vs Unchecked: "Specific" Does Not Mean Checked

A public method does not need `throws` for every error condition:

```java
static void setDiscount(int percent) {
    if (percent < 0 || percent > 100) {
        throw new IllegalArgumentException(
                "percent phải thuộc [0,100]");
    }
}
```

`IllegalArgumentException` is a **specific and unchecked** type, appropriate when the caller violates a precondition. The compiler does not require listing `throws IllegalArgumentException`, though Java allows listing it if you want to document it.

**Two separate decisions:**

1. Is the failure a condition that can occur in the business flow that the compiler should remind callers to handle, or is it a contract violation/runtime error?
2. Is the chosen exception type specific and meaningful to callers?

Do not turn every `IOException` into unchecked just to remove `throws`, and do not create a checked exception for every validation check.

### 7.1. Java 17 — Demo 4: Both Checked and Unchecked in One API

Create **`CheckedUncheckedContractDemo.java`**:

```java
import java.io.IOException;

public class CheckedUncheckedContractDemo {
    static int compute(int input) throws IOException {
        if (input < 0) {
            throw new IllegalArgumentException("input âm");
        }
        if (input == 0) {
            throw new IOException("Nguồn dữ liệu rỗng");
        }
        return input * 2;
    }

    public static void main(String[] args) {
        for (int input : new int[] {3, -1, 0}) {
            try {
                System.out.println("OK: " + compute(input));
            } catch (IllegalArgumentException e) {
                System.out.println("INVALID: "
                        + e.getClass().getSimpleName());
            } catch (IOException e) {
                System.out.println("IO: "
                        + e.getClass().getSimpleName());
            }
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 CheckedUncheckedContractDemo.java
java CheckedUncheckedContractDemo
```

Stdout:

```text
OK: 6
INVALID: IllegalArgumentException
IO: IOException
```

Explanation:

- `compute` declares `IOException` because it is a checked failure.
- `IllegalArgumentException` can still occur, but does not need to be listed in `throws`.
- Callers can catch the unchecked exception if they have an appropriate input-response policy; this is not needed in every piece of code.
- `int * 2` in the demo can overflow for very large inputs; the example picks small inputs. Production APIs must consider arithmetic bounds separately (`Math.multiplyExact` if needed).
- Do not interpret `throws IOException` as meaning "only `IOException`, no `RuntimeException`".

## 8. Benefits When Callers Can Write Per-Type Handlers

When an API is specific, callers can easily express **different policies**:

| Failure type | Potentially appropriate action | Should not be the default |
| --- | --- | --- |
| `FileNotFoundException` | Choose another path or report missing file | Infinite retry on the same path |
| Transient `IOException` | Bounded retry if the operation is idempotent | Retrying every I/O failure |
| `InvalidRecordException` | Request fixing the input | Retrying I/O hoping the data becomes valid |
| `SQLException` at JDBC layer | Manage transaction, inspect SQL state if needed | Exposing SQL internals in a public API |
| `CatalogUnavailableException` | Report dependent service unavailable | Casting every cause to `SQLException` |
| `IllegalArgumentException` | Fix arguments supplied by the caller | Catching, hiding the bug, and returning success |
| `IllegalStateException` | Fix operation state/sequence | Assuming a retry will fix the invariant |
| `InterruptedException` | Respect the interruption policy | Swallowing the interrupt without restoring it |

**An exception type alone does not automatically determine a retry policy.** For example, `IOException` can cover permission errors, missing files, or temporary connection drops. You need semantic metadata, idempotency, side-effect state, and business requirements.

## 9. Writing Specific `catch` Blocks and Ordering Them Correctly

In Java, handlers are evaluated top-down; subclasses must appear before superclasses if they need to be distinguished.

```java
try {
    readFile();
} catch (FileNotFoundException e) {
    handleMissingFile(e);
} catch (IOException e) {
    handleOtherIo(e);
}
```

This is a snippet with three hypothetical methods. If `catch(IOException)` is placed before `catch(FileNotFoundException)`, the latter handler becomes unreachable.

### 9.1. `catch(Exception)` Only at Boundaries That Truly Need It?

A boundary such as a CLI dispatcher, task runner, executor, or server request boundary may catch broadly to **log, convert errors into safe failure responses, and avoid breaking other orchestration**, after layers closer to the source have performed specific handling.

However:

- `catch(Exception)` also catches `RuntimeException`; do not treat every bug as an expected recoverable error.
- It does **not** catch `Error`. Catching `Throwable` is even broader and requires an extremely cautious policy.
- Broad catching at a boundary **does not justify** declaring `throws Exception` on every method at every layer.
- If a layer cannot resolve the error, it can rethrow or translate to an appropriate error, preserving the cause.
- Do not report "success" just because an exception was caught.

## 10. Java 17 — Demo 5: Multi-Catch for Independent Checked Failures

Create **`MultiCatchContractDemo.java`**:

```java
import java.io.IOException;
import java.text.ParseException;

public class MultiCatchContractDemo {
    enum Mode { OK, IO, PARSE }

    static String run(Mode mode)
            throws IOException, ParseException {
        return switch (mode) {
            case OK -> "success";
            case IO -> throw new IOException("Lỗi thiết bị");
            case PARSE -> throw new ParseException("Sai ngày", 0);
        };
    }

    public static void main(String[] args) {
        for (Mode mode : Mode.values()) {
            try {
                System.out.println("OK: " + run(mode));
            } catch (IOException | ParseException e) {
                System.out.println("FAILED: "
                        + e.getClass().getSimpleName());
            }
        }
    }
}
```

Run on JDK 17+:

```bash
javac -encoding UTF-8 MultiCatchContractDemo.java
java MultiCatchContractDemo
```

Stdout:

```text
OK: success
FAILED: IOException
FAILED: ParseException
```

Why is this valid?

- `IOException` and `ParseException` are both checked exceptions, but **have no parent–child relationship**.
- `run` explicitly declares both types.
- One multi-catch handles both if the caller chooses the same policy.
- If the handler needs different behavior, split into two `catch` blocks.
- A `switch` expression with `throw` branches is a standard feature in Java 17.
- In a multi-catch, the variable `e` has a type computed by the common lub rule and is effectively final; do not write code assuming `e` is always an `IOException`.

### 10.1. Wrong: Multi-Catching Parent and Child

```java
// INTENTIONALLY DOES NOT COMPILE:
catch (IOException | FileNotFoundException e) {
    // The two alternatives have an inheritance relationship.
}
```

Choose `catch(IOException e)` if you need unified handling, or two handlers ordered subtype first, then superclass.

## 11. Interfaces and Overriding: `throws` Is a Substitutable Contract

An interface implementation must not **widen** the list of checked exceptions compared to the overridden interface method.

```java
interface Loader {
    String load() throws IOException;
}
```

Valid:

```java
final class FileLoader implements Loader {
    @Override
    public String load() throws FileNotFoundException {
        throw new FileNotFoundException("missing");
    }
}
```

Invalid:

```java
// INTENTIONALLY DOES NOT COMPILE:
final class BroadLoader implements Loader {
    @Override
    public String load() throws Exception {
        return "x";
    }
}
```

`Exception` is broader than `IOException`, so callers of `Loader` were not promised to handle all checked subtypes of `Exception`. Implementations must respect the contract: the same checked type, an appropriate subtype, or fewer checked exceptions.

### 11.1. Java 17 — Demo 6: Interfaces and Reference Types

Create **`OverrideSpecificThrowsDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;

public class OverrideSpecificThrowsDemo {
    interface Reader {
        String read() throws IOException;
    }

    static final class FileReader implements Reader {
        @Override
        public String read() throws FileNotFoundException {
            throw new FileNotFoundException("missing");
        }
    }

    public static void main(String[] args) {
        FileReader concrete = new FileReader();
        try {
            concrete.read();
        } catch (FileNotFoundException e) {
            System.out.println("Concrete catches: "
                    + e.getClass().getSimpleName());
        }

        Reader api = concrete;
        try {
            api.read();
        } catch (IOException e) {
            System.out.println("Interface catches: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 OverrideSpecificThrowsDemo.java
java OverrideSpecificThrowsDemo
```

Stdout:

```text
Concrete catches: FileNotFoundException
Interface catches: FileNotFoundException
```

**Distinguish two things:**

1. **The compiler obligation** at the call site depends on the method resolved from the **static reference type**. `FileReader.read` declares `FileNotFoundException`; `Reader.read` declares `IOException`.
2. **The runtime exception object** is `FileNotFoundException` in both calls; upcasting the receiver to `Reader` does not turn the error object into an `IOException`.

Without a contractual reason, an implementation should not add `throws Exception` "just in case of future errors", because doing so violates the interface.

## 12. Multiple Interfaces with Different `throws`

A class may implement two interfaces that have the same method signature, where each interface lists a different checked exception. The implementation must satisfy **all** overriding rules simultaneously.

Example:

```java
interface A {
    void execute() throws IOException;
}
interface B {
    void execute() throws SQLException;
}

final class Combined implements A, B {
    @Override
    public void execute() {
        System.out.println("done");
    }
}
```

This is an illustrative snippet requiring `IOException`/`SQLException` imports. Because the two checked types are unrelated, `Combined.execute()` **must not** declare `throws IOException, SQLException`; omitting checked `throws` makes it valid for both.

Remember: `throws Exception` is even less of a fix when the interface contract is **narrower**. An implementation signature cannot arbitrarily widen the contract.

## 13. When Changing `throws`, Check Source Compatibility

The `throws` declaration is part of the checked-exception verification contract. If a public API previously had only `throws ParseException` and then adds `IOException`, a caller that only caught `ParseException` may **fail to recompile**:

~~~java
// Two illustrative signature versions, not declared together in one class.
String parse(String input) throws ParseException;
// Next version:
String parse(String input) throws ParseException, IOException;
~~~

Narrowing or removing checked `throws` can also make a caller's checked handler unreachable upon recompilation. However, changing only the `throws` clause **does not by itself change the JVM method descriptor**; you must separate *source*, *binary*, and *behavioral compatibility*. Do not change a library's public `throws` just because the current implementation no longer throws an error; check callers, overrides, and migration paths. The lesson on **compatibility impacts when changing exception contracts** analyzes the matrix and upgrade strategies in full.

## 14. Use Javadoc `@throws` to Explain Conditions, Not Just List Types

The `throws` clause informs the compiler of checked exceptions; `@throws` in Javadoc tells callers **when** an exception is thrown. In the documentation for `load(String documentId) throws IOException`, you can state: `@throws IOException if the data source cannot be read` and `@throws IllegalArgumentException if documentId is empty`. This is illustrative Javadoc content, not a new method declaration.

You can also document **unchecked exceptions** with `@throws` even though they do not need to be declared in the signature. Avoid vague descriptions like "if an error occurs"; write specific conditions, and keep Javadoc updated alongside contract tests. Rules for doc generation, inline tags, overriding, and multiple failure branches are covered in full in the lesson on **documenting with `@throws`**.

## 15. `throws` in Constructors, Resources, and I/O APIs

The "be specific" rule also applies to constructors and resource cleanup.

```java
public FileStore(Path root) throws IOException {
    // Read or create data on the file system.
}
```

If a constructor can throw checked `IOException`, callers must handle or declare it. There is no reason to declare `throws Exception` when I/O is the only real checked failure category.

When using `try-with-resources`, both the `try` body and the resource's `close()` method can throw checked exceptions. If the resource type declares `close() throws IOException`, the wrapping API can use `throws IOException`; however, if the resource is declared as the general `AutoCloseable` with `close() throws Exception`, the compiler may have to account for `Exception` at the close point. **The static type of the resource** and its `close` API affect the contract.

### 15.1. Java 17 — Demo 7: `Closeable` for Specific Checked `IOException`

Create **`CloseableSpecificThrowsDemo.java`**:

```java
import java.io.Closeable;
import java.io.IOException;

public class CloseableSpecificThrowsDemo {
    static final class Resource implements Closeable {
        String read() throws IOException {
            return "ok";
        }

        @Override
        public void close() throws IOException {
            System.out.println("closing");
        }
    }

    static String load() throws IOException {
        try (Resource resource = new Resource()) {
            return resource.read();
        }
    }

    public static void main(String[] args) {
        try {
            String result = load();
            System.out.println("result: " + result);
        } catch (IOException e) {
            System.out.println("IO: " + e.getMessage());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 CloseableSpecificThrowsDemo.java
java CloseableSpecificThrowsDemo
```

Stdout:

```text
closing
result: ok
```

Why is `load() throws IOException` sufficient?

- Both `Resource.read` and `Closeable.close` declare `throws IOException`.
- `try-with-resources` guarantees `close` is called when leaving `try` along the applicable execution paths.
- There is no need for `throws Exception` when all checked failure sources in the example are I/O.
- If both `read` and `close` throw errors, Java has a primary/suppressed exception mechanism; they do not automatically turn into a broad `Exception` just because multiple `Throwable`s occurred.
- `try-with-resources` does not guarantee that the read operation succeeded or that side effects are rolled back; it manages closing the resource.

### 15.2. Why Declaring a Resource as `AutoCloseable` Can Broaden `throws`

`AutoCloseable.close()` declares `throws Exception`. If code only sees the `AutoCloseable` type and does not catch/translate errors on close, it must account for checked `Exception` from `close`.

The solution is not arbitrary casting, but choosing a resource interface with an appropriately narrow contract (`Closeable` for I/O) or handling/translating errors at a meaningful boundary.

## 16. Exception Chaining: Preserve `cause` When Choosing a Specific Exception

Translating `SQLException` into `CatalogUnavailableException` is only useful if the root cause is not lost.

Do:

```java
throw new CatalogUnavailableException(
        "Không tải được catalog", sqlException);
```

Do not:

```java
throw new CatalogUnavailableException(
        sqlException.getMessage(), null);
```

These snippets assume an appropriate constructor and a `sqlException` variable. The second approach drops the cause, making it hard to inspect the original stack trace, vendor code/SQL state, and failure chain.

**Message and cause serve different purposes:**

- Message: describes the failure for readers at the current layer.
- Cause: links to the underlying layer's failure.
- Custom typed context: safe IDs/codes, if callers need structured handling.
- Suppressed: secondary errors retained in the same situation, especially when closing a resource fails.

Do not manually copy the entire stack trace or create a separate `originalException` field duplicating `getCause()` unless there is a specific need.

## 17. When Should You Wrap Checked into Unchecked?

A library callback such as `Function.apply` does not declare checked exceptions. Sometimes you need to wrap `IOException` into `UncheckedIOException` while preserving the cause:

```java
Function<Path, String> read = path -> {
    try {
        return Files.readString(path);
    } catch (IOException e) {
        throw new UncheckedIOException("Không đọc được", e);
    }
};
```

This is a **snippet** requiring `Function`/`Path`/`Files`/`IOException`/`UncheckedIOException` imports. It changes **how the error is reported** across the callback API, without turning an I/O failure into success.

However, do not treat this as general advice to strip checked `throws` from every API. If you control the declared method, an explicit `throws IOException` may be more appropriate than forcing errors through an unchecked wrapper.

### 17.1. `InterruptedException` Needs Its Own Policy

If code catches `InterruptedException` and translates it, you must consider preserving the interruption signal: either propagate `InterruptedException` when the API allows, or restore the interrupt flag via `Thread.currentThread().interrupt()` before throwing another exception, depending on the contract.

Do not simply `catch(Exception ignored)` around a blocking operation and swallow the interruption. This is a strong example of how `throws Exception` lumps together different failures with distinct policies without clarity.

## 18. Is `throws Exception` Always a Design Flaw?

**No.** It can be reasonable at certain **general boundaries**:

- `public static void main(String[] args) throws Exception` in **small demonstration programs**, where the goal is simply to learn another API and letting the program terminate on error is acceptable.
- Test harnesses or internal runners, where callbacks are defined to allow arbitrary checked exceptions.
- `java.util.concurrent.Callable<V>.call() throws Exception`: a standard API with a deliberately general contract allowing tasks to report checked failures.
- Framework/plugin abstractions running code supplied by another application, where the set of checked types is unknown in advance and the caller is designed as a generic dispatcher.
- A specific boundary that needs to propagate all checked exceptions without being able to promise a more specific abstraction (requires clear documentation and scope limits).

Still, consider whether `throws Exception` causes inconvenience for a **long-lived public API**. Do not use it at every layer just because it is easy to write.

### 18.1. Is `main throws Exception` Different from a Library API?

Yes, in purpose. `main` is the entry point invoked by the JVM; for a small demo, declaring `throws Exception` is sometimes acceptable because no other Java caller has to implement a policy. A **public library** method `load() throws Exception` may be used by hundreds of callers for years; an overly broad contract becomes a maintenance cost.

In Java learning materials, examples with specific handlers are preferred to demonstrate behavior, though `main throws Exception` need not be strictly "forbidden".

### 18.2. `Callable.call() throws Exception` Is Intentional

`Callable<V>` allows many kinds of checked failures because a task framework can run arbitrary logic. However, when submitting a task to an `ExecutorService` and calling `Future.get()`, the caller sees **`ExecutionException`** (whose cause is the task's error) per the `Future` API, not necessarily the task's checked exception directly. Each layer still needs its own contract.

**Takeaway:** "specific" is relative to the abstraction layer and the caller's role; it does not mean every generic API must know every task failure type in advance.

## 19. Generic `throws E`: Preserving Specificity for Callbacks You Control

When designing an API that accepts a lambda that can throw a checked exception, instead of forcing callers into `throws Exception` everywhere, you can use a type parameter.

```java
@FunctionalInterface
interface CheckedSupplier<T, E extends Exception> {
    T get() throws E;
}

static <T, E extends Exception> T execute(
        CheckedSupplier<T, E> action) throws E {
    return action.get();
}
```

These are illustrative declarations, not a standalone program. With a callback that throws checked `IOException`, `E` can be `IOException`, so the method calling `execute` does not have to declare broad `Exception` just because the API is generic.

### 19.1. Java 17 — Demo 8: Propagating a Checked Type via Generics

Create **`GenericSpecificThrowsDemo.java`**:

```java
import java.io.IOException;

public class GenericSpecificThrowsDemo {
    @FunctionalInterface
    interface CheckedSupplier<T, E extends Exception> {
        T get() throws E;
    }

    static <T, E extends Exception> T execute(
            CheckedSupplier<T, E> action) throws E {
        return action.get();
    }

    public static void main(String[] args) {
        try {
            String ok =
                    GenericSpecificThrowsDemo
                        .<String, IOException>execute(() -> "done");
            System.out.println("Value: " + ok);

            GenericSpecificThrowsDemo
                .<String, IOException>execute(() -> {
                    throw new IOException("lost");
                });
        } catch (IOException e) {
            System.out.println("I/O: " + e.getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 GenericSpecificThrowsDemo.java
java GenericSpecificThrowsDemo
```

Stdout:

```text
Value: done
I/O: lost
```

Explanation:

- `CheckedSupplier.get()` declares checked `E`.
- `execute()` declares `throws E` instead of hard-coding `throws Exception`.
- At the call site, the example explicitly specifies `E = IOException` to avoid relying on type inference details while learning.
- The lambda can throw `IOException` because the target functional interface **permits** that checked exception.
- Standard `Supplier<T>` in `java.util.function` does **not** have `throws E`; it cannot be automatically replaced by a custom `CheckedSupplier` in an API that already takes `Supplier`.
- A generic `E` represents a single exception type, not a general union of unrelated checked types.

## 20. Multiple Checked Exceptions and Framework APIs

A framework accepting plugin code might use an interface:

```java
interface PluginAction {
    void execute() throws Exception;
}
```

This can make sense because a plugin might perform I/O, SQL, parsing, and many other things the framework cannot know in advance. However, at the **plugin invocation boundary**, the framework should:

- Define a failure policy: log, mark the task failed, clean up.
- Not treat every `Exception` as transient or retryable.
- Distinguish plugin failures from environment/permission violations when needed.
- Not catch `Error` and return success.
- Preserve the cause when translating errors into `PluginExecutionException` or a structured result.
- Not pass internal stack traces directly to end users.
- If plugins share a clear domain contract, consider a checked `PluginException` narrower than `Exception`.

**A dedicated exception named `PluginException` can also be too broad** if it bundles together all failures that callers need to distinguish. Choose an exception taxonomy based on real use cases, not the maximum number of layers.

## 21. If Failure Is an Expected Business Outcome, Consider a Result Type

Not every invalid input in a validation flow needs `throws`. If callers want to receive multiple errors at once, a typed result with error codes may be appropriate:

~~~java
record FieldIssue(String field, String code) {}
record ValidationResult(java.util.List<FieldIssue> issues) {}
~~~

These are illustrative records (Java 17), not a full program. **Specific exceptions** remain right when an operation fails abnormally, such as being unable to read an I/O source; `Optional<T>` is better when **having no result** is normal and the reason is not needed. The lesson "Choosing Exceptions, Optional, or Structured Result Types" compares and tests these three options in detail.

## 22. Avoid Creating Overly Deep Custom Hierarchies

Specificity does not mean dozens of classes:

```text
Exception
└── ApplicationException
    └── ServiceException
        └── DataException
            └── RepositoryException
                └── CatalogException
                    └── CatalogTimeoutException
```

An illustrative tree like the one above can carry costs:

- Callers must understand many types that have no genuinely different handling policies.
- Application layers must translate through many wrappers, creating long stack/cause chains.
- An overly deep hierarchy ties the API to the current package/layer organization.
- If multiple types only differ in message, a single class with typed error codes may suffice.
- If there are too few types, callers cannot distinguish meaningful failures.

A moderate design usually classifies by **recoverability or handling responsibility**:

```text
CatalogException (checked)
├── CatalogNotFoundException
└── CatalogUnavailableException
```

This is an example taxonomy, not a requirement that every application define the exact same one. If `NotFound` is a normal outcome, you can return `Optional<Catalog>` or a result type instead of an exception.

## 23. Specific Exceptions and Typed Context Data

A clear exception type can include typed getters:

```java
final class ResourceNotFoundException extends Exception {
    private final String resourceId;

    ResourceNotFoundException(String resourceId) {
        super("Không tìm thấy tài nguyên");
        this.resourceId = java.util.Objects.requireNonNull(
                resourceId, "resourceId");
    }

    String resourceId() {
        return resourceId;
    }
}
```

This is an illustrative class with no `main`. Callers can know **the failure type** and **which ID is involved** without parsing `getMessage()`.

When designing:

- Keep only the context needed for the handling/diagnostic contract.
- Do not store passwords/tokens/raw request bodies in exceptions.
- Do not copy the cause into a separate field if `Throwable.getCause()` already suffices.
- Do not duplicate `errorCode` and subtypes in ways that can conflict; if both serve the API/telemetry, keep them synchronized by design.
- Keep context stable and avoid large mutable object graphs.

**Error messages are for humans; exception types and typed getters are for machine logic.**

## 24. When Checked Exceptions Are Wrapped by Another Library API

An API may accept a callback without declaring checked exceptions, such as `Function.apply`/`Supplier.get`. In that case, you **cannot simply add `throws IOException` to the lambda** if the target functional method has no `throws`.

Options:

1. Handle the checked exception inside the lambda when a meaningful fallback exists.
2. Wrap into an unchecked exception with a cause, such as `UncheckedIOException`.
3. Design your own functional interface with `throws E` if you control the API accepting the callback.
4. Use a regular loop or method to preserve the checked contract directly.

When a framework API wraps errors via `InvocationTargetException`, `ExecutionException`, or `CompletionException`, callers must follow **the calling layer's contract** and inspect the root cause through the corresponding mechanism. No `throws IOException` on a deeply nested method automatically appears at every layer.

**This reinforces the principle:** choose an exception type that is specific enough, yet **at the right abstraction boundary** that the caller is using.

## 25. Design Retry Policies Based on Semantics, Not Just Type Names

An `IOException` can originate from:

- file does not exist (retrying the exact same operation is usually pointless);
- permission denied (requires permissions or configuration);
- temporary connection loss (may be retried with limits);
- mid-write failure (requires checking how much data was already written).

Therefore, even if an API has a specific `throws IOException`, callers **are not automatically entitled to retry every `IOException`**. The domain layer may need specific information such as error code, operation kind, timeout category, and idempotency.

Conversely, `throws Exception` makes retry policies hard to get right because too many unrelated failure types can pass through one generic handler.

### 25.1. Policy Decision Examples

| Situation | Handling direction choice |
| --- | --- |
| Missing input file | Request a valid path or choose a file |
| Existing file has format errors | Report invalid values/fields; do not auto-retry |
| Unstable connection | Bounded retry with backoff if the operation allows it |
| Partially written then disconnected | Verify state, idempotency, or compensate before retrying |
| Input violates contract | Fix caller/input; do not auto-retry with the same arguments |
| Fixed dependency missing configuration | Alert/fix configuration; do not retry indefinitely |

**An API with clear failure types facilitates recovery**, but you still need policies beyond the `throws` signature.

## 26. Common Design Mistakes

| Mistake | Why it is dangerous | How to fix |
| --- | --- | --- |
| Every method has `throws Exception` | Contract is too broad; callers must handle generically | Choose specific checked types or domain exceptions |
| `catch(Exception) { return null; }` | Hides errors, confuses null with success | Report failure per contract or provide a real fallback |
| `catch(Exception) { retry(); }` | Retries unrecoverable input errors and bugs | Retry with classification and limits |
| Public domain API exposes `SQLException` unnecessarily | Couples callers to JDBC internals | Translate at the repository layer, preserving cause |
| Wrapping `IOException` in `new Exception(message)` | Loses meaningful error type and possibly cause | Choose a subtype/domain checked exception with cause |
| Creating a new exception class for every message | Taxonomy bloats while caller handling does not differ | Group by handling strategy; use typed codes where appropriate |
| Choosing an overly narrow checked subclass for "precision" | Hard to evolve when the API gains related errors | Choose a superclass at the right abstraction level |
| Forgetting `throws` from resource `close()` | Compile error or missing handling | Use `Closeable`/a clear cleanup contract |
| Using `throws Exception` just to handle a `Function` callback | Does not change `Function.apply` | Catch inside the lambda or use a typed callback |
| Overriding implementation uses `throws Exception` when interface has `throws IOException` | Violates checked overriding rules | Keep the same type/subtype or fewer checked exceptions |
| Changing API to add a checked exception without updating callers | Source compatibility can break | Manage changes with versioning/changelog |
| Assuming removing `throws` has no source impact | Old checked catches may become unreachable | Check caller recompilation |
| Logging only `e.getMessage()` when translating errors | Loses stack/cause | Keep `Throwable` as cause, log with the proper API |
| Casting every `getCause()` to an infrastructure type | Implementation changes break the cast | Use `instanceof` or avoid internal dependencies |
| Using generic `RuntimeException` for every failure | Hard for callers to classify; may lose semantics | Choose meaningful unchecked subtypes when needed |
| Catching `Throwable` instead of `catch(Exception)` | Catches severe `Error`s as well | Consider only at special boundaries |
| Throwing `Error` for validation failures | Wrong hierarchy and meaning | Use `IllegalArgumentException`/an appropriate result |
| Not documenting unchecked errors | Callers do not know preconditions | Javadoc `@throws` and validation |
| Testing by branching on error messages | Text changes easily | Test type/code/context/cause |
| Storing tokens/passwords in exceptions | Logs may leak secrets | Minimal context, safe messages |

## 27. Process for Choosing a `throws` Clause for a New API

When designing a method:

1. **Write the method's purpose** in one sentence at the API user's level.
2. **List the failure paths** visible in the contract, not just every exception from the current implementation.
3. **Classify expected failures**: bad input, not found, I/O, parsing, temporary resource issue, invalid state, internal error.
4. **Identify what each caller can do**: fall back, fix input, retry, roll back, report an error, or terminate.
5. **Choose checked vs unchecked vs result** based on operation semantics, not compiler convenience.
6. **Choose a sufficiently narrow and stable type**: an appropriate JDK group or a necessary custom domain exception.
7. **Translate low-level exceptions at the boundary** if implementation details should not leak into the public API; always preserve the cause.
8. **Write `throws` and Javadoc `@throws`** describing causes/contracts, including notable unchecked conditions.
9. **Check interface overrides and callback APIs**: implementations must not widen checked throws; lambdas are bound by the target functional type.
10. **Write tests** verifying exception type, cause, typed data, success path, and failure path.
11. **Review API compatibility** when planning a new release; checked throws affect callers at compile time.
12. **Do not add checked types "just in case"** because other errors might appear in the future. If the scope of change is foreseeable, choose a meaningful abstraction.

### 27.1. Three Self-Check Questions

- If users see `throws Exception`, do they know **the failure type and handling policy**?
- If I replace the infrastructure implementation, does the API signature have to change? If yes, it may be an abstraction leak.
- If called through an interface or callback, is my checked `throws` clause **truly contract-compatible**?

If the answers are not good, revisit the taxonomy or API boundary.

## 28. Testing Exception Contracts

A good test checks **the exception type and cause**, not just "any `Exception` is fine".

JUnit 5 example:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.io.IOException;
import org.junit.jupiter.api.Test;

class SpecificThrowsContractTest {
    @Test
    void reportsSpecificIOException() {
        IOException e = assertThrows(IOException.class,
                () -> SpecificFileContractDemo.read("offline"));
        assertEquals("Thiết bị không sẵn sàng", e.getMessage());
    }

    @Test
    void translatesButPreservesCause() {
        var error = assertThrows(
                ExceptionTranslationDemo.CatalogUnavailableException.class,
                ExceptionTranslationDemo::loadCatalog);
        assertInstanceOf(java.sql.SQLException.class,
                error.getCause());
    }

    @Test
    void separatesFormatFromIo() {
        assertThrows(
                TwoSpecificFailuresDemo.InvalidRecordException.class,
                () -> TwoSpecificFailuresDemo.load("oops"));
    }
}
```

This is **a JUnit Jupiter test file**, not runnable standalone with only `javac` from the JDK; it requires JUnit 5 and the demo classes in the same package (or adjusting visibility/package). `assertThrows` checks inheritance subtype relationships; for APIs with very strict contracts, you can use `assertThrowsExactly` from a suitable JUnit version.

**Test success outcomes too**, not only failures. For exception translation, verify that `getCause()` is the expected type/object, and that domain data is not reported as successful when the lower layer throws.

### 28.1. Source-Level API Compatibility Tests

For public libraries, you can maintain **compile-time contract tests**: simulated callers writing handlers for the checked types declared by the API. When changing a `throws` clause, check whether downstream modules recompile. A single runtime unit test does not catch every source-level change to a checked-exception contract.

## 29. Frequently Asked Questions

### 29.1. Is writing `throws Exception` "wrong Java"?

No. It is completely valid syntax. The issue is primarily **contract design**, especially for public/library APIs where callers need to handle failures accurately.

### 29.2. Is `throws IOException, SQLException` okay?

Yes, if the method genuinely declares two checked failures and they fit the abstraction/override contract. At a domain boundary, however, you may want to translate them into one or more appropriate domain exceptions to avoid exposing the infrastructure layer.

### 29.3. If there is only `IOException` now, can I declare `throws Exception` to make future upgrades easier?

Syntactically yes, but usually **you should not** without a contractual reason. It forces every caller to deal with a broad checked type from the start. Design a stable abstraction around real failure categories; manage API evolution when adding new failures.

### 29.4. Does declaring `throws IOException` prevent `NullPointerException`?

No. `NullPointerException` is unchecked and can still occur. `throws` mainly participates in compile-time rules for checked exceptions.

### 29.5. Why can `catch(Exception)` hide bugs?

Because `RuntimeException extends Exception`. If a handler catches broadly and retries/falls back without classifying, it can swallow `NullPointerException` or `IllegalStateException` that indicate programming/state bugs.

### 29.6. When do you need a custom exception?

When callers need a **domain-meaningful failure classification** that JDK contracts cannot express accurately, or when you want to avoid exposing infrastructure exceptions. Do not create a custom class just to wrap every `IOException` if a pure I/O API can use `IOException` directly.

### 29.7. Why not just use `RuntimeException` for everything?

While it reduces compile-time obligations, it can lose the failure contract that callers need to handle. Checked vs unchecked is an API design decision, not a rule that "modern Java always drops checked exceptions".

### 29.8. Does `throws Exception` include `Error`?

No. `Error` is a separate branch under `Throwable`. `throws Exception` is not a contract for all `Throwable`s; `catch(Exception)` also does not catch `Error`. `throws Throwable` is even broader and is rarely justified for application APIs.

### 29.9. If `throws IOException` is added to an interface method, must every implementation list it?

No. An implementation may declare fewer checked exceptions or none at all, but it may not widen beyond the contract. Callers through the interface are still checked by the compiler against the interface signature.

### 29.10. Should Javadoc describe unchecked exceptions?

You should document important contract-violation conditions via `@throws`, even though unchecked types are not required in the `throws` clause. Clear documentation helps callers know preconditions.

## 30. Practice Exercises

### Exercise 1 — Narrowing a File-Reading API

A method currently uses `String read(Path) throws Exception` but only calls `Files.readString`. Switch to `throws IOException` and update the caller. Why is `IOException` more appropriate than `Exception` while still covering the `FileNotFoundException` subtype?

### Exercise 2 — Two Unrelated Error Types

Write a method `importText(String) throws IOException, ParseException` simulating `"offline"` and `"bad-format"` inputs. Write a caller with two separate `catch` blocks, then switch to multi-catch when the handling policy is the same.

### Exercise 3 — Translating JDBC Errors

Simulate `SQLException` at the repository layer and translate it to `CatalogUnavailableException` at the domain layer. Test that `getCause()` is `SQLException`; do not let callers depend on `SQLState` as part of the business contract unless needed.

### Exercise 4 — Checked vs Unchecked

A method takes a percentage value and calls a configuration source that can throw `IOException`. Which type should handle `percent = -1`? How should `IOException` be declared? Explain why `throws Exception` is unnecessary.

### Exercise 5 — Interface Overriding

Given interface `Loader.load() throws IOException`, is an implementation with `throws FileNotFoundException` valid? What if the implementation is changed to `throws Exception`? Explain using subtype relationships.

### Exercise 6 — API v2 Change

Version 1 declares `throws ParseException`; version 2 adds `throws IOException`. Write a version 1 caller that fails to recompile without updating its handler. State the source compatibility impact.

### Exercise 7 — Broad Catch at a Boundary

In a CLI dispatcher, `catch(Exception)` may be used to log and return a failure exit code. Why should you not apply the same catch-and-return-`null` pattern in every repository/service? Is `Error` caught?

### Exercise 8 — Resource Close

Replace `Closeable` in `CloseableSpecificThrowsDemo` with the static type `AutoCloseable` and examine the checked obligation of `close() throws Exception`. Find a way to use an appropriate type/adapter to avoid unnecessary `throws Exception`.

### Exercise 9 — Generic Callback

Create `CheckedSupplier<T,E extends Exception>` accepting a lambda that throws `IOException`. Write `execute(...) throws E`; compare with `java.util.function.Supplier`, which does not declare checked throws.

### Exercise 10 — Is a Domain Failure a Normal Outcome?

A form has three invalid fields. Discuss why returning a `ValidationResult` with three issues can be clearer than throwing three exceptions. When does a custom checked exception still make sense?

### Exercise 11 — Contract Tests

Write JUnit tests verifying that `read("offline")` throws `IOException`, `load("oops")` throws the custom checked exception, and exception translation preserves `cause`. Do not just write `assertThrows(Exception.class, ...)` for every test.

### Exercise 12 — Library Upgrade

Suppose a public API currently has `throws Exception` and you want to narrow it to `throws IOException`. Try recompiling a caller that has `catch(SQLException)` followed by `catch(Exception)`; see which handler may become unreachable and need refactoring.

## 31. Pre-Release API Design Checklist

- [ ] Have I identified **the checked failures that truly belong to the contract**, not just unclassified exceptions from internal code?
- [ ] Can `throws Exception` be replaced by a specific JDK type such as `IOException`/`ParseException`?
- [ ] If a domain API should not expose JDBC/HTTP internals, do I have a meaningful domain exception?
- [ ] When translating errors, did I pass `cause` so the original stack trace is not lost?
- [ ] Can callers distinguish errors that have **different handling policies**?
- [ ] Have I distinguished checked exceptions, unchecked exceptions, and `Error`?
- [ ] Does the API list only necessary checked exceptions, without declaring overly broad types "just in case"?
- [ ] Is the chosen exception type stable enough if the implementation changes?
- [ ] Have I avoided creating an overly deep taxonomy or a meaningless, overly broad custom `ApplicationException`?
- [ ] Have I written Javadoc `@throws` for failure conditions and important preconditions?
- [ ] If the method overrides an interface, is `throws` compatible with the parent contract?
- [ ] If using standard functional interfaces, do I understand the checked-throws limitations of callbacks?
- [ ] If using `try-with-resources`, have checked exceptions from `close()` been accounted for?
- [ ] Have I avoided assuming every `IOException` is automatically retryable, every validation error must be thrown, or every bug is recoverable?
- [ ] Are there no low-level `catch(Exception)` blocks silently returning `null`/`false`/success?
- [ ] If a public API changes checked throws, have I reviewed source compatibility and migration?
- [ ] Have I tested failure types, meaningful messages, cause, success paths, and post-error state?
- [ ] Are exceptions and logs free of secrets or unnecessary raw request contents?
- [ ] Is there a boundary responsible for converting errors into safe API/CLI responses?
- [ ] Have I considered a result type if failure is a frequent expected outcome?

## 32. Summary

`throws Exception` is not a syntax error, but it is usually **too broad a contract** for a specific API. Use `throws IOException` for I/O operations, multiple explicit checked types when callers need to distinguish them, or a custom domain exception when you want to hide lower-layer details while still **preserving `cause`**. Do not list unchecked exceptions just to satisfy the compiler; instead, document preconditions. Checked `throws` affects callers, overrides, generic callbacks, and version upgrade compatibility, so choose types that are **sufficiently narrow, meaningful, and at the right level of abstraction**. `throws Exception` still has a place in general callbacks/frameworks and simple demos, but it should not be the default choice for every method.
