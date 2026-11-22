# AutoCloseable and try-with-resources: Explicit Resource Closing in Java

## 1. Problem: Why Do Resources Need to Be Closed?

Java objects have their heap memory managed by the Garbage Collector (GC), yet many objects also own **off-heap** resources: file descriptors, sockets, database connections, I/O streams, operating system handles, or native memory regions. When an object is no longer referenced, the GC may reclaim its memory; that **does not guarantee** off-heap resources are released at the right time. Waiting on the GC to close files or return connections to a pool can cause resource exhaustion, locked files, held connections, and unpredictable program behavior.

For resources with clear lifecycles, the principle is: **open when needed, use within the shortest reasonable scope, close reliably when exiting scope**. Java provides the **AutoCloseable** interface and **try-with-resources** syntax to express that principle directly in source code.

Resources that commonly need closing: **InputStream**, **OutputStream**, **Reader**, **Writer**, **Scanner** (when owning a closeable source), **java.sql.Connection**, **Statement**, **ResultSet**, **java.nio.channels.Channel**, **Files.lines(...)**, and user-defined objects with resource-release methods. An object that lives solely on the heap and holds no finite external resources generally does not need to be made AutoCloseable.

## 2. The Contracts of AutoCloseable and Closeable

**java.lang.AutoCloseable** declares a single method:

~~~java
public interface AutoCloseable {
    void close() throws Exception;
}
~~~

Objects implementing this interface can appear in the resource declaration header of **try-with-resources**. Java automatically calls **close()** when exiting the block, whether the block completes normally, throws an exception, or executes **return**.

**java.io.Closeable** extends AutoCloseable but narrows the checked exception type to **IOException**:

~~~java
public interface Closeable extends AutoCloseable {
    void close() throws IOException;
}
~~~

Key differences to know:

| Property | AutoCloseable | Closeable |
| --- | --- | --- |
| Scope of use | General-purpose interface for objects needing cleanup | Traditionally used for I/O sources/destinations |
| close declaration | May throw Exception | May throw IOException |
| Calling close multiple times | Not required to be idempotent; design safely if possible | Contract requires subsequent calls after closing to have no effect |
| try-with-resources compatibility | Yes | Yes |

**Idempotent** here means calling **close()** again neither alters state nor causes new side effects. Do not infer that every AutoCloseable is safe to close twice; read the contract of the specific resource type.

**close()** simply means completing/releasing the work that the class promises to clean up. It does not strictly mean “destroy the object”, “delete data”, or “physically disconnect”: for instance, **Connection.close()** on a connection pool typically returns the connection to the pool per the library's contract.

## 3. Standard Syntax and Lifecycle

~~~java
try (ResourceType resource = acquire()) {
    use(resource);
} catch (Exception e) {
    handle(e);
}
~~~

Here **ResourceType** must implement AutoCloseable; **acquire**, **use**, and **handle** are illustrative names rather than a standalone Java program. The actual sequence is:

1. Evaluate expressions and initialize resources.
2. Run the **try** body.
3. Call **close()** automatically when leaving the **try** body.
4. If **catch** or **finally** clauses are attached to the overall construct, they execute after the resource-closing step, depending on control flow and exceptions.

If there are multiple resources, they are created in **left-to-right order** but closed in **reverse order**. This is the “last in, first out” rule, very useful when a later resource depends on an earlier one.

### Runnable Example: Opening/Closing Order

File **ResourceOrderDemo.java**:

~~~java
public class ResourceOrderDemo {
    static final class Tracked implements AutoCloseable {
        private final String name;

