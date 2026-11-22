# AutoCloseable and Closeable in try-with-resources

## Objectives

Java provides two important interfaces to represent objects that require resource release: `AutoCloseable` and `Closeable`. Both work with the `try-with-resources` syntax to automatically call `close()` when the `try` block finishes, even when an exception occurs.

After this lesson, you will know the relationship between the two interfaces, how to choose the appropriate type, the resource closing order, and how Java handles exceptions occurring during closing.

## 1. What Is AutoCloseable?

`AutoCloseable` belongs to the `java.lang` package and has been available since Java 7. It is the general contract for an object that can be closed or have its resources released. The interface declares the method:

~~~java
public interface AutoCloseable {
    void close() throws Exception;
}
~~~

This is the general signature of the interface. An implementing class can declare `close()` to throw no checked exceptions, or to throw an exception type narrower than `Exception`. For example, a class that manages database connections can throw `SQLException`, while a class that manages I/O resources can throw `IOException`.

`AutoCloseable` is used by many APIs that require resource cleanup, such as database resources, transactions, readers/writers, or application-defined resources. It allows `try-with-resources` to handle calling `close()` using the same mechanism without needing to know the internal details of the resource.

## 2. What Is Closeable and How Does It Differ?

`Closeable` belongs to the `java.io` package, has been available since Java 5, and extends `AutoCloseable`. It is designed for I/O resources:

~~~java
public interface Closeable extends AutoCloseable {
    void close() throws IOException;
}
~~~

Because `Closeable` is an `AutoCloseable`, every object that implements `Closeable` can also be used in `try-with-resources`.

| Characteristic | `AutoCloseable` | `Closeable` |
|---|---|---|
| Package | `java.lang` | `java.io` |
| Available since | Java 7 | Java 5 |
| Scope | General resource-closing contract | Focused on I/O resources |
| `close()` signature | `throws Exception` | `throws IOException` |
| Inheritance relationship | Root interface of this contract | Extends `AutoCloseable` |
| Closing multiple times | Not required to be safe when called multiple times; should be designed to be idempotent when appropriate | The contract specifies that calling `close()` when already closed has no effect |

The notable differences are the exception type and the contract for repeated closing. `Closeable.close()` declares only `IOException`, which is well suited to I/O operations. `AutoCloseable.close()` has a more general signature so it can throw `Exception`; in actual implementations, you should declare the most specific exception type possible.

When overriding a method, Java does not allow the overriding method to broaden the list of checked exceptions beyond the contract of the original method. Therefore, a class implementing `Closeable` cannot declare `close() throws Exception`; it must conform to a compatible signature, such as `throws IOException` or declaring no checked exceptions.

## 3. try-with-resources Automatically Closes Resources

The `try-with-resources` syntax was introduced in Java 7. Each resource declared inside the parentheses must implement `AutoCloseable` (including `Closeable`):

~~~java
try (BufferedReader reader = Files.newBufferedReader(path)) {
    System.out.println(reader.readLine());
}
~~~

The example above illustrates the syntax; to run standalone, the program needs to declare the `path` variable and handle `IOException`. When the `try` block finishes normally or due to an exception, Java automatically calls `reader.close()`. You do not need to write a `finally` block yourself just to close the reader.

Multiple resources can be declared, separated by semicolons:

~~~java
try (InputStream input = Files.newInputStream(source);
     OutputStream output = Files.newOutputStream(destination)) {
    input.transferTo(output);
}
~~~

Resources are initialized in left-to-right order and closed in the reverse order, meaning the resource opened later will be closed first. This order is useful when one resource depends on another.

Since Java 9, you can use a variable already declared outside if that variable is `final` or effectively final:

~~~java
BufferedReader reader = Files.newBufferedReader(path);
try (reader) {
    System.out.println(reader.readLine());
}
~~~

In Java 7 and Java 8, the resource declaration in `try-with-resources` must create the resource variable directly inside the parentheses. The example above using a previously declared variable requires Java 9 or later.

## 4. Exceptions When Closing Resources

Exception handling is an important reason to prefer `try-with-resources`.

- If the `try` body finishes normally and `close()` throws an exception, the exception from `close()` is propagated outward.
- If the `try` body has already thrown an exception and `close()` also throws an exception, the exception from the `try` body remains the primary exception. The exception from closing is attached to the list of suppressed exceptions.
- If there are multiple resources and multiple close calls throw exceptions, Java still closes the resources that were successfully initialized. When the `try` body already has a primary exception, the exceptions from the close operations are added to the primary exception in the closing order.
- If initializing a later resource fails, the resources that were previously initialized successfully are still closed in reverse order.

Suppressed exceptions can be read using `Throwable.getSuppressed()`. This preserves the original error while avoiding losing information about resource cleanup errors.

