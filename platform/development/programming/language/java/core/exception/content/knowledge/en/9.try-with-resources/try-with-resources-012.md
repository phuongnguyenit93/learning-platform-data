# Resource Ownership and When Not to Auto-Close in Java

## 1. Lesson Objectives

`try-with-resources` lets Java automatically call `close()` when leaving a block of code. However, **being closeable** and **having the right to close** are two different things: just because an object implements `AutoCloseable` does not mean any method receiving a reference to it should automatically end that object's lifecycle.

A data-reading method passed an `InputStream` from the outside may only be **borrowing** the resource. Conversely, a method that opens a file itself to complete its work usually **owns the responsibility for closing** that file. In applications with frameworks, connection pools, transactions, or request lifecycles, closing a resource in too narrow a scope can prevent another component from using that resource, even if the code looks like a "textbook" `try-with-resources` pattern.

After this lesson, you will be able to:

- Distinguish between **owned**, **borrowed**, **transferred** (closing responsibility transferred), and **framework-managed** (lifecycle managed by another layer) resources.
- Decide whether to use `try-with-resources` based on the **ownership contract** and actual lifecycle, not merely on the `AutoCloseable` type.
- Recognize cases where closing a wrapper also closes the underlying stream/reader it wraps.
- Understand why Java 9+'s `try (resource)` still automatically closes an object even when the variable is declared outside.
- Design methods that accept `InputStream`, `Reader`, `Connection`, and factories that return resources so callers know who must close them.
- Avoid leaks, double-closes, returning an already-closed resource, or accidentally closing `System.in`/`System.out` or framework-owned resources.
- Handle cleanup when initializing multiple resources or when exceptions occur without breaking the caller's contract.

The standalone Java 17+ examples include compile/run commands and deterministic `stdout` output. Snippets that only illustrate signatures or depend on external APIs are explicitly noted.

## 2. What Does `try-with-resources` Guarantee — and What Does It Not?

A familiar Java construct:

```java
try (java.io.BufferedReader reader =
        java.nio.file.Files.newBufferedReader(path)) {
    System.out.println(reader.readLine());
}
```

This is a **code snippet** inside a method that has a `path` variable of type `Path` and handles/declares `IOException`. `reader` is a resource declared in the header. When the scope exits, Java calls `reader.close()`, even if the body terminates abruptly due to an exception or `return`.

The `try-with-resources` statement manages calling `close()` syntactically, but it **does not automatically know**:

1. Whether the resource is owned by this method or merely borrowed.
2. Whether the resource still needs to be used elsewhere afterward.
3. Whether `close()` closes a physical socket/file, returns a connection to a pool, flushes data, or performs another action.
4. Whether closing a wrapper also closes the underlying resource.
5. Whether a resource referenced in two places in the header is actually the same object.
6. Whether closing at this point aligns with the transaction/request/session lifecycle.

Key takeaway: **`try-with-resources` is an automatic closing mechanism; it is not an ownership-checking system.** Java does not have an "ownership type system" in the compiler that forces you to prove you own a resource before placing it in the header.

### `AutoCloseable` Does Not Mean "Always Close Immediately After One Method Finishes Using It"

`java.lang.AutoCloseable` declares the `close()` method. Some implementations of `close()` can have side effects and throw exceptions. `Closeable` is intended for many I/O resources and has its own contract. However, **the interface does not tell you who the owner is**; that comes from the API contract, architecture, and the object that creates/manages the resource.

Therefore, good practice is not "never use `try-with-resources` on parameters", but rather "use it when **that scope has received ownership and closing responsibility** according to the contract".

## 3. Four Common Ownership Models

| Model | Example | Who decides when to close? | Recommendation |
| --- | --- | --- | --- |
| **Owned** | Method opens a file itself, creates a reader/stream for internal use | The method itself or a component explicitly receiving ownership | Close in the appropriate scope, typically with `try-with-resources` |
| **Borrowed** | Parse method receives a `Reader` from the caller solely to read | Caller retains ownership | Parse method must **not** close the parameter, unless the contract states otherwise |
| **Ownership transfer** | Factory returns a newly opened `InputStream` and transfers responsibility to the caller | Caller upon successful receipt | API must clearly state that the caller must close; caller uses `try-with-resources` |
| **Framework-managed / pooled** | Connection/session/stream provided by a container, transaction manager, or pool | Per the framework/pool contract or the unit holding the lifecycle | Do not close just because `close()` can be called; follow the scope and return rules specified by the API |