        Tracked(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        void work() {
            System.out.println("work " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        try (Tracked first = new Tracked("A");
             Tracked second = new Tracked("B")) {
            first.work();
            second.work();
        }
        System.out.println("done");
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac ResourceOrderDemo.java
java ResourceOrderDemo
~~~

Expected output:

~~~text
open A
open B
work A
work B
close B
close A
done
~~~

There is no need to call **first.close()** or **second.close()** inside the **try** body. If an exception is thrown while initializing **second**, **first** is still closed; any resource not yet successfully initialized has no corresponding close call. If the block body uses **return**, Java still attempts to close the resources before the method actually returns.

## 4. Applying to Files and Data Streams

The example below opens both a read source and a write destination and lets Java close both. File **CopyTextFile.java**:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class CopyTextFile {
    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            System.out.println("Usage: java CopyTextFile <source> <destination>");
            return;
        }

        Path source = Path.of(args[0]);
        Path destination = Path.of(args[1]);

        try (BufferedReader reader =
                     Files.newBufferedReader(source, StandardCharsets.UTF_8);
             BufferedWriter writer =
                     Files.newBufferedWriter(destination, StandardCharsets.UTF_8)) {
            String line;
            while ((line = reader.readLine()) != null) {
                writer.write(line);
                writer.newLine();
            }
        }

        System.out.println("File copied.");
    }
}
~~~

Run:

~~~bash
javac CopyTextFile.java
java CopyTextFile input.txt output.txt
~~~

If **input.txt** exists, is readable, and there are no write errors, the program prints:

~~~text
File copied.
~~~

**Files.newBufferedWriter** with default options creates the destination file if it does not exist or overwrites existing contents. Do not use the same path for source and destination in this example: opening the destination can truncate the file while the source is still being read. This snippet copies **text lines** and normalizes line separators according to the platform; when copying raw bytes and preserving appropriate metadata is needed, see **Files.copy(...)**. For sensitive or critical data, proactively design rules for writing to a temporary file, verifying the result, and safely replacing the target file.

Closing the resource may automatically **flush** buffered data under the Writer contract; however, errors during flush/close can still occur. Do not assume “reaching the end of the try body” means data has already been written and closed successfully. For critical writes, let exceptions propagate or handle them transparently after closing.

## 5. Exceptions on Close: Primary and Suppressed

An important difference between **try-with-resources** and a hand-written **finally** block is that Java preserves the primary meaningful exception when both the **try** body and **close()** fail.

- If the **try** body throws exception **A**, and then **close()** throws exception **B**, **A** remains the primary exception; **B** is stored in **A.getSuppressed()**.
- If the **try** body succeeds but **close()** fails, the exception from **close()** is thrown outward.
- If there are multiple resources and multiple close calls fail, the first close exception that occurs (in reverse closing order) becomes the primary exception when the **try** body has not failed; the remaining close exceptions are added as suppressed exceptions.
- If creating a subsequent resource fails, Java still closes the previously created resources; any additional close errors are also attached as suppressed on the primary initialization error.

### Runnable Example: Avoiding Loss of Business Errors

File **SuppressedDemo.java**:

~~~java
public class SuppressedDemo {
    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws Exception {
            throw new Exception("close error");
        }
    }

    public static void main(String[] args) {
        try (FailingResource resource = new FailingResource()) {
            throw new IllegalStateException("processing error");
        } catch (Exception e) {
            System.out.println("primary: " + e.getMessage());
            for (Throwable suppressed : e.getSuppressed()) {
                System.out.println("suppressed: " + suppressed.getMessage());
            }
        }
    }
}
~~~

~~~bash
javac SuppressedDemo.java
java SuppressedDemo
~~~

Expected output:

~~~text
primary: processing error
suppressed: close error
~~~

In real error handling, log the full **Throwable** or inspect **getSuppressed()** when investigating cleanup failures. Printing only **getMessage()** as in the example can lose stack traces. Exceptions from **close()** must have a handling policy based on the contract: they may be propagated, wrapped with cause, reported to the caller, or logged when unrecoverable. Do not silently swallow all close errors.

### Why Does Manual finally Easily Mask Errors?

~~~java
// Illustrates the issue; not a standalone program:
Resource resource = acquire();
try {
    use(resource);          // may throw error A
} finally {
    resource.close();       // may throw error B, masking A
}
~~~

**try-with-resources** handles preserving the primary error and suppressed errors consistently. It also prevents forgetting to close a resource on a **return** branch or an exception-throwing branch. However, despite automatic closing, resources can still report errors when closing, and the program must choose the right handling strategy.

## 6. Declaring Multiple Resources and Using Existing Variables

### Declaring Multiple Resources

~~~java
try (InputStream source = Files.newInputStream(sourcePath);
     OutputStream target = Files.newOutputStream(targetPath)) {
    source.transferTo(target);
}
~~~

This is an illustrative snippet within a method that already has **sourcePath**, **targetPath**, and corresponding imports. **target** closes before **source**. Use only when both paths are valid and distinct; **Files.newOutputStream** may truncate the target file by default. With some wrappers, you only need to close the outermost wrapper because closing it closes the underlying stream; clarify who owns the underlying stream.

### Java 9+: final or effectively final Variables

Since Java 9, you can use a resource variable declared before the block, provided that variable is **final or effectively final**:

~~~java
BufferedReader reader = Files.newBufferedReader(path);
try (reader) {
    System.out.println(reader.readLine());
}
~~~

This is an illustrative snippet inside a method with **path**, imports, and appropriate **IOException** handling. The **reader** variable is not reassigned after initialization; if reassigned, the **try (reader)** syntax is invalid. After the **try** block, the variable may still exist in scope, but the object is closed; do not continue using it as an open resource.

Consider declaring resources **directly inside try** whenever possible: that syntax conveys ownership scope most clearly and is easier to inspect during code review.

### With catch and finally

~~~java
try (BufferedReader reader = Files.newBufferedReader(path)) {
    System.out.println(reader.readLine());
} catch (IOException e) {
    System.err.println("Could not read file: " + e.getMessage());
} finally {
    System.out.println("Finished read operation");
}
~~~

If opening, reading, or closing raises an **IOException**, the **catch** branch can handle that exception. The **finally** block of the statement runs after all resource closes; do not use it to call **reader.close()** a second time. If a specific AutoCloseable object's **close()** method declares a broader exception type, that exception type must be caught or declared according to Java rules.

## 7. Designing Your Own AutoCloseable Class

Implementing AutoCloseable makes sense when an object **truly owns** a finite resource that must be closed at a deterministic time (sessions, native handles, transaction scopes, data collectors, etc.). The class should document who creates it, who closes it, which methods remain valid after closing, and whether closing multiple times is safe.

File **SessionDemo.java** is a minimal model of lifecycle state; it does not open a real network connection:

~~~java
public class SessionDemo {
    static final class Session implements AutoCloseable {
        private boolean closed;