This is an advantage over closing manually in `finally`: if closing in `finally` throws an exception, it can mask an important exception arising from the main processing logic if the code does not carefully manage both cases.

## 5. Complete Example: Closing Order and Suppressed Exceptions

Save the following program to the file `Main.java`. The `DemoResource` class implements `Closeable`, and therefore also satisfies `AutoCloseable`. It prints its name when closed and intentionally throws an `IOException` to illustrate how Java stores secondary exceptions.

~~~java
import java.io.Closeable;
import java.io.IOException;

final class DemoResource implements Closeable {
    private final String name;
    private final boolean failOnClose;

    DemoResource(String name, boolean failOnClose) {
        this.name = name;
        this.failOnClose = failOnClose;
    }

    @Override
    public void close() throws IOException {
        System.out.println("close " + name);
        if (failOnClose) {
            throw new IOException("close-" + name);
        }
    }
}

public class Main {
    public static void main(String[] args) {
        try (DemoResource first = new DemoResource("first", true);
             DemoResource second = new DemoResource("second", true)) {
            System.out.println("body");
            throw new IllegalStateException("body-failed");
        } catch (Exception e) {
            System.out.println("primary: " + e.getMessage());
            for (Throwable suppressed : e.getSuppressed()) {
                System.out.println("suppressed: " + suppressed.getMessage());
            }
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~text
javac Main.java
java Main
~~~

Exact standard output:

~~~text
body
close second
close first
primary: body-failed
suppressed: close-second
suppressed: close-first
~~~

Explanation:

1. The `try` body prints `body` and then throws an `IllegalStateException` with the message `body-failed`. This is the primary exception.
2. Java closes `second` first because it was declared after `first`. Its `close()` method prints its name and then throws an `IOException`; that exception is stored as a suppressed exception.
3. Java proceeds to close `first` and also stores the exception from this close operation as a suppressed exception.
4. The `catch` block receives the primary exception and prints each exception from `getSuppressed()`.

In this example, both close operations fail, yet closing the remaining resource is still performed. The original exception from the `try` body is not replaced by the close exceptions.

## 6. Example Using Real I/O APIs

Classes such as `BufferedReader`, `InputStream`, and `OutputStream` implement the closing contract suitable for I/O. When reading a text file, you can use `Files.newBufferedReader`:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class ReadFirstLine {
    public static void main(String[] args) {
        Path path = Path.of("input.txt");
        try (BufferedReader reader = Files.newBufferedReader(path)) {
            System.out.println(reader.readLine());
        } catch (IOException e) {
            System.err.println("Không thể đọc tệp: " + e.getMessage());
        }
    }
}
~~~

Save the code to `ReadFirstLine.java`, create an `input.txt` file in the working directory with your desired content, then compile with `javac ReadFirstLine.java` and run with `java ReadFirstLine`. The program prints the first line of the file; if the file is empty, `readLine()` returns `null`. If opening, reading, or closing the file raises an `IOException`, the `catch` block handles the error.

## 7. Common Mistakes and How to Avoid Them

| Mistake | Cause | How to Handle |
|---|---|---|
| Object cannot be used in `try-with-resources` | The class does not implement `AutoCloseable` or a subinterface such as `Closeable` | Implement the appropriate resource-closing contract |
| A class implementing `Closeable` declares `close() throws Exception` | A checked exception broader than `IOException` is incompatible with the contract | Use `IOException` or a narrower type |
| Assuming resources are closed in declaration order | Java closes them in reverse order | The last initialized resource is closed first |
| Checking only the primary exception | Errors in `close()` can be stored as suppressed exceptions | Check `getSuppressed()` when diagnosing |
| Manually closing again without understanding the contract | Not every `AutoCloseable` is required to be safe when closed multiple times | Design clear ownership; follow each class's contract |
| Ignoring close exceptions | Releasing a resource can fail | Log or handle the exception according to the application's policy when needed |

## 8. Adoption Workflow

1. Identify which resource needs to be released and check whether that class implements `AutoCloseable` or `Closeable`.
2. Choose `try-with-resources` to ensure that initialized resources are closed automatically.
3. Declare resources in an order that fits their dependency relationships; Java will close them in reverse order.
4. Handle the exception type declared by the API. For I/O resources, this is usually `IOException`; other APIs may use a specialized exception type.
5. When error analysis is needed, preserve the primary exception and inspect suppressed exceptions as well.
6. Only manage the lifecycle manually with another mechanism when there are explicit requirements regarding ownership or closing timing.

## Key Takeaways

`AutoCloseable` is the general contract for closeable resources; `Closeable` extends it and focuses on I/O with `IOException`. `try-with-resources` calls `close()` automatically, closes resources in the reverse order of initialization, and preserves closing errors as suppressed exceptions when the `try` body has already thrown an exception.