**Important note about pools:** For many `Connection` objects obtained from a pool, `close()` means **returning the logical connection to the pool**, not necessarily closing the physical connection. If you are the one granted a connection by the pool with the responsibility to return it, `try-with-resources` may be completely appropriate. If a connection is *borrowed* from a caller/transaction manager managing it across a broader scope, closing it in a helper method can be premature.

### Ownership Should Be Determined by Contract, Not Guesswork

Answer these questions before adding `try (resource)`:

- **Who creates or receives the resource from a factory?** The creator usually bears initial responsibility, though ownership can be transferred.
- **Who is permitted to end its lifecycle?** It could be the caller, callee, transaction manager, container, or application shutdown.
- **After this call, does anything else still need the resource?**
- **What exactly does `close()` do?** Close only the wrapper, close the delegate too, flush output, return a connection to a pool, or roll back a transaction?
- **Could a double-close or leak happen on an error path?**
- **Does the API contract document closing responsibility and failure scenarios?**

Do not rely solely on the fact that "the object is no longer used in the current method." It may still be needed by the caller or other parts of the application.

## 4. When Should You Auto-Close?

### 4.1. Resources Created by the Method That Do Not Escape

Valid example:

```java
static String readFirstLine(java.nio.file.Path path)
        throws java.io.IOException {
    try (java.io.BufferedReader reader =
            java.nio.file.Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
```

This is a **method snippet**. The reader is created inside the method, and the returned data is a `String`, not the reader itself. The scope of the work and the resource lifecycle match: open, read, close, return value.

`try-with-resources` also calls `close()` if `readLine()` throws an exception; the close operation itself may throw its own exception, which is handled according to suppressed exception rules.

### 4.2. Caller Explicitly Receives Ownership

When a factory API returns an **open** resource and states that the caller is responsible for closing it, the caller should typically use:

```java
try (java.io.InputStream input = openOwnedStream()) {
    useInput(input);
}
```

This is an **illustrative snippet**, requiring `openOwnedStream()` and `useInput(...)` to be defined and checked exceptions handled appropriately. Ownership is **transferred** from the factory to the caller on a successful result; the caller is responsible for closing.

If a factory returns a resource that actually belongs to another object's lifecycle, that API must document it clearly; do not infer ownership solely from a name starting with `open...`.

### 4.3. Management Scope Matches Usage Scope

In a CLI tool reading a file once, the scope may fit neatly inside a single method. In a service performing multi-step database operations, the scope may be an entire transaction. In a server, the scope of a single request and the scope of the application are two different things. Choose the scope based on **the unit of work that requires the resource to remain alive**, not the fewest lines you can wrap in a `try`.

## 5. When Should You **Not** Auto-Close?

### 5.1. Functions That Only Borrow an `InputStream` or `Reader`

For example, a parser receives a `Reader` passed by the caller and only needs to read data. If the parser writes:

```java
static String parse(java.io.Reader source)
        throws java.io.IOException {
    try (source) {
        char[] buffer = new char[16];
        int count = source.read(buffer);
        return count < 0 ? "" : new String(buffer, 0, count);
    }
}
```

This is a **valid method snippet in Java 9+** if the `source` parameter is effectively final, but it can **violate the contract**: it closes the reader supplied by the caller.

If the contract says "caller retains ownership", keep the reader open:

```java
static String parseBorrowed(java.io.Reader source)
        throws java.io.IOException {
    char[] buffer = new char[16];
    int count = source.read(buffer);
    return count < 0 ? "" : new String(buffer, 0, count);
}
```

This is a method snippet using a borrowed reader; the caller remains responsible for closing it. Both methods can read and return a `String`; the difference lies in **the authority to end the lifecycle**.

**Do not close a borrowed resource even when processing fails** if the contract requires the caller to retain ownership. Propagate the exception out, letting the caller decide whether to retry, reset, continue, or close.

### 5.2. Process-Managed Standard Streams

Streams such as `System.in`, `System.out`, and `System.err` are typically used by many parts of an application. A helper should not arbitrarily do:

```java
try (java.io.InputStream input = System.in) {
    // ...
}
```

This is a valid but **risky** snippet: it closes `System.in` when exiting the block. Subsequent input steps may no longer be able to use this stream.

Similarly, closing a `Scanner` created over `System.in` usually closes the underlying stream as well, because `Scanner.close()` closes its source if the source implements `Closeable`. If an application explicitly determines that it is completely done reading stdin, the application-level owner may have an appropriate closing policy. However, a **short-lived helper** should not impose that policy on the entire process.

`System.out` and `System.err` should also not be closed prematurely by a helper; closing the wrapper/output can cause subsequent logging or printing steps to fail or stop working as expected.