        void send(String message) {
            if (closed) {
                throw new IllegalStateException("Session closed");
            }
            System.out.println("send: " + message);
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                System.out.println("session closed");
            }
        }
    }

    public static void main(String[] args) {
        try (Session session = new Session()) {
            session.send("hello");
        }
        System.out.println("finished");
    }
}
~~~

~~~bash
javac SessionDemo.java
java SessionDemo
~~~

Expected output:

~~~text
send: hello
session closed
finished
~~~

The example intentionally makes **close()** idempotent. With real resources, **close()** needs to release or hand off ownership properly; if the class holds multiple resources, think about cleanup order and handling when one close fails. If multiple threads operate concurrently, a plain boolean **closed** as in the example is insufficient to guarantee thread safety; a separate synchronization contract is required. Do not treat this simulated example as a production network session.

If your **AutoCloseable.close()** implementation cannot throw a checked exception, you can declare **public void close()** as in the example; callers of the class will not have to catch an unnecessary generic **Exception**. If I/O errors can occur, consider **Closeable**, **IOException**, or a specific exception type fitting the API.

## 8. Who Owns the Resource? Ownership Boundaries

The most important question before adding **try-with-resources** is: **does the object in this scope belong to my responsibility to close?**

- **Create and own**: a method that calls **Files.newInputStream** itself is usually responsible for closing that stream, ideally with try-with-resources.
- **Borrow to use**: if receiving a stream from a caller and the contract states the caller manages its lifecycle, do not close the stream inside the helper; closing it will surprise the caller and can break subsequent operations.
- **Transfer ownership**: if an API returns an AutoCloseable to the caller, document clearly that the caller must close it. Do not close it right before returning the object.
- **Wrappers**: closing a **BufferedReader** or **BufferedInputStream** normally closes the underlying source; do not put the source in the same try-with-resources just to close it redundantly when the wrapper already owns it, unless the contract requires it.
- **Shared resources**: do not put a shared client or shared pool inside a per-request try-with-resources if closing it would affect other requests.

Example of clear ownership APIs:

~~~java
// Caller provides the stream and retains ownership:
static String firstLine(BufferedReader borrowed) throws IOException {
    return borrowed.readLine();     // helper does not close borrowed
}

// Method opens and closes the stream itself:
static String firstLine(Path path) throws IOException {
    try (BufferedReader owned = Files.newBufferedReader(path)) {
        return owned.readLine();
    }
}
~~~

The two methods above are **illustrative method snippets**, needing placement inside a Java class with appropriate imports. They produce the same read result, yet their closing responsibilities are completely different. Avoid programming by “closing just in case” without determining ownership.

## 9. Familiar Cases Beyond File I/O

### JDBC

Core JDBC resource types (**Connection**, **Statement/PreparedStatement**, **ResultSet**) can all be managed with try-with-resources. Example when **dataSource** is already provided and SQL returns data:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
             connection.prepareStatement("SELECT name FROM users WHERE id = ?")) {
    statement.setLong(1, userId);

    try (ResultSet rows = statement.executeQuery()) {
        if (rows.next()) {
            System.out.println(rows.getString("name"));
        }
    }
}
~~~

