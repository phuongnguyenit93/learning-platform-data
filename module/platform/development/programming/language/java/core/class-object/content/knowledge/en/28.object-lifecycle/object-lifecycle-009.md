# Closing Resources with AutoCloseable and try-with-resources in Java 17+

## 1. Why Do We Still Need to Close Resources When There Is a Garbage Collector?

Java manages heap memory through garbage collection (GC). When an object is no longer reachable, the JVM may reclaim that object's memory at an **unguaranteed** time. However, a Java object may **own resources outside the heap**, such as a file descriptor, socket, database connection, native handle, or file lock. Those resources typically need to end at the right point of a business operation, rather than waiting for GC.

The two mechanisms address two different responsibilities:

- **Garbage collection:** manages the reclaimability of memory for objects that are no longer accessed by the program.
- **`close()` and `try-with-resources`:** manage the lifecycle of a resource that must be closed, along a specific control-flow path of the program.

`AutoCloseable` is the interface that expresses the resource-closing operation. `try-with-resources`, abbreviated as TWR, is a `try` syntax that **automatically calls `close()`** on a successfully initialized resource when exiting the scope, even when the body throws an exception.

~~~java
try (java.io.BufferedReader reader =
             new java.io.BufferedReader(
                     new java.io.StringReader("Java"))) {
    System.out.println(reader.readLine());
}
~~~

This is a valid snippet if placed inside a method that declares or handles `IOException`. The reader is closed when the block finishes. Simply having the reader variable go out of scope does **not** mean GC has run; the guarantee here comes from TWR.

This lesson belongs to **Java core – class-object**, in the **Object Lifecycle** group, under the topic **Closing Resources with AutoCloseable and try-with-resources**. The standalone programs below use **Java 17+**, without preview enabled; each complete example has a file name, `javac`/`java` commands, and deterministic output. Snippets intended solely to describe syntax are marked separately.

## 2. Learning Objectives

Upon completing this lesson, you will be able to:

1. Distinguish object lifetime on the heap from **resource ownership/lifetime**.
2. Read and implement `AutoCloseable.close()` with the correct signature.
3. Use TWR with a single resource, multiple resources, and variables declared before `try`.
4. Explain **opening from left to right, closing from right to left**.
5. Predict closing behavior if the body throws, returns, or the second resource fails to initialize.
6. Distinguish between **primary exception** and **suppressed exceptions**.
7. Explain why `AutoCloseable` and `Closeable` are not completely synonymous.
8. Handle checked exceptions of `close()`.
9. Know how to avoid double-closing when a wrapper owns the underlying stream.
10. Use TWR with `BufferedReader`, file streams, `Files.lines`, and JDBC.
11. Avoid closing a resource that is merely borrowed from a caller/framework.
12. Design an idempotent `close()` when appropriate and consider use-after-close.
13. Know when to use `finally` instead of TWR.
14. Remember that `ExecutorService` and `Lock` in Java 17 are not directly AutoCloseable.
15. Test cleanup without relying on finalizers, Cleaner, or GC timing.

## 3. `AutoCloseable`: The Resource-Closing Contract

The Java 17 public API signature has the form:

~~~java
public interface AutoCloseable {
    void close() throws Exception;
}
~~~

This is a description of the interface built into the JDK, **not source code you need to create yourself**. The only important method is `close()`; it has return type `void`. The interface allows throwing checked `Exception`, but an implementation can declare a **narrower** exception, such as `IOException`, or declare no checked exception at all.

A custom implementing class:

~~~java
final class Lease implements AutoCloseable {
    @Override
    public void close() {
        System.out.println("released");
    }
}
~~~

This is a valid class declaration. Because `close()` does not declare a checked exception, code using `Lease` in TWR does not need to catch Exception solely for the close operation.

`AutoCloseable` does not allocate on its own, does not synchronize across multiple threads on its own, and does not make the close behavior safe if called twice on its own. Everything depends on the contract of the concrete resource type.

## 4. Basic Syntax and Scope

Descriptive pattern:

~~~text
try (ResourceType resource = expressionCreatingResource) {
    statementsUsingResource
}
~~~

This is an **illustrative pattern**, not runnable Java source. The resource expression needs to have a type that is a subtype of AutoCloseable; the resource variable declared in the header is **implicitly final** and is used in the try body.

When the body completes normally, TWR attempts to call close before the program proceeds. When the body completes abruptly, for example due to an exception or return, TWR still performs cleanup according to the JLS rules.

A major benefit compared to a hand-written `finally` is handling **suppressed exceptions** when multiple places throw errors at the same time.

## 5. Complete Program 1 — open, work, close

Create the file **`BasicAutoCloseDemo.java`**:

~~~java
final class DemoResource implements AutoCloseable {
    DemoResource() {
        System.out.println("opened");
    }

    void work() {
        System.out.println("working");
    }

    @Override
    public void close() {
        System.out.println("closed");
    }
}