### 5.3. Framework-, Container-, or Transaction-Owned Resources

Cases where you must check the framework contract:

- Request/response body streams managed by a web server/container.
- A `Connection` passed by the caller to participate in an active transaction.
- A session or entity manager managed by a transaction manager.
- A stream in a pipeline that an orchestrating layer needs to continue processing.
- Resources shared across multiple calls or living until component/service shutdown.

A business-logic method **does not automatically become the owner** of a resource just because it receives a reference. If a framework delegates closing responsibility to the application within a specific scope (such as an independent connection checkout), close it at the right time per the framework's documentation.

### 5.4. Resources That Are Returned or Stored for Later Use

A classic mistake:

```java
static java.io.BufferedReader openBroken(java.nio.file.Path path)
        throws java.io.IOException {
    try (java.io.BufferedReader reader =
            java.nio.file.Files.newBufferedReader(path)) {
        return reader; // Returns a reference to a reader that is about to be closed.
    }
}
```

This is a method snippet that **compiles but has a broken lifecycle**. During `return`, `try-with-resources` closes `reader` before the caller receives the value. The caller receives an already-closed object. Calling `readLine()` afterward may throw an `IOException` because the stream is no longer open.

The right approach when transferring ownership:

```java
static java.io.BufferedReader openOwned(java.nio.file.Path path)
        throws java.io.IOException {
    return java.nio.file.Files.newBufferedReader(path);
}
```

The caller is then responsible:

```java
try (java.io.BufferedReader reader = openOwned(path)) {
    System.out.println(reader.readLine());
}
```

The snippets above are **illustrative code**; `path` must be a valid variable and the caller must handle/declare `IOException`. Do not close a resource in a factory on the success path if the contract **transfers ownership** to the caller.

## 6. Runnable Program: Borrowed Resource vs. Owned Resource

Create the file **`BorrowedOwnedDemo.java`**:

```java
import java.io.IOException;
import java.io.StringReader;

public class BorrowedOwnedDemo {
    static class TrackedReader extends StringReader {
        private boolean closeCalled;

        TrackedReader(String text) {
            super(text);
        }

        @Override
        public void close() {
            closeCalled = true;
            super.close();
        }

        boolean closeCalled() {
            return closeCalled;
        }
    }

    static String readBorrowed(TrackedReader source)
            throws IOException {
        char[] chars = new char[16];
        int count = source.read(chars);
        return count < 0 ? "" : new String(chars, 0, count);
    }

    public static void main(String[] args) throws IOException {
        TrackedReader external = new TrackedReader("alpha");

        System.out.println("borrowed=" + readBorrowed(external));
        System.out.println("borrowed closed=" + external.closeCalled());

        TrackedReader owned = new TrackedReader("beta");
        try (owned) {
            System.out.println("owned=" + readBorrowed(owned));
        }
        System.out.println("owned closed=" + owned.closeCalled());

        external.close();
        System.out.println("external closed by owner="
                + external.closeCalled());
    }
}
```

Run with JDK 17+:

```bash
javac BorrowedOwnedDemo.java
java BorrowedOwnedDemo
```

`stdout`:

```text
borrowed=alpha
borrowed closed=false
owned=beta
owned closed=true
external closed by owner=true
```

Explanation:

1. `external` is created in `main` and passed to `readBorrowed`, which **does not** put the resource in a `try` header and does not call `close()`.
2. After reading, `external.closeCalled()` is still `false`; `main` retains control over its lifecycle.
3. `owned` is a resource that `main`'s scope actively manages with `try (owned)`. Java 9+ allows this syntax because the variable is effectively final.
4. When exiting the block, Java calls `owned.close()`, turning the tracking flag to `true`.
5. Finally, `main` closes `external` itself where ownership resides.

The `closeCalled` flag is a tracking mechanism **designed for this example**, not a general API built into every `Reader`. The example requires no files or network, so its output is deterministic.

## 7. Closing a Wrapper Can Also Close the Underlying Resource

Another source of bugs is **wrapper cascading close**. Resource wrapper classes commonly forward `close()` calls to their delegate.

Example:

```java
java.io.InputStream borrowedInput = getBorrowedInput();

try (java.io.BufferedReader reader = new java.io.BufferedReader(
        new java.io.InputStreamReader(borrowedInput))) {
    System.out.println(reader.readLine());
}
```

This is an **illustrative snippet**, requiring `getBorrowedInput()` to be defined and checked exceptions handled. Closing `BufferedReader` closes `InputStreamReader`, which in turn closes `borrowedInput`. **Just because `borrowedInput` does not appear in the header does not mean it will not be closed.**