This is an **illustrative snippet, not a standalone program**: it requires importing **java.sql.***, a **dataSource** object, **userId**, matching schema, and **SQLException** handling. Closing order: ResultSet, PreparedStatement, Connection. With a connection pool, calling **close()** on a connection proxy typically returns the connection to the pool, per the pool's contract.

**Closing resources does not replace transaction management**. With manual JDBC transactions, clearly determine when to **commit/rollback**; do not assume Connection.close() automatically commits on behalf of business logic. Automatic rollback, if any, depends on the driver/pool and configuration.

### Files.lines and Stream

**Stream** also has a **close()** mechanism, though not every stream holds off-heap resources. For example, **Files.lines(path)** maintains an underlying reader source and therefore needs closing:

~~~java
try (java.util.stream.Stream<String> lines =
         Files.lines(path, StandardCharsets.UTF_8)) {
    long count = lines.filter(line -> !line.isBlank()).count();
    System.out.println(count);
}
~~~

This snippet belongs inside a method with **path**, appropriate imports, and **IOException** handling. By contrast, a stream created from **list.stream()** generally has no resources to release. For file-backed streams, avoid returning a **Stream** out of a closed **try** block: the caller will receive a stream whose underlying source may already be closed. If returning a stream is needed, explicitly transfer closing responsibility to the caller or return materialized data.

### Scanner and System.in

**Scanner** implements Closeable. However, closing **new Scanner(System.in)** also closes the underlying **System.in** source. If code merely borrows standard input for the entire application, do not arbitrarily close it inside a short-lived helper; closing decisions belong to the application lifecycle management layer.

## 10. Common Mistakes and How to Avoid Them