public class BasicAutoCloseDemo {
    public static void main(String[] args) {
        try (DemoResource resource = new DemoResource()) {
            resource.work();
        }
        System.out.println("after try");
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 BasicAutoCloseDemo.java
java BasicAutoCloseDemo
~~~

**Stdout:**

~~~text
opened
working
closed
after try
~~~

`close()` runs **before** the statement after try. There is no `System.gc()`; this closing mechanism relies on control flow, not waiting for the object to disappear from the heap.

## 6. Body Throws an Exception: The Resource Is Still Closed

A developer who only calls `stream.close()` at the end of the happy path may miss closing a resource when reading/writing throws an exception partway through. TWR solves this common error path.

The rule is simple:
- The resource is created successfully.
- The body starts.
- The body may throw.
- Before the outer catch is run, Java attempts to close the resource.
- If close does not throw an additional exception, the exception from the body continues to the handler.

TWR guarantees **executing the close call** according to language rules; it does not guarantee that `close()` always completes successfully.

## 7. Complete Program 2 — Closing Before Catch

File **`FailureCleanupDemo.java`**:

~~~java
final class UnitOfWork implements AutoCloseable {
    void execute() {
        System.out.println("execute");
        throw new IllegalStateException("failed");
    }

    @Override
    public void close() {
        System.out.println("close");
    }
}

public class FailureCleanupDemo {
    public static void main(String[] args) {
        try (UnitOfWork unit = new UnitOfWork()) {
            unit.execute();
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
        System.out.println("end");
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 FailureCleanupDemo.java
java FailureCleanupDemo
~~~

**Stdout:**

~~~text
execute
close
caught=failed
end
~~~

First, the body prints `execute`; then it throws; resource close is called before catch. Even though the UnitOfWork object may not yet have been reclaimed by GC, its resource lifecycle has been explicitly ended.

## 8. Multiple Resources: Initialized Left-to-Right, Closed in Reverse

Given:

~~~java
try (A a = openA();
     B b = openB();
     C c = openC()) {
    use(a, b, c);
}
~~~

This is an **illustrative syntax** snippet; A/B/C and the methods need to be defined if you want to run it.

If all initializations succeed, Java opens/evaluates the resources from **A → B → C**, then closes **C → B → A**. This resembles a LIFO stack and usually makes sense for dependencies: an inner-layer resource can rely on an outer-layer one.

When C's close fails, Java still attempts to close B and A. Subsequent errors are handled according to the primary/suppressed exceptions rules.

## 9. Complete Program 3 — LIFO Closing Order

File **`MultiResourceDemo.java`**:

~~~java
final class NamedResource implements AutoCloseable {
    private final String name;

    NamedResource(String name) {
        this.name = name;
        System.out.println("open " + name);
    }

    @Override
    public void close() {
        System.out.println("close " + name);
    }
}

public class MultiResourceDemo {
    public static void main(String[] args) {
        try (NamedResource a = new NamedResource("A");
             NamedResource b = new NamedResource("B");
             NamedResource c = new NamedResource("C")) {
            System.out.println("body");
        }
        System.out.println("finished");
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 MultiResourceDemo.java
java MultiResourceDemo
~~~

**Stdout:**

~~~text
open A
open B
open C
body
close C
close B
close A
finished
~~~

This is a deterministic rule of TWR, unrelated to the order in which GC considers the three objects.

## 10. Second Resource Fails to Open: The First Resource Is Still Closed

If Java has already opened A but the call to open B fails, A must be closed even though the try body **has not run**. This is an especially important rule when acquiring multiple files/connections in a single operation.

If **B's constructor** throws after already creating a native resource internally, TWR cannot automatically know about that hidden resource to close it; the constructor/factory itself must ensure **exception safety during initialization**.

Some beginners think TWR only manages resources after entering the try body. In reality, a failure right in the header also performs cleanup for resources that have already been successfully initialized.

## 11. Complete Program 4 — Failure When Opening B

File **`OpenFailureDemo.java`**:

~~~java
final class Channel implements AutoCloseable {
    private final String name;

    Channel(String name, boolean fail) {
        System.out.println("opening " + name);
        if (fail) {
            throw new IllegalStateException("bad-" + name);
        }
        this.name = name;
    }

    @Override
    public void close() {
        System.out.println("closing " + name);
    }
}

public class OpenFailureDemo {
    public static void main(String[] args) {
        try (Channel a = new Channel("A", false);
             Channel b = new Channel("B", true)) {
            System.out.println("body");
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 OpenFailureDemo.java
java OpenFailureDemo
~~~

**Stdout:**

~~~text
opening A
opening B
closing A
caught=bad-B
~~~

B did not complete its constructor, so there is no completed B resource for TWR to close; A was opened and closed. The body did not run.

## 12. Checked Exceptions and `throws` on close

`AutoCloseable.close()` is declared with `throws Exception`, so if you hold a resource with the **static type `AutoCloseable`**, the enclosing method may need to declare `throws Exception` or catch it.

A concrete class overriding:

~~~java
@Override
public void close() {
    // cleanup without checked exception
}
~~~

does not force the caller to handle a checked exception from close through that class's static type. This explains why `main` in BasicAutoCloseDemo does not declare `throws Exception`.

For I/O, many classes implement `java.io.Closeable`, which has `close() throws IOException`. You should keep specific error types in APIs, rather than arbitrarily declaring `throws Exception` across the application.

## 13. Primary and Suppressed Exceptions: Failures in Two Places

Suppose the body throws IOException("body"), while the resource's `close()` also throws IOException("close"). If a manual `finally` is written carelessly, the close error can **mask the body error**.

TWR has a special mechanism:
- The exception from the body becomes the **primary exception**.
- Exceptions occurring during cleanup are attached to the primary as **suppressed**.
- The caller inspects the list via `Throwable.getSuppressed()`.
- With multiple resources, suppressed exceptions usually appear in the order in which closing fails (reverse of opening order).

If the body does **not** throw and close throws, the close error becomes primary.

## 14. Complete Program 5 — Two Suppressed Exceptions

File **`SuppressedDemo.java`**:

~~~java
import java.io.IOException;

final class BrokenClose implements AutoCloseable {
    private final String name;

    BrokenClose(String name) {
        this.name = name;
    }

    @Override
    public void close() throws IOException {
        System.out.println("close " + name);
        throw new IOException("close-" + name);
    }
}

public class SuppressedDemo {
    public static void main(String[] args) {
        try (BrokenClose a = new BrokenClose("A");
             BrokenClose b = new BrokenClose("B")) {
            throw new IOException("body");
        } catch (IOException ex) {
            System.out.println("primary=" + ex.getMessage());
            System.out.println("count=" + ex.getSuppressed().length);
            for (Throwable t : ex.getSuppressed()) {
                System.out.println("suppressed=" + t.getMessage());
            }
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 SuppressedDemo.java
java SuppressedDemo
~~~

**Stdout:**

~~~text
close B
close A
primary=body
count=2
suppressed=close-B
suppressed=close-A
~~~

B and A throw in `close()` in turn, but the body exception retains its primary status. In production logging, you should preserve both cause and suppressed data when debugging is needed.

## 15. Only close Fails: The Close Error Becomes Primary

TWR does not “swallow” a close error if the try body has no error. For example, closing a Writer may trigger a flush; if the underlying I/O encounters an error during closing, the caller must be notified according to the exception contract.

You should not equate “all `write()` calls have been invoked” with “data has been successfully finalized on the device.” Depending on the API, an error may appear only during close.

## 16. Complete Program 6 — Error Occurs Only at close

File **`CloseOnlyFailureDemo.java`**:

~~~java
import java.io.IOException;

final class WriterLike implements AutoCloseable {
    @Override
    public void close() throws IOException {
        System.out.println("close attempt");
        throw new IOException("flush failed");
    }
}

public class CloseOnlyFailureDemo {
    public static void main(String[] args) {
        try (WriterLike output = new WriterLike()) {
            System.out.println("body succeeded");
        } catch (IOException ex) {
            System.out.println("caught=" + ex.getMessage());
            System.out.println("suppressed count="
                    + ex.getSuppressed().length);
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 CloseOnlyFailureDemo.java
java CloseOnlyFailureDemo
~~~

**Stdout:**

~~~text
body succeeded
close attempt
caught=flush failed
suppressed count=0
~~~

Because the body completed normally, the close exception is primary. There is no second error to be suppressed.

## 17. Do return, break, and continue Skip close?

No. When returning in a TWR body, the return expression is evaluated, and Java performs resource cleanup before the caller receives the return value. When `break` or `continue` causes control to exit the managed region, close is also executed according to Java rules.

If close throws an exception, a return statement being prepared may not complete to the caller. This is an important consequence if a resource is closed when the method returns an assumed success result.

You should not place unexpected side effects in close that cause the caller to misunderstand the transaction state.

## 18. Complete Program 7 — close Before return

File **`ReturnCleanupDemo.java`**:

~~~java
final class Gate implements AutoCloseable {
    @Override
    public void close() {
        System.out.println("gate closed");
    }
}

public class ReturnCleanupDemo {
    static int answer() {
        try (Gate gate = new Gate()) {
            System.out.println("computing");
            return 42;
        }
    }

    public static void main(String[] args) {
        System.out.println("result=" + answer());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ReturnCleanupDemo.java
java ReturnCleanupDemo
~~~

**Stdout:**

~~~text
computing
gate closed
result=42
~~~

Even with a return in the body, close still takes place before the caller prints the result.

## 19. Resource Variables Declared in the Header Are Implicitly Final

The syntax:

~~~java
try (SomeResource resource = create()) {
    resource.use();
}
~~~

is a pattern that requires SomeResource/create to be defined. The `resource` reference in the header is **implicitly final**. You cannot assign `resource = other` inside the try body to switch the tracked object.

This differs from object mutability: the resource can still advance a file cursor, send bytes, write to a buffer, and transition from the OPEN state to CLOSED. Final here locks the **reference variable**; it does not make the resource an immutable object.

If you need to open a new resource, create a new TWR scope or register a second resource in the header, instead of trying to reassign the old resource variable.

## 20. Existing Resource Variables: A Java 9+ Feature, Available in Java 17

Since Java 9, you can write:

~~~java
SomeResource resource = create();
try (resource) {
    resource.use();
}
~~~

This snippet requires SomeResource/create. Condition: the local variable `resource` is **final or effectively final**. Effectively final means it is not reassigned according to compilation rules, even if the `final` keyword is not written.

Because the variable is declared outside, the reference may **still remain in scope after try**, while the resource is already closed. Therefore, do not continue calling operations that require an open resource just because you still have the variable to call.

If the variable is reassigned so that it loses its effectively final status, `try (resource)` is rejected at compile time.

## 21. Complete Program 8 — existing resource variable

File **`ExistingVariableDemo.java`**:

~~~java
final class Permit implements AutoCloseable {
    private boolean closed;

    void use() {
        if (closed) {
            throw new IllegalStateException("closed");
        }
        System.out.println("permit used");
    }

    boolean closed() {
        return closed;
    }

    @Override
    public void close() {
        closed = true;
        System.out.println("permit closed");
    }
}

public class ExistingVariableDemo {
    public static void main(String[] args) {
        Permit permit = new Permit();

        try (permit) {
            permit.use();
        }

        System.out.println("closed flag=" + permit.closed());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ExistingVariableDemo.java
java ExistingVariableDemo
~~~

**Stdout:**

~~~text
permit used
permit closed
closed flag=true
~~~

The resource reference still exists, but the object has transitioned to the CLOSED state. TWR handles **resource lifetime**; it does not necessarily make the object disappear from memory.

## 22. Null Resource: Java Does Not Call close on null

If the resource value is null, TWR skips calling close for that resource, without throwing NullPointerException solely because of cleanup.

Example:

~~~java
AutoCloseable resource = null;
try (resource) {
    System.out.println("body");
}
~~~

This snippet is valid in a method declaring `throws Exception` or handling the checked exception. Note that if the body itself calls `resource.close()`, an NPE can still occur as usual.

## 23. Complete Program 9 — null resource

File **`NullResourceDemo.java`**:

~~~java
public class NullResourceDemo {
    public static void main(String[] args) throws Exception {
        AutoCloseable resource = null;

        try (resource) {
            System.out.println("body");
        }

        System.out.println("done");
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 NullResourceDemo.java
java NullResourceDemo
~~~

**Stdout:**

~~~text
body
done
~~~

`main` declares `throws Exception` because the static type AutoCloseable has close() throws Exception. The runtime value null causes cleanup not to need to call close.

## 24. `Closeable` and `AutoCloseable`: What Is the Difference?

`java.io.Closeable` **extends AutoCloseable**, with the signature `void close() throws IOException`. It specifically serves I/O resources, rather than arbitrary types of resources.

| Characteristic | AutoCloseable | Closeable |
| --- | --- | --- |
| Package | `java.lang` | `java.io` |
| Interface method | `close() throws Exception` | `close() throws IOException` |
| Used in TWR | Yes | Yes |
| Checked close exception | Can be broad | Narrower, IOException |
| Calling close multiple times | No general idempotent guarantee | Closeable contract states calling close on an already closed stream has no further effect |
| Released on time by GC? | No | No |

A concrete class can override close without throws so callers do not have to catch a checked exception. When designing an API, you should declare meaningful exceptions, rather than unnecessarily elevating to Exception.

## 25. Complete Program 10 — `Closeable` I/O

File **`CloseableDemo.java`**:

~~~java
import java.io.Closeable;
import java.io.IOException;

final class Channel implements Closeable {
    void read() {
        System.out.println("read");
    }

    @Override
    public void close() throws IOException {
        System.out.println("closed");
    }
}

public class CloseableDemo {
    public static void main(String[] args) throws IOException {
        try (Channel channel = new Channel()) {
            channel.read();
        }
        System.out.println("finished");
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 CloseableDemo.java
java CloseableDemo
~~~

**Stdout:**

~~~text
read
closed
finished
~~~

The IOException signature of `close()` is allowed according to the Closeable interface. The example runs normally while still declaring IOException to properly handle the compile-time contract.

## 26. AutoCloseable Can Be a Lambda Target

Because AutoCloseable has a single abstract method `close()`, you can declare a lambda with static type AutoCloseable and register it in TWR. This form is suitable for some very small cleanup actions.

You should not use lambda cleanup to hide ownership or relationships among multiple complex resources. A named class is usually better when a state machine and diagnostics are needed.

## 27. Complete Program 11 — lambda cleanup

File **`LambdaCleanupDemo.java`**:

~~~java
public class LambdaCleanupDemo {
    public static void main(String[] args) throws Exception {
        AutoCloseable action =
                () -> System.out.println("cleanup action");

        try (action) {
            System.out.println("work");
        }

        System.out.println("end");
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 LambdaCleanupDemo.java
java LambdaCleanupDemo
~~~

**Stdout:**

~~~text
work
cleanup action
end
~~~

The lambda does not open a real file; it only simulates a cleanup operation. When try ends, Java calls `action.close()` and executes the lambda.

## 28. `BufferedReader`, `StringReader`, and Wrapper Ownership

If a `BufferedReader` wraps a `StringReader` or a file reader, closing the wrapper typically **closes the underlying reader** according to the wrapper's contract. Therefore, it is not necessary by default to register both in two separate resource declarations.

Common case:

~~~java
try (java.io.BufferedReader reader =
             new java.io.BufferedReader(
                     new java.io.StringReader("first\nsecond"))) {
    System.out.println(reader.readLine());
}
~~~

This snippet requires IOException handling. The inner reader uses existing string data and does not open an operating system file descriptor; however, TWR still demonstrates ownership and close.

With native or custom wrappers, check whether the API specifies that the **wrapper owns the underlying resource or merely borrows it**. Avoid double-closing if closing the wrapper already closes the underlying resource and the underlying resource does not guarantee idempotency.

## 29. Complete Program 12 — Two-Line Reader

File **`BufferedReaderDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public class BufferedReaderDemo {
    public static void main(String[] args) throws IOException {
        try (BufferedReader reader =
                     new BufferedReader(
                             new StringReader("alpha\nbeta\n"))) {
            System.out.println("one=" + reader.readLine());
            System.out.println("two=" + reader.readLine());
            System.out.println("end=" + (reader.readLine() == null));
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 BufferedReaderDemo.java
java BufferedReaderDemo
~~~

**Stdout:**

~~~text
one=alpha
two=beta
end=true
~~~

TWR closes BufferedReader at the end of the body; having read up to EOF is not necessarily a replacement for close.

## 30. Reading Real Files and Handling Temporary Files

`Files.newBufferedReader(path, charset)` creates a BufferedReader corresponding to the file path, which needs to be closed. TWR ensures that closing the reader is attempted when reading completes or when an exception occurs.

However, **closing the reader does not delete the file**. If the application creates a temporary file itself and wants to delete it after reading, that is an independent action that needs to be organized in `finally` or another cleanup policy. At the same time, I/O can fail due to the environment, permissions, or a full disk, so expected stdout should only describe the successful flow.

## 31. Complete Program 13 — Temporary File with UTF-8

File **`TemporaryFileDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class TemporaryFileDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("lesson-", ".txt");

        try {
            Files.writeString(
                    file, "Java\nseventeen\n",
                    StandardCharsets.UTF_8);

            try (BufferedReader reader =
                         Files.newBufferedReader(
                                 file, StandardCharsets.UTF_8)) {
                System.out.println(reader.readLine());
                System.out.println(reader.readLine());
            }

            System.out.println("reader scope ended");
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 TemporaryFileDemo.java
java TemporaryFileDemo
~~~

**Stdout when the system permits creating/reading/deleting temporary files:**

~~~text
Java
seventeen
reader scope ended
~~~

The temporary file name is not printed, so the output does not depend on a random path. TWR closes BufferedReader before `finally` deletes the file.

## 32. `Files.lines` Returns a `Stream` That Needs to Be Closed

Not every `Stream<T>` holds an external resource. However, `Files.lines(Path)` returns a file-backed stream; the API documentation requires closing that stream after use.

~~~java
try (java.util.stream.Stream<String> lines =
             java.nio.file.Files.lines(path)) {
    long count = lines.count();
}
~~~

This snippet requires a valid Path and IOException handling. The terminal operation `count()` **does not replace** the necessary close action of a file-backed stream.

A stream created from a regular `List.of(...).stream()` does not hold a file/socket, so closing that stream is not the same kind of resource ownership requirement.

## 33. Complete Program 14 — Files.lines

File **`FilesLinesDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class FilesLinesDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("lines-", ".txt");
        try {
            Files.writeString(file, "one\n\ntwo\n",
                    StandardCharsets.UTF_8);

            try (Stream<String> lines =
                         Files.lines(file, StandardCharsets.UTF_8)) {
                long nonBlank = lines
                        .filter(s -> !s.isBlank())
                        .count();
                System.out.println("nonblank=" + nonBlank);
            }
            System.out.println("stream closed");
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 FilesLinesDemo.java
java FilesLinesDemo
~~~

**Stdout in an environment where temporary files work normally:**

~~~text
nonblank=2
stream closed
~~~

The two lines with text are one and two; the blank line is not counted. The stream is closed before deleting the file.

## 34. JDBC: Connection, PreparedStatement, and ResultSet

A JDBC query can hold multiple resources with the relationship:

~~~text
Connection
    |
    +-- PreparedStatement
            |
            +-- ResultSet
~~~

Integration pattern:

~~~java
try (java.sql.Connection connection =
             dataSource.getConnection();
     java.sql.PreparedStatement statement =
             connection.prepareStatement(
                     "SELECT name FROM users WHERE id = ?")) {

    statement.setLong(1, userId);

    try (java.sql.ResultSet results =
                 statement.executeQuery()) {
        while (results.next()) {
            consume(results.getString("name"));
        }
    }
}
~~~

This is an **integration snippet**, not a standalone program: it requires `dataSource`, `userId`, `consume`, and a database/driver. ResultSet closes before statement/connection according to TWR nesting.

With a **connection pool**, `Connection.close()` may return the logical connection to the pool instead of closing the physical network connection. TWR should still be used when the caller is granted appropriate ownership.

## 35. TWR Does Not Automatically Commit or Roll Back Transactions

TWR only controls **attempting to close** resources. It does not promise to enforce any transaction policy:

- With a manual JDBC transaction, the caller usually has to set autoCommit as needed.
- On success, business logic decides `commit()`.
- On error, it needs `rollback()` if appropriate, while also handling any rollback errors.
- Finally, Connection is closed/returned to the pool according to ownership.
- With framework-managed transactions, let the framework manage the lifecycle and commit/rollback; do not close the connection yourself without authorization.

Do not assume that calling `close()` on a connection will automatically create a transaction commit according to business intent. The semantics when closing a connection with an incomplete transaction depend on the JDBC contract/driver/pool and should not be the foundation of critical business logic.

## 36. Avoid Accidentally Closing “Borrowed” Resources

A reference passed into a method **does not necessarily transfer ownership**.

~~~java
static void append(java.io.Writer writer)
        throws java.io.IOException {
    writer.write("hello");
}
~~~

This is a valid method snippet. The caller may want to keep writing after `append`, so the method should not close the writer itself unless the contract explicitly specifies so.

Error-prone cases:
- Wrapping `System.in` in a Scanner and then closing the Scanner mid-application, making standard input unusable.
- Manually closing a Connection managed by a transaction framework.
- Closing an HTTP response/stream before the caller finishes consuming all the data.
- Registering both a buffered wrapper and the underlying stream and double-closing.

**Ownership is more important than syntax:** only use TWR where you have the authority and responsibility to close.

## 37. Complete Program 15 — borrowed writer

File **`BorrowedWriterDemo.java`**:

~~~java
import java.io.IOException;
import java.io.StringWriter;
import java.io.Writer;

public class BorrowedWriterDemo {
    static void addGreeting(Writer writer) throws IOException {
        writer.write("Hello");
    }

    public static void main(String[] args) throws IOException {
        StringWriter writer = new StringWriter();

        addGreeting(writer);
        writer.write(" Java");

        System.out.println(writer.toString());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 BorrowedWriterDemo.java
java BorrowedWriterDemo
~~~

**Stdout:**

~~~text
Hello Java
~~~

The method only borrows the writer. `StringWriter` is an in-memory buffer and `close()` does not affect continued use according to its contract; the example teaches ownership, rather than proving that every Writer can be used after close.

## 38. Must `close()` Be Idempotent?

`AutoCloseable` does not guarantee that every concrete implementation can be safely closed multiple times. The API recommends idempotency if possible, but a native handle or transactional resource may have its own constraints.

A simple implementation can keep a `closed` flag:

~~~java
@Override
public void close() {
    if (!closed) {
        closed = true;
        release();
    }
}
~~~

This snippet requires an appropriate `closed` field and `release`. It is not inherently thread-safe. If two threads close concurrently, a boolean flag without synchronization can cause a double release.

You should clearly decide:
- Is a second close a no-op or does it throw an error?
- What exception does use-after-close report?
- If release fails, how is the state updated?
- Can close be called by another thread?
- If the resource has multiple subresources, what is the correct release order?

## 39. Complete Program 16 — Idempotent close by Design

File **`IdempotentDemo.java`**:

~~~java
final class SafeLease implements AutoCloseable {
    private boolean closed;

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            System.out.println("released");
        }
    }

    boolean isClosed() {
        return closed;
    }
}

public class IdempotentDemo {
    public static void main(String[] args) {
        SafeLease lease = new SafeLease();

        try (lease) {
            System.out.println("using");
        }

        lease.close();
        System.out.println("closed=" + lease.isClosed());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 IdempotentDemo.java
java IdempotentDemo
~~~

**Stdout:**

~~~text
using
released
closed=true
~~~

TWR calls close once; the additional call does not print `released` because the implementation itself is designed for idempotency. Do not infer that every AutoCloseable behaves the same way.

## 40. Custom AutoCloseable for a Lock Lease

In Java 17, `java.util.concurrent.locks.Lock` **does not extend AutoCloseable**, so a Lock cannot be placed directly in TWR. However, you can create a **LockLease** wrapper that holds ownership to lock/unlock with the scope.

This is a useful pattern, but care is needed: `ReentrantLock.unlock()` must be performed by the appropriate thread. If the resource can move to another thread, you need a different concurrent ownership design.

## 41. Complete Program 17 — Wrapper Managing ReentrantLock

File **`LockLeaseDemo.java`**:

~~~java
import java.util.concurrent.locks.ReentrantLock;

final class LockLease implements AutoCloseable {
    private final ReentrantLock lock;
    private boolean closed;

    LockLease(ReentrantLock lock) {
        this.lock = lock;
        lock.lock();
        System.out.println("acquired");
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            lock.unlock();
            System.out.println("released");
        }
    }
}

public class LockLeaseDemo {
    public static void main(String[] args) {
        ReentrantLock lock = new ReentrantLock();

        try (LockLease lease = new LockLease(lock)) {
            System.out.println("held=" + lock.isHeldByCurrentThread());
        }

        System.out.println("held after="
                + lock.isHeldByCurrentThread());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 LockLeaseDemo.java
java LockLeaseDemo
~~~

**Stdout:**

~~~text
acquired
held=true
released
held after=false
~~~

The program runs on a single thread with no contention; the output is stable. A lock lease in a real system needs a clear state and thread-affinity design.

## 42. When `finally` Is Needed Instead of TWR

Not every cleanup API implements AutoCloseable. With a plain Lock:

~~~java
lock.lock();
try {
    updateSharedState();
} finally {
    lock.unlock();
}
~~~

This snippet requires `lock` and `updateSharedState` to be defined. `finally` matches the Java 17 Lock contract.

If you own a resource that has AutoCloseable, TWR is usually less error-prone than a hand-written `finally`, because of:
- Not forgetting to close on return/throw paths.
- Closing multiple resources in the right order.
- Preserving primary/suppressed exceptions when close throws.
- Not having to manually write simple null-check logic.

However, TWR cannot replace a transaction protocol, protect against process crashes, or compensate for external side effects.

## 43. Complete Program 18 — Cleanup with finally

File **`FinallyDemo.java`**:

~~~java
public class FinallyDemo {
    static void runTask() {
        try {
            System.out.println("work");
            throw new IllegalStateException("failed");
        } finally {
            System.out.println("cleanup");
        }
    }

    public static void main(String[] args) {
        try {
            runTask();
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 FinallyDemo.java
java FinallyDemo
~~~

**Stdout:**

~~~text
work
cleanup
caught=failed
~~~

`finally` is executed by the language according to control flow; it is not a GC callback. If cleanup in finally also throws, manual code needs to be careful to avoid accidentally masking the original error.

## 44. Does `try-with-resources` Always Perform Cleanup Even When the JVM Stops?

No. The language mechanism applies when control exits the try scope along normal Java execution paths, including return and exceptions. However, a process can die without unwinding stack frames:

- `Runtime.halt(...)` forcibly terminates the VM.
- `System.exit(...)` causes the process to shut down and does not promise that all currently active try scopes will complete along the normal path.
- An OS kill, power failure, native crash, or JVM crash can prevent close code from running.
- A `close()` may block indefinitely or throw an error depending on its implementation.

Therefore, TWR is **not** a crash-durable transaction guarantee. When data requires all-or-nothing semantics or durability, you must add a transaction, flush policy, atomic file move, journal/recovery, or an appropriate protocol.

## 45. `Cleaner` and `finalize` Cannot Replace Timely close

Legacy finalization has no guaranteed execution time and is unsuitable for managing files/sockets in a timely manner. `Cleaner` can be useful as a **backup** for resource holders with native state, but automatic cleaning still depends on reachability, scheduling, and the JVM lifecycle.

With TWR, the caller can clearly define a **close attempt** milestone by scope. That is the difference between ownership-based resource cleanup and deadline-free GC-based cleanup.

If a class has both `close()` and a backup Cleaner, the Cleaner action should not hold a strong reference to the referent itself, because doing so can prevent automatic cleanup. When closing explicitly, you must also guard against double release.

**Do not write tests like “sleep 1 second and then the finalizer must print closed”.** Use a fake AutoCloseable and assert the indicators produced by close.

## 46. Use-after-close: The Reference Remains, but the Resource Is Closed

If the resource is declared **outside** try, the variable may still remain in scope afterward. However, the object's state may have transitioned from OPEN to CLOSED.

A good API should define what happens when a caller reads/writes after close: typically throwing `IllegalStateException` or `IOException`, depending on the contract. Do not call `getClass()` or check whether the reference is still non-null and conclude that the resource can still be used.

This helps distinguish **object lifetime on the heap** from **external handle lifetime**.

## 47. Complete Program 19 — Blocking Operations After close

File **`ClosedStateDemo.java`**:

~~~java
final class ManagedResource implements AutoCloseable {
    private boolean closed;

    void use() {
        if (closed) {
            throw new IllegalStateException("resource closed");
        }
        System.out.println("used");
    }

    @Override
    public void close() {
        closed = true;
        System.out.println("closed");
    }
}

public class ClosedStateDemo {
    public static void main(String[] args) {
        ManagedResource resource = new ManagedResource();

        try (resource) {
            resource.use();
        }

        try {
            resource.use();
        } catch (IllegalStateException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ClosedStateDemo.java
java ClosedStateDemo
~~~

**Stdout:**

~~~text
used
closed
rejected=resource closed
~~~

The object is still referenced by the `resource` variable when catch executes, but the use method is rejected because the lifecycle is closed.

## 48. Testing Resource Closing with an Event Log

A good test for TWR does not require real I/O or GC. You can create a FakeResource that implements AutoCloseable and record `open`, `use`, and `close` events. Check the sequence, close count, and order across multiple resources.

If testing suppressed exceptions, throw exceptions with fixed messages in body/close and then read `getSuppressed()`; there is no need to assume stack trace formats across JDKs.

Keep distinct:
- **TWR unit test:** does the language call close at the right time?
- **I/O integration test:** does the filesystem/socket/pool release according to the contract?
- **GC observation:** when does the JVM reclaim the object (non-deterministic, not a TWR correctness check)?

## 49. Complete Program 20 — Recording close Order

File **`CloseAuditDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

final class AuditedResource implements AutoCloseable {
    private final String name;
    private final List<String> events;

    AuditedResource(String name, List<String> events) {
        this.name = name;
        this.events = events;
        events.add("open-" + name);
    }

    void use() {
        events.add("use-" + name);
    }

    @Override
    public void close() {
        events.add("close-" + name);
    }
}

public class CloseAuditDemo {
    public static void main(String[] args) {
        List<String> events = new ArrayList<>();

        try (AuditedResource a = new AuditedResource("A", events);
             AuditedResource b = new AuditedResource("B", events)) {
            a.use();
            b.use();
        }

        System.out.println(events);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 CloseAuditDemo.java
java CloseAuditDemo
~~~

**Stdout:**

~~~text
[open-A, open-B, use-A, use-B, close-B, close-A]
~~~

The program verifies the exact resource close order, completely independent of memory GC or the file system.

## 50. Compilation Errors and Common Mistakes

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Using `try (new Object())` | Invalid resource syntax / not an AutoCloseable type | Declare/receive a resource that implements AutoCloseable |
| Resource is a class that does not implement AutoCloseable | TWR does not know how to close it | Implement the interface or use finally per the contract |
| Reassigning a resource header variable | Implicitly final | Declare a new resource in another scope |
| `try (existing)` where the variable is not effectively final | Java 9+ requires final/effectively final | Stop reassigning |
| Not catching/declaring checked exception from close | Violates checked exception analysis | Catch/declare the proper type |
| Assuming body catch runs before close | Cleanup happens before outer catch | Understand exception processing order |
| Closing both wrapper and raw stream twice | The wrapper may own the raw stream | Have only one owner; check the contract |
| Resource declared before try, yet a method still uses it after close | Object is already CLOSED | Do not use operations requiring open |
| Confusing TWR with automatically deleting temporary files | Close does not delete files | Use `Files.deleteIfExists` per cleanup policy |
| Using `try (System.in)` and still wanting to read afterward | Standard input ownership is violated | Do not close the shared stream yourself |
| Ignoring suppressed exceptions | Missing cleanup failure details | Inspect `getSuppressed()` |
| Using Java 17 ExecutorService in TWR | Java 17 ExecutorService does not extend AutoCloseable | Use shutdown APIs |
| Relying only on GC to close resources | GC timing is not guaranteed | Use TWR or explicit close |
| Using `try (resource)` as a guarantee of transaction commit | Close is not a transaction policy | Commit/roll back explicitly |

In particular, **Java 17 `ExecutorService` is not AutoCloseable**: syntax using `try (ExecutorService executor = Executors.newSingleThreadExecutor())` as a resource **does not compile on a Java 17 target**. APIs in newer JDK versions may differ; always check `--release 17` in projects requiring 17 compatibility.

## 51. When Is `try-with-resources` Not Needed?

Not every object needs to be closed:
- Immutable values such as String, Integer, BigDecimal, and most pure-data records.
- Regular in-memory collections such as ArrayList, HashMap.
- Plain streams from a Collection, if there is no special close handler/resource ownership.
- Objects that do not implement AutoCloseable and do not represent a resource lifecycle.
- Resources **borrowed** from a caller where the contract requires the callee not to close them.
- Framework-managed resources/transactions where the caller does not own the close boundary.

Conversely, an `AutoCloseable` object can be returned to the caller with a “caller must close” contract; the important thing is to transfer ownership responsibility clearly. If a method opens an InputStream and then **returns the stream for the caller to continue reading**, do not put that same InputStream into a TWR scope that ends before `return`: you would return an already closed stream.

## 52. Knowledge Check Exercises

**Question 1.** Why does GC not replace `close()` for a file descriptor?

**Question 2.** Which package is AutoCloseable in, and what method does it have?

**Question 3.** If a `close()` implementation does not declare a checked exception, does main have to declare `throws Exception` solely because of TWR?

**Question 4.** With three resources A, B, C in the header, what are the opening and closing orders?

**Question 5.** When the body throws, does Java attempt to close already opened resources?

**Question 6.** If B's constructor fails but A has already opened, is A closed?

**Question 7.** Does TWR know about every native resource partially allocated inside a failing constructor B to release it automatically?

**Question 8.** If both the body and close throw, which exception is primary?

**Question 9.** Which method reads suppressed exceptions?

**Question 10.** If the body succeeds and only close throws IOException, does the caller receive the exception?

**Question 11.** Does a return in the body skip close?

**Question 12.** Can a resource header variable be reassigned?

**Question 13.** Does Java 17 allow `try (resource)` with a previously declared variable?

**Question 14.** What property must a previously declared variable have to be used in `try (resource)`?

**Question 15.** When the resource value is null, does TWR automatically throw an NPE during cleanup?

**Question 16.** Does Closeable extend AutoCloseable, and how does it differ in checked exceptions?

**Question 17.** Why does a BufferedReader wrapper usually not need its underlying reader registered to be closed again?

**Question 18.** Does `Files.lines` require closing the resulting stream?

**Question 19.** When `Files.newBufferedReader` is closed, is the file on disk automatically deleted?

**Question 20.** Does TWR automatically commit or roll back a JDBC transaction according to business policy?

**Question 21.** Does a pooled Connection.close() always destroy the physical socket?

**Question 22.** Should a method that borrows a Writer close it on its own?

**Question 23.** Is AutoCloseable.close() always idempotent?

**Question 24.** If close is called from multiple threads, does an unsynchronized boolean flag guarantee an exactly-once release?

**Question 25.** Does Java 17 `Lock` extend AutoCloseable?

**Question 26.** Can Java 17 `ExecutorService` be used directly in TWR?

**Question 27.** Why should you not wait for a finalizer/Cleaner instead of timely close?

**Question 28.** Does TWR guarantee close runs if Runtime.halt terminates the JVM?

**Question 29.** Can a resource object that is still referenced after try still be CLOSED?

**Question 30.** State one way to unit-test cleanup without needing GC.

**Question 31.** If a method creates an InputStream and returns it to the caller, which side is responsible for closing?

**Question 32.** If a resource has a close error when the body already failed, what needs to be inspected to log everything completely?

### Answers with Explanations

1. GC has no deadline; native/file resources require explicit release according to ownership.
2. `java.lang.AutoCloseable`, method `void close() throws Exception`.
3. No, when the static concrete close signature does not declare a checked exception.
4. Open A→B→C; close C→B→A.
5. Yes, successfully initialized resources are attempted to be closed.
6. Yes.
7. No; B's constructor must protect against partial initialization itself.
8. The body error is primary, and the close error is suppressed.
9. `Throwable.getSuppressed()`.
10. Yes, the close exception is primary.
11. No, close happens before the caller receives the return value.
12. No, a resource header variable is implicitly final.
13. Yes, since Java 9.
14. Final or effectively final.
15. No; a null resource does not have close called on it automatically.
16. Yes; Closeable is narrower with IOException.
17. The wrapper usually closes the underlying reader itself; avoid double-closing outside ownership.
18. Yes; the file-backed stream must be closed.
19. No; deleting the file is a separate operation.
20. No; the transaction policy must be designed separately.
21. No, many pools return the logical connection to the pool.
22. No, unless the contract transfers ownership.
23. No; the implementation needs to choose its contract explicitly.
24. Not yet; a concurrency-safe close protocol is needed.
25. No.
26. No in Java 17; use shutdown/awaitTermination.
27. GC/cleaner scheduling has no guaranteed deadline.
28. No; halt can prevent unwinding scopes.
29. Yes; reference lifetime differs from resource lifetime.
30. A fake AutoCloseable records events and asserts the call order/count.
31. The caller, if the API clearly states ownership transfer.
32. Primary/cause and suppressed exceptions.

## 53. Code Review Checklist

- [ ] Is it clear who owns the resource and who must close it?
- [ ] Does the resource implement AutoCloseable/Closeable?
- [ ] If the resource is created here and needs closing, is TWR used with the proper scope?
- [ ] Is external resource cleanup distinguished from garbage collection?
- [ ] With multiple resources, is the reverse closing order accounted for?
- [ ] Is failure of a subsequent resource right in the header handled?
- [ ] Does the constructor clean up partial acquisitions when throwing?
- [ ] Are body and close exceptions preserved as primary/suppressed?
- [ ] Are checked exceptions from close not swallowed without good reason?
- [ ] Are resource variables used in `try (existing)` final/effectively final?
- [ ] Is continued use of the resource after it is CLOSED avoided?
- [ ] Is closing a resource owned by the caller/framework avoided?
- [ ] With wrappers, is underlying resource ownership identified?
- [ ] Is TWR used appropriately for Files.lines and I/O streams?
- [ ] Are JDBC transactions and connection pool lifecycles handled separately?
- [ ] Do temporary files have a separate deletion policy?
- [ ] Does a custom close have an idempotency/use-after-close contract?
- [ ] If the resource is concurrent, is there safe close/release state handling?
- [ ] Is assuming all Java 17 Lock/ExecutorService are AutoCloseable avoided?
- [ ] Are finalizer/Cleaner/GC not relied upon for timely closing?
- [ ] Have success, body exception, close exception, acquisition failure, and return been tested?
- [ ] Does cleanup verification not depend on GC timing?
- [ ] Is ownership documented when an API returns a stream/resource outward?

## 54. Official Java 17 Documentation

- [Java SE 17 API — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): close method, exceptions, and contract.
- [Java SE 17 API — Closeable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html): I/O close, IOException, idempotency.
- [JLS Java 17 §14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): resource specification, evaluation, close order, and exceptions.
- [JLS Java 17 §4.12.4 — final variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): final and effectively final.
- [Java SE 17 API — Throwable.getSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getSuppressed()): suppressed exceptions.
- [Java SE 17 API — BufferedReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html): buffered text input.
- [Java SE 17 API — Files.newBufferedReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#newBufferedReader(java.nio.file.Path,java.nio.charset.Charset)): resource that needs closing.
- [Java SE 17 API — Files.lines](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#lines(java.nio.file.Path,java.nio.charset.Charset)): file-backed Stream.
- [Java SE 17 API — Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): AutoCloseable stream.
- [Java SE 17 API — Connection](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html): JDBC lifecycle, transaction.
- [Java SE 17 API — PreparedStatement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html): SQL prepared statement.
- [Java SE 17 API — ResultSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html): SQL result set.
- [Java SE 17 API — Cleaner](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html): backup-only automatic cleanup.
- [Java SE 17 API — Lock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Lock.html): lock/unlock.
- [Java SE 17 API — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): shutdown in Java 17.
- [JEP 213 — Milling Project Coin](https://openjdk.org/jeps/213): using an existing effectively final resource in TWR.
- [Oracle Java Tutorials — The try-with-resources Statement](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html): close order and suppressed exceptions.

## 55. Summary

**`AutoCloseable`** expresses “this object has a `close()` operation.” **`try-with-resources`** guarantees that Java **attempts to call close by scope**, regardless of whether the try body succeeds, throws an exception, or returns. With multiple resources, they open left to right and close in reverse order. When both the body and close throw errors, Java keeps the **primary exception** and records cleanup errors as **suppressed exceptions**.

In Java 17, you can use a variable declared directly in the TWR header or a previously declared variable that is final/effectively final. `Closeable` is a narrower subtype of AutoCloseable for I/O. Resources such as files, file-backed streams, and JDBC objects generally require closing according to ownership; transaction commit/rollback, file deletion, or executor shutdown are separate responsibilities and do not happen automatically just because of TWR.

**Practical rule:** GC manages memory reclamation, whereas the **resource owner** must manage when to close. When ownership, exception behavior, and concurrency are clearly defined, TWR helps keep code readable, reduces the chance of missing a resource, and preserves important error information.