This is an important reason to check a wrapper's `close()` contract: `BufferedReader`, `InputStreamReader`, `BufferedInputStream`, and many other wrappers typically take responsibility for closing their delegate.

### Runnable Example: `close()` Cascading Through Wrappers

Create the file **`WrapperCascadeDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class WrapperCascadeDemo {
    static class TrackedInput extends ByteArrayInputStream {
        private boolean closeCalled;

        TrackedInput(String text) {
            super(text.getBytes(StandardCharsets.UTF_8));
        }

        @Override
        public void close() {
            closeCalled = true;
            super.close();
        }

        boolean closeCalled() {
            return closeCalled;
        }
    }

    public static void main(String[] args) throws IOException {
        TrackedInput input = new TrackedInput("hello");

        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(input, StandardCharsets.UTF_8))) {
            System.out.println("read=" + reader.readLine());
        }

        System.out.println("underlying close called="
                + input.closeCalled());
    }
}
```

```bash
javac WrapperCascadeDemo.java
java WrapperCascadeDemo
```

`stdout`:

```text
read=hello
underlying close called=true
```

`ByteArrayInputStream`'s `close()` is overridden solely to record the call; normally this class's `close()` has no significant effect. Even so, the flag proves the call **was forwarded** through the wrapper layers. For files, sockets, or external resources, the close effect can actually release the underlying resource.

### When You Need a Wrapper While Keeping the Underlying Stream Open

If the contract requires keeping the delegate open, three approaches are typically appropriate:

- Avoid creating a wrapper that owns closing the delegate in a short scope; use APIs directly on the borrowed stream if sufficient.
- Adjust the API so **the caller creates, owns, and closes the wrapper**, while the helper only borrows the wrapper to read.
- When genuinely necessary, use a **leave-open/non-closing** wrapper with well-defined closing behavior, and verify its impact on buffering, flushing, stream state, errors, and resource closing. This is an intentional design choice, not a default trick.

You should not simply omit `close()` in all cases: some wrappers have output buffers that must be flushed/finished to ensure data integrity. Keeping the underlying stream open must be paired with a clear policy for finishing the wrapper and flushing data.

## 8. Runnable Program: Wrapper That Does Not Close Borrowed Input

Sometimes you must use a wrapper's API while letting the caller retain ownership of the underlying stream. One illustrative approach is creating an `InputStream` wrapper whose `close()` **does not close the delegate**.

Create the file **`LeaveOpenDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class LeaveOpenDemo {
    static class TrackedInput extends ByteArrayInputStream {
        private boolean closeCalled;

        TrackedInput(String text) {
            super(text.getBytes(StandardCharsets.UTF_8));
        }

        @Override
        public void close() {
            closeCalled = true;
            super.close();
        }

        boolean closeCalled() {
            return closeCalled;
        }
    }

    static class LeaveOpenInput extends FilterInputStream {
        LeaveOpenInput(InputStream source) {
            super(source);
        }

        @Override
        public void close() {
            // Intentionally do not close delegate: ownership stays with the caller.
        }
    }

    static String readBorrowed(InputStream source)
            throws IOException {
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                        new LeaveOpenInput(source),
                        StandardCharsets.UTF_8))) {
            return reader.readLine();
        }
    }

    public static void main(String[] args) throws IOException {
        TrackedInput external = new TrackedInput("line one\nline two");

        System.out.println("line=" + readBorrowed(external));
        System.out.println("closed by helper=" + external.closeCalled());
        external.close();
        System.out.println("closed by caller=" + external.closeCalled());
    }
}
```

```bash
javac LeaveOpenDemo.java
java LeaveOpenDemo
```

`stdout`:

```text
line=line one
closed by helper=false
closed by caller=true
```

This is an **intentional illustrative mechanism**, not a rule for every `AutoCloseable` wrapper. `BufferedReader.close()` is still called by `try-with-resources`, but the close operation reaching `LeaveOpenInput` is not forwarded down to `external`.

**Warning about buffering:** a wrapper may have read ahead more bytes than it returned. In this example, `BufferedReader.readLine()` may buffer `line two` as well before returning `line one`; closing the wrapper and continuing to read directly from `external` can cause logical data loss for the caller. Therefore, only use the leave-open pattern when the contract genuinely tolerates a discrepancy between **the underlying stream's state** and **the wrapper's buffer state**. For protocols that must preserve read position, agree on a wrapper owned by the caller and reuse it, rather than creating a temporary wrapper just to read a portion.

The example above only verifies **not calling `close()` on the underlying stream**; it does not guarantee that remaining data can always be read in the original manner.