| Mistake | Impact | Proper Practice |
| --- | --- | --- |
| Opening a stream/connection and closing only on the success branch | Resource leak on exception/return | Place owned resources in try-with-resources |
| Trusting GC to close files on time | Unpredictable retention of handles/connections | Close explicitly at the ownership boundary |
| Calling close() on a resource lent by the caller | Caller receives an already-closed resource | State and respect ownership clearly |
| Closing both wrapper and raw source without knowing the contract | Double closing; AutoCloseable class may not be idempotent | Understand ownership chain and close the right object |
| Catching Exception and ignoring everything | Hides business errors or cleanup errors | Handle or propagate informative errors |
| Logging only the primary exception | Loses trace of failures when close() fails | Inspect suppressed exceptions / log stack traces |
| Returning a resource after try has already ended | Recipient uses a closed object | Return data or transfer ownership clearly |
| Holding a connection too long inside a try block | Pool exhaustion, longer lock hold times | Narrow the usage scope |
| Putting a shared resource in per-request try blocks | Premature closing, breaks other tasks | Let a higher-level owner manage the lifecycle |
| Starting async work and immediately exiting try | Worker may use a closed resource | Wait for work to finish within scope or transfer ownership carefully |

### Note on Asynchronous Code and Multithreading

**try-with-resources** manages a **synchronous lexical scope**: it calls close when execution leaves the block. It **does not automatically wait** for a **CompletableFuture**, new thread, or callback using the resource launched inside the block. If a callback continues after the block exits, the resource may already be closed. Keep the entire resource usage duration within scope or design an owner that lives long enough to close when the async task truly finishes. **AutoCloseable** also does not inherently guarantee concurrent use/closing is thread-safe.

## 11. Code Review Checklist

When reading Java code involving resources, verify in order:

1. **What is the resource?** Does it own a file descriptor, socket, cursor, connection, or handle that needs timely termination?
2. **Who owns it?** Does the current code create, borrow, or receive transferred ownership?
3. **Can opening partially succeed?** If opening the second resource fails, is the first resource cleaned up?
4. **Do all exit paths close it?** Normal completion, **return**, initialization errors, processing errors, and closing errors all need consideration.
5. **Is the closing order appropriate?** Dependent resources usually need to close before their owners.
6. **Are close() errors visible?** Is the root cause lost, and are there suppressed exceptions to observe?
7. **Is the scope short enough and long enough?** Do not hold resources needlessly; nor close before active tasks finish.
8. **What does the specific library contract say?** Closeable, JDBC pools, I/O wrappers, Streams from Files, and custom AutoCloseable classes have different semantics.

## 12. Self-Check Exercises

**Exercise 1 — Predict the order.** With two resources **A** then **B** in the same try-with-resources, and the try body printing **body**. What is the sequence related to closing?

Answer: **body**, then **B.close()**, then **A.close()**; if constructors log messages, initialization prints **A** before **B**.

**Exercise 2 — Dual failure.** The try body throws **IllegalStateException("business")**, and resource close throws **IOException("close")**. Which exception is thrown outward?

Answer: **IllegalStateException("business")** is the primary exception; **IOException("close")** is in **getSuppressed()** of the primary exception (assuming no other abnormal exceptions).

**Exercise 3 — Ownership review.** A helper receives an **InputStream** managed by the caller and only needs to read the header. Should the stream be placed in **try (input)** inside the helper?

Answer: No, if the contract states the caller owns it. The helper reads and lets the caller close it. Only take over closing responsibility when the API specifies an explicit ownership transfer.

**Exercise 4 — Asynchrony.** A background task is still reading a file when the try block containing the stream just finishes. What can happen?

Answer: The background reading thread may encounter an error because the source is already closed. You must structure the lifecycle to close after the task completes.

## 13. Key Takeaways

**AutoCloseable** is the contract for a closeable resource; **try-with-resources** turns that contract into automatic cleanup, in reverse order for multiple resources, while preserving the primary exception via suppressed exceptions. Use it when **the current scope owns the resource**, coordinate close error handling, track resource lifetimes across async boundaries, and follow each API's specific contract. Heap memory management by the GC cannot replace explicit resource management.