## 9. Java 9+ `try (resource)` Still Closes Borrowed Objects If Misused

Since Java 9, you can write:

```java
static void process(java.io.Reader borrowed)
        throws java.io.IOException {
    try (borrowed) {
        // Read data.
    }
}
```

This is a syntactically **valid** method snippet because the `borrowed` parameter is not reassigned (effectively final) and `Reader` implements `Closeable`/`AutoCloseable`. However, upon leaving `try`, `close()` will be called on **the exact object the caller passed in**.

The final/effectively final requirement only determines **whether the variable is syntactically valid in the header**, not **ownership**.

Comparison:

| Code | Behavior | When is it right? |
| --- | --- | --- |
| `try (Reader r = openMyFile())` | Scope opens and closes the reader | When this scope owns the resource |
| `try (borrowedReader)` | Closes the reader supplied by the caller | Only when the caller transfers closing responsibility |
| `try (Reader alias = borrowedReader)` | Closes the same object via an alias | Does not protect a borrowed reader from being closed |
| `try (BufferedReader b = new BufferedReader(borrowedReader))` | Typically closes the borrowed reader too via wrapper | Only if you have the right to close the delegate as well |
| Not using TWR on a borrowed parameter | Does not auto-close the parameter | When the caller retains ownership and closes it itself |
| `try (Reader r = factoryTransfersOwnership())` | Caller receives and closes the resource | When the factory has transferred closing responsibility |

**Aliases do not create copies of a resource.** Declaring `Reader managed = borrowedReader` merely creates another reference; closing either alias still closes the same object, unless a wrapper explicitly defines different behavior.

## 10. Ownership with JDBC and Connection Pools

JDBC is a prime example where misunderstanding ownership has major consequences.

### 10.1. Methods Receiving `Connection` from Caller: Usually Do Not Close `Connection`

**Illustrative code snippet, without `main` or a real database**:

```java
static int countRows(java.sql.Connection connection)
        throws java.sql.SQLException {
    try (java.sql.PreparedStatement statement =
            connection.prepareStatement(
                    "SELECT COUNT(*) FROM inventory");
         java.sql.ResultSet rows = statement.executeQuery()) {
        rows.next();
        return rows.getInt(1);
    }
}
```

In this example, `connection` is a **borrowed resource** passed in by the caller. This method only manages the statement and result set it creates for the query; it **does not close the connection**. The caller/transaction manager can continue using the connection for multiple statements or decide to commit/roll back at a broader scope.

Closing `ResultSet` before `PreparedStatement` follows the reverse closing order in the header. In practice, JDBC also has rules where a statement closes its dependent result sets, so avoid relying on a fixed number of close calls; follow the driver/framework contract and do not assume every object is safe to close repeatedly in every way.

**Important point:** the rule "do not close the connection" here stems from the assumption that **the callee only borrows the connection**. If the method itself obtains the connection from a `DataSource`, is responsible for a unit of work, and does not transfer closing responsibility elsewhere, then `try (Connection connection = dataSource.getConnection())` may be the right choice to return the connection to the pool on time.

### 10.2. Do Not Confuse Closing a Connection with Ending a Transaction

`Connection.close()` and `commit()`/`rollback()` are different actions. Exiting a TWR scope must never be treated as the sole way to decide whether a transaction succeeds or fails. If auto-commit is off, there must be a commit/rollback policy decided by the layer owning the transaction, following the rules of the JDBC API, driver, and pool in use.

If a helper method closes a connection belonging to a caller's transaction, it can disrupt the transaction, return the connection to the pool prematurely, or cause subsequent operations to fail.

### 10.3. Pools Can Change the Meaning of `close()`

A connection proxy returned by a pool typically uses `close()` to **return the logical handle to the pool**, not necessarily to sever the physical TCP connection. Thus, it is incorrect to say "never close a pooled connection": if the application checks out a connection under a contract requiring its return after work, **it must be closed/returned at the right time**. What is wrong is closing a resource **you do not currently own** or closing it **too early**.

## 11. Returning Resources from Factories: Transferring Ownership Explicitly

An API that opens a file and returns an `InputStream` can specify: "Caller must close the returned stream." In that case, **do not** wrap the resource in TWR inside the factory itself if the success path is meant to return an open resource.

Create the program **`OwnershipTransferDemo.java`**:

```java
public class OwnershipTransferDemo {
    static class TrackedResource implements AutoCloseable {
        private final String name;

        TrackedResource(String name) {
            this.name = name;
        }

        void use() {
            System.out.println("use " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    // Contract: caller must close the returned object.
    static TrackedResource openOwned() {
        return new TrackedResource("report");
    }

    public static void main(String[] args) {
        try (TrackedResource resource = openOwned()) {
            resource.use();
        }
        System.out.println("done");
    }
}
```

```bash
javac OwnershipTransferDemo.java
java OwnershipTransferDemo
```

`stdout`:

```text
use report
close report
done
```

Flow:

1. `openOwned()` creates the resource and **transfers closing responsibility** to the caller upon successful return.
2. `main` declares the resource in the header and becomes the owner for this scope.
3. After `use()`, Java automatically calls `close()`, and then `main` prints `done`.

In real factories with multiple initialization steps that can fail, the factory must close any resources it has already opened but **not yet transferred ownership of** on an error path. Ownership only transfers successfully once a valid result is handed over.

### Factories Should Not Return an Already-Closing Resource

An easy mistake to make:

```java
static TrackedResource openBroken() {
    try (TrackedResource resource = new TrackedResource("report")) {
        return resource;
    }
}
```

This is a **method snippet** assuming the `TrackedResource` class from the example above. Before the caller receives the object, `try-with-resources` has already called `close()`. Returning the reference may still compile, but the "return an open resource" API contract is violated.

## 12. Creating Multiple Resources: Avoiding Leaks Before Entering TWR

When initializing resources outside the header:

```java
Resource first = openFirst();      // Succeeds.
Resource second = openSecond();    // May throw an exception.
try (first; second) {
    use(first, second);
}
```

This is an **illustrative snippet**, requiring `Resource` and the methods to be defined. If `openSecond()` throws an exception, the program **has not yet entered** the `try` statement; that TWR scope is not yet responsible for closing `first`. This can cause a leak.

A common way to avoid this bug:

```java
try (Resource first = openFirst();
     Resource second = openSecond()) {
    use(first, second);
}
```

This is also an illustrative snippet. When initializing the second resource in the header fails, the first resource—already created and managed—will be closed according to TWR semantics.

### When You Must Have a Resource Before the Header

Sometimes a resource is created by another layer and ownership is transferred before the call. Design the **protecting scope to start early enough** so that every error path after receiving ownership has cleanup. If the caller still owns it, **do not** try to fix a leak risk by silently taking over closing responsibility.

The best approach depends on the API: pass a factory/supplier so the scope can open the resource itself, use a lifecycle-managing object, or establish a clear ownership-transfer contract with `try-with-resources` at the caller.

## 13. Exceptions from `close()`: Ownership Also Involves Error Handling

If you have accepted closing responsibility, you are also responsible for **observing close failures** in accordance with the contract.

In TWR:

- If the `try` body succeeds but `close()` throws a checked exception, you must catch or declare that exception.
- If the `try` body throws an exception and `close()` also throws, the body's exception is normally kept as the primary exception; the exception from `close()` goes into `getSuppressed()`.
- If there are multiple resources, Java attempts to close them in reverse order and records close failures according to suppressed exception rules.
- Do not write a `finally` block that redundantly closes a resource already managed by TWR, unless the API has a very specific requirement.

### Runnable Program: Primary and Suppressed Exceptions

Create the file **`CloseFailureDemo.java`**:

```java
public class CloseFailureDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("close failed");
        }
    }

    public static void main(String[] args) {
        Resource resource = new Resource();

        try (resource) {
            throw new IllegalArgumentException("work failed");
        } catch (IllegalArgumentException failure) {
            System.out.println("primary=" + failure.getMessage());
            System.out.println("suppressed="
                    + failure.getSuppressed()[0].getMessage());
        }
    }
}
```

```bash
javac CloseFailureDemo.java
java CloseFailureDemo
```

`stdout`:

```text
primary=work failed
suppressed=close failed
```

This example uses a resource owned by `main`'s scope. If it were a resource owned by another caller, putting it into TWR would introduce an **extra risk**: not only closing too early, but also surfacing a close failure in a place that has no authority over the lifecycle.

### If `close()` Has Side Effects or Is Not Idempotent

`AutoCloseable` does not require every `close()` implementation to be completely idempotent; some have side effects and may throw if called again. Avoid creating two wrappers that both own the delegate, or placing the same resource into multiple overlapping TWR scopes without a specific contract.

Different APIs may have their own guarantees regarding multiple closes; check the implementation's documentation rather than applying a single assumption to every `AutoCloseable`.

## 14. Ownership in Newly Designed APIs

### 14.1. State Clearly Who Must Close in JavaDoc

For a method accepting a borrowed stream:

```java
/**
 * Reads data from a caller-owned stream.
 * This method does not close {@code source}.
 *
 * @param source an open stream managed by the caller
 * @throws java.io.IOException if the read operation fails
 */
static void decode(java.io.InputStream source)
        throws java.io.IOException {
    int first = source.read();
    System.out.println(first);
}
```

This is an **illustrative method snippet**. Its main purpose is to explicitly state **not closing the parameter**. The JavaDoc `@throws` explains the error type, while the description text must clearly state resource responsibility.

For a factory returning a resource:

```java
/**
 * Opens a new reader.
 * The caller receives ownership and must close the returned reader.
 */
static java.io.BufferedReader openDocument(java.nio.file.Path path)
        throws java.io.IOException {
    return java.nio.file.Files.newBufferedReader(path);
}
```

This is also a method snippet. On the success path, the reader is returned open; closing responsibility belongs to the caller.

### 14.2. Name APIs to Express Intent, but Do Not Rely on Names Alone

Names like `readBorrowed`, `openOwned`, `withReader`, or `executeInTransaction` can suggest a contract. However, names do not replace JavaDoc and framework lifecycle rules. When an API accepts a callback to use a resource and then closes it itself, it must ensure the callback does not store the resource for use after the scope ends.

### 14.3. Do Not Store a Borrowed Resource Beyond the Permitted Borrow Window

If a helper receives a borrowed resource and saves it to a field for asynchronous use after the caller exits its scope, the helper may access a resource already closed by the owner. This is wrong even if the helper **never calls `close()`**. Ownership governs not only "who closes" but also **how long it may be used**.

### 14.4. Thread-Safety Is a Separate Requirement

Borrowed/owned status does not by itself tell you whether a resource can be used concurrently from multiple threads. For a stream, JDBC connection, or session, follow the API's thread-safety contract. Do not use "the caller retains ownership" to infer that a resource can be shared freely across threads.

## 15. Decision Matrix

| Scenario | Should this method use `try-with-resources`? | Reason |
| --- | --- | --- |
| Calling `Files.newInputStream(path)` itself for a one-time read | **Yes** | The scope opens and owns the resource |
| Receiving an `InputStream` whose closing right is kept by the caller | **No** on that stream | The caller needs to continue managing it |
| Receiving a `Reader` and parsing part of the data without ownership transfer | **No** on the received reader | Closing could deprive the caller of the resource |
| Factory newly opens a stream and returns it to the caller | **No** on the successful return path | Ownership is transferred to the caller |
| Caller receives a new stream from a factory with a caller-closes contract | **Yes** | The caller is responsible for closing |
| Borrowing `System.in` for a temporary read | **No** inside a helper | Process-wide shared stream |
| Using a wrapper whose close cascades to a borrowed stream | **Only if you have the right to close the delegate** | Closing cascade does not depend on variable names |
| Caller directly checks out a connection from a pool under a return contract | **Usually yes**, at the appropriate unit-of-work scope | `close()` typically returns the handle to the pool |
| Method receives a connection belonging to the caller's transaction | **No** on that connection | The transaction owner controls the lifecycle |
| Creating internal statements and result sets on a borrowed connection | **Yes** on the statement/result set | Child resources are scoped to the query |
| API is handed a response stream by a container | **Per container contract** | The container may manage closing or have specific rules |
| Resource is already closed while the variable is still in scope | Do not keep using it unless the API explicitly allows it | Variable scope differs from open lifecycle |
| Multiple new resources that can fail sequentially during creation | **Prefer declaring them in the header from the start** | Ensures cleanup if a later resource fails to initialize |

The choices in this table are based on the **ownership assumptions stated in each row**. They cannot substitute for the specific documentation of the driver, pool, library, or framework you are using.

## 16. Common Pitfalls

**"Whenever you see `AutoCloseable`, you must call `close()` yourself right away."** No. The interface only indicates the closing mechanism; who has the right to close must come from the lifecycle contract.

**"`try-with-resources` automatically detects borrowed resources and skips closing them."** False. If a non-null resource is listed in the header, the mechanism will call `close()` per Java rules, regardless of who created the object.

**"Closing a wrapper leaves the delegate open because the delegate isn't in the header."** False for many wrappers: `close()` can cascade down to the underlying resource.

**"Creating an alias `try (Reader alias = borrowed)` is a way to keep the borrowed reader open."** False. The alias points to the same object; closing via the alias closes the borrowed reader itself.

**"A method returning a stream inside `try-with-resources` still returns an open stream."** Usually false: when exiting `try` to `return`, the resource is closed before the caller receives the result.

**"`System.in` is just a normal `InputStream`, so it's fine for a helper to close it."** False regarding shared lifecycle. Closing it can affect the entire process.

**"You must never call `close()` on a pooled connection."** False. When an application is given a connection by a pool under a return contract, `close()` may be the required operation to return the handle to the pool.

**"A JDBC connection's `close()` is the same as `commit()`."** False. Transaction management has its own semantics; you must use the appropriate APIs and framework contracts.

**"A borrowed `Reader` can be saved to a field and used later at any time."** False. The borrower must respect the borrow duration; the owner may close the resource when that duration ends.

**"Java 9's `try (resource)` won't close it because the variable was declared outside."** False. The Java 9 feature only makes the syntax shorter; the resource is still closed when exiting the scope.

**"Closing twice is always safe."** No. Some APIs allow repeated closes, while others have side effects or do not guarantee idempotency.

**"Not using TWR for a borrowed stream means you don't need to handle exceptions."** False. Checked exceptions from `read()` must still be caught or declared; the caller still needs cleanup in the owning scope.

**"After the parser finishes reading, the caller won't need the stream anymore."** False. The caller may read multiple parts, handle a multi-stage protocol, retry, or decide to close in a broader scope.

**"If a resource is opened before TWR and the next creation step fails, TWR will always clean it up."** False. If `try` has not been entered yet, the header is not managing that resource.

## 17. Self-Check

1. **A method receives a `Reader` to read from, and its JavaDoc states the caller owns it. Should it use `try (reader)`?** No; that would close the caller's resource.
2. **Since Java 9, is an effectively final method parameter syntactically allowed in `try (reader)`?** Yes, but you must check ownership before using it.
3. **A factory creates and returns an open `BufferedReader`; who closes it?** The caller, if the contract has transferred ownership.
4. **Can closing a `BufferedReader` wrapping an `InputStreamReader` close the underlying `InputStream`?** Yes, due to the wrapper/delegate close cascade.
5. **Can you use `try-with-resources` to auto-close a `PreparedStatement` while keeping a borrowed `Connection` open?** Yes, if the method owns the statement and the caller retains management of the connection.
6. **A pooled `Connection` is checked out for a unit of work and must be returned to the pool; should it be closed?** Per the pool contract: typically yes, call `close()` when done to return the handle.
7. **Should a helper receiving `System.in` create a `Scanner` and wrap it in `try (scanner)`?** Usually no, because closing the scanner can close `System.in`.
8. **If an error occurs while opening a second resource before entering `try (first; second)`, is `first` guaranteed to be closed?** No; the scope has not started yet.
9. **If a resource is still open and a helper only borrows it, is it valid for the helper to save it for use after the owner's scope ends?** No, if it exceeds the borrow window.
10. **If `close()` also throws when the TWR body has already thrown an error, where do you find the close error?** Usually in `getSuppressed()` on the primary exception.
11. **Does making a variable `final` establish resource ownership?** No. `final` restricts reassigning the variable; it does not determine who is allowed to close it.
12. **When should you use a leave-open wrapper?** Only when the contract requires keeping the delegate open and you have analyzed side effects, buffering, flushing, and subsequent read rules; do not use it by default.
13. **Does closing a wrapper and reusing the underlying stream afterward always preserve the exact read position?** No. The wrapper may have read ahead into a buffer.
14. **Where should you look for the exact source of closing responsibility?** JavaDoc/API contracts, framework/pool contracts, and the application's lifecycle management architecture.

## 18. Official References

- [Java Language Specification 17 — §14.20.3, try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): closing mechanism, error paths, and suppressed exceptions.
- [Java SE 17 API — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): `close()` contract and notes on idempotency.
- [Java SE 17 API — Closeable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html): I/O resource closing contract.
- [Java SE 17 API — BufferedReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html) and [InputStreamReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html): reader wrappers and closing behavior.
- [Java SE 17 API — Scanner](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Scanner.html): closing a scanner and its underlying input source.
- [Java SE 17 API — Connection](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html): JDBC connection lifecycle and transactions.
- [Java SE 17 API — Throwable.getSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getSuppressed()): reading suppressed exceptions from closing resources.
- [Java Language Specification 17 — §4.12.4 final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): final/effectively final variables used in resource access.

**Core principle:** `try-with-resources` is very useful when **the current scope has the right and obligation to close** the resource. Do not mechanically put resources that are merely **borrowed** or managed by another component into TWR. Clarify the owner, usage window, wrapper closing cascade, pool/framework semantics, and error paths when handing off resources; from there, place automatic closing at **the right lifecycle boundary**.
