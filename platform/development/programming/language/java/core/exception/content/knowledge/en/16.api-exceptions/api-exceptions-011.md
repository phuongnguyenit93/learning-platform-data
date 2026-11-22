# UncheckedIOException When an API Does Not Declare Checked IOException

In Java, `java.io.IOException` is a **checked exception**: if a call can throw it, the enclosing method must catch it or declare an appropriate `throws` clause. However, many important Java callbacks such as `Function.apply`, `Consumer.accept`, `Supplier.get`, `Predicate.test`, and `Runnable.run` **do not declare checked exceptions**. What happens when logic placed inside a callback still needs to read files, write data, or perform I/O?

`java.io.UncheckedIOException` provides a way to **wrap an IOException into an unchecked exception** with clear semantics. It extends `RuntimeException`, preserves the original `IOException` as its **cause**, and can propagate through APIs that do not allow checked `throws`. The final handler can still inspect the real cause via `getCause()`.

**Rule to remember:** use `UncheckedIOException` when **an operation genuinely fails due to an IOException**, **the callback/API boundary does not allow passing checked IOException directly**, and **the contract policy allows converting that failure to unchecked**. This is not a trick to ignore errors: the program still fails if unhandled, the conversion must be intentional, and retrying the operation is not necessarily safe.

This lesson explains the hierarchy, constructor usage, runnable Java 17 examples, lambdas and method references, the Stream API, `Files.lines`/`BufferedReader.lines`, reusable adapters, catching and unwrapping, resources, exception propagation, retry risks, testing, and cases where the wrapper should not be used.

## 1. Where Does `UncheckedIOException` Sit in the Hierarchy?

Simplified diagram:

```text
java.lang.Throwable
├── java.lang.Error
└── java.lang.Exception
    ├── java.io.IOException                (checked)
    │   ├── java.io.FileNotFoundException
    │   ├── java.nio.file.FileSystemException
    │   └── ...
    └── java.lang.RuntimeException         (unchecked)
        ├── java.io.UncheckedIOException
        ├── java.lang.IllegalArgumentException
        ├── java.lang.IllegalStateException
        └── ...
```

Key takeaways:

- `IOException` and its regular subclasses are **checked**.
- `UncheckedIOException extends RuntimeException`, so it is **unchecked**.
- `UncheckedIOException` **does not extend `IOException`**. A `catch (IOException e)` block does not directly catch an `UncheckedIOException` object.
- `UncheckedIOException` **holds an `IOException`** as its cause (`cause`). This is a **containment/cause-chain** relationship, not a subtype relationship.
- The constructor of `UncheckedIOException` requires the cause to be an `IOException`; not every `Exception` can directly serve as the cause in that specialized constructor.
- `UncheckedIOException` was introduced in Java 8, aligning with the heavy adoption of the Stream API and lambdas.

Type example:

```java
IOException original = new IOException("Không đọc được tệp");
UncheckedIOException wrapped = new UncheckedIOException(
        "Lỗi I/O trong callback", original);

System.out.println(wrapped instanceof RuntimeException);
System.out.println(wrapped.getCause() == original);
```

This is an **illustrative snippet** requiring imports for `java.io.IOException` and `java.io.UncheckedIOException`, and can be placed inside a method. Both checks print `true`. Conversely, you must not write `wrapped instanceof IOException`: here the two classes have no type relationship permitting that check, and the Java compiler may reject an impossible `instanceof` check between unrelated static types.

## 2. Checked Exceptions Are Incompatible with Many Functional Interfaces

Java uses the **single abstract method** (SAM) of a functional interface to type-check a lambda or method reference.

Some common SAMs:

| Functional interface | SAM | Checked `throws` declared? |
| --- | --- | --- |
| `Runnable` | `void run()` | No |
| `Supplier<T>` | `T get()` | No |
| `Consumer<T>` | `void accept(T)` | No |
| `Function<T,R>` | `R apply(T)` | No |
| `Predicate<T>` | `boolean test(T)` | No |
| `BiFunction<T,U,R>` | `R apply(T,U)` | No |
| `Callable<V>` | `V call() throws Exception` | Yes |
| Custom `IoFunction<T,R>` | `R apply(T) throws IOException` | Yes if you define it |

Example data-reading method:

```java
static String read(String path) throws IOException {
    return Files.readString(Path.of(path));
}
```

This is an **illustrative method**, requiring imports for `IOException`, `Files`, and `Path`. If you try to assign:

```java
Function<String, String> fn = Example::read;
```

it **does not compile** (assuming the method belongs to class `Example`), because `Function.apply()` does not declare `throws IOException`.

Using a method reference `::` does not automatically turn an exception into an unchecked one. Similarly:

```java
Function<String, String> fn = x -> Files.readString(Path.of(x));
```

is a **non-compiling counterexample**: the lambda body can throw checked `IOException`. Declaring `throws IOException` on the enclosing method **cannot fix** the `Function.apply` contract, because the error lies in the expression used to create the callback.

## 3. Why Can't You "Add throws" to `Function.apply`?

The standard interface has the signature `R apply(T t)`, not `R apply(T t) throws IOException`. When implementing or using a lambda expression as a `Function`, the implementation cannot declare checked exceptions broader than the SAM's contract.

An **intentionally invalid** example:

```java
class FileMapper implements Function<String, String> {
    @Override
    public String apply(String path) throws IOException {
        return Files.readString(Path.of(path));
    }
}
```

This is a **counterexample snippet** requiring the corresponding imports. The compiler reports an error because the overriding method adds checked `IOException`, which is not present in `Function.apply`.

There are four main approaches:

1. **Avoid `Function`** when you control the API: define a custom SAM with `throws IOException` and propagate the checked exception explicitly.
2. **Catch and genuinely recover** inside the callback: choose an appropriate fallback or return a result type.
3. **Catch `IOException` and wrap it in `UncheckedIOException`** if you want the exception to still propagate, but through an unchecked contract.
4. **Restructure the code**: move the I/O operation outside the callback/pipeline, where `throws IOException` can be declared.

`UncheckedIOException` corresponds to approach 3 and does not replace the other approaches.

## 4. The Two Common Constructors

Two constructors are used:

```java
new UncheckedIOException(ioException);

new UncheckedIOException("Mô tả ngữ cảnh", ioException);
```

These are **illustrative expressions**; the variable `ioException` has type `IOException`. The constructor with a message is very useful for adding context such as "failed to read configuration file" or "failed while transforming stream element".

Example:

```java
try {
    saveReport();
} catch (IOException e) {
    throw new UncheckedIOException(
            "Ghi báo cáo thất bại", e);
}
```

This is an **illustrative snippet** with `saveReport() throws IOException` defined elsewhere. Result:

- The outer exception is `UncheckedIOException`.
- `getMessage()` contains the description you provided.
- `getCause()` returns the original `IOException` object.
- The cause preserves the stack trace and details of the lower-level error.
- The caller is not forced by the compiler to catch/declare `UncheckedIOException`, yet the program can still be aborted when the callback executes.

**The constructor requires a non-null cause.** Do not create a wrapper with a fake cause or `null` to represent a "missing file" condition unrelated to an actual I/O error.

## 5. Standalone Java 17 Example: Wrapping and Catching the Right Type

Save **`UncheckedIOExceptionBasicsDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;

public class UncheckedIOExceptionBasicsDemo {
    static void load() {
        try {
            simulateRead();
        } catch (IOException e) {
            throw new UncheckedIOException(
                    "Không tải được cấu hình", e);
        }
    }

    static void simulateRead() throws IOException {
        throw new IOException("Thiết bị đọc thất bại");
    }

    public static void main(String[] args) {
        try {
            load();
        } catch (UncheckedIOException e) {
            System.out.println("Wrapper: "
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
javac -encoding UTF-8 --release 17 UncheckedIOExceptionBasicsDemo.java
java UncheckedIOExceptionBasicsDemo
```

**Exact stdout:**

```text
Wrapper: UncheckedIOException
Message: Không tải được cấu hình
Cause: IOException
Cause message: Thiết bị đọc thất bại
```

The program **deliberately simulates an error with `IOException`**, without depending on a real disk or network. This is suitable for unit-testing wrapping behavior.

Note that the error is converted **at the `load()` boundary**. If the outer API can declare `throws IOException`, wrapping may not add value; you must consider the caller's responsibility.

## 6. `getCause()` Has a Covariant Return Type

In `Throwable`, `getCause()` returns `Throwable`. Specifically, `UncheckedIOException` overrides `getCause()` with a narrower return type: **`IOException`**.

Therefore, you can write:

```java
UncheckedIOException failure =
        new UncheckedIOException(new IOException("I/O"));

IOException original = failure.getCause();
System.out.println(original.getClass().getSimpleName());
```

This is **illustrative code** requiring imports for both classes. It prints `IOException` and requires no manual cast.

This differs from `new RuntimeException(ioException)`:

```java
RuntimeException generic = new RuntimeException(
        new IOException("I/O"));
// IOException original = generic.getCause(); // Does not compile.
// getCause() here has static type Throwable.
```

Do not assume `UncheckedIOException` makes the underlying error disappear. It is a wrapper **specialized for I/O**: the cause's type and semantic meaning are preserved.

## 7. When Should You Use `UncheckedIOException`?

It is appropriate when three conditions hold simultaneously:

1. **There is a real `IOException`** from an I/O operation or an API with an I/O contract.
2. **The boundary being used does not allow checked `throws IOException`**; for example, `Function` in `Stream.map`, `Consumer` in `forEach`, or `Runnable` in an executor.
3. **The policy allows the failure to propagate as an unchecked exception** so a responsible layer can handle, report, or abort the operation.

Some examples:

- Mapping a list of `Path` values to file contents using `Stream.map`.
- Reading data inside `forEach` of an API that only accepts `Consumer`.
- An adapter to pass an I/O-throwing function to `Function<T,R>`.
- Executing a `Runnable` that needs I/O when the framework has no checked `throws`.
- A lazily reading stream (*lazy*) whose API documentation specifies that read exceptions occurring during the terminal operation are converted to `UncheckedIOException`.

**Do not wrap merely to "silence the compiler."** If a public library expects callers to choose how to recover from I/O failures, keeping checked `IOException` or designing a callback with `throws` may still be the better choice.

## 8. `Stream.map`: Why Does a Compile Error Occur?

`Stream.map` accepts `Function<? super T, ? extends R>`. The SAM `Function.apply` does not declare checked exceptions, so the following expression **intentionally does not compile**:

```java
Stream<Path> paths = Stream.of(Path.of("a.txt"));
Stream<String> contents = paths.map(Files::readString);
```

Assuming imports for `java.util.stream.Stream` and `java.nio.file.Files, Path`. The method `Files.readString(Path)` declares `throws IOException`; the method reference is incompatible with `Function<Path,String>`.

The equivalent lambda snippet:

```java
Stream<String> contents = paths.map(
        path -> Files.readString(path));
```

also fails to compile for the exact same reason.

**A `try/catch` wrapping the pipeline creation line does not fix the issue**, because the checked exception belongs to the SAM implementation. You must change **inside the lambda expression**, or change the target interface/structure.

For streams, also remember that many operations are **lazy**: creating the pipeline does not necessarily invoke the mapper immediately, so the wrapped exception may only appear when a terminal operation consumes elements.

## 9. Runnable Example: Converting `IOException` to `UncheckedIOException` in `map`

Save **`StreamUncheckedIOExceptionDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;

public class StreamUncheckedIOExceptionDemo {
    static String read(String key) throws IOException {
        if ("missing".equals(key)) {
            throw new IOException("Không tìm thấy dữ liệu: " + key);
        }
        return "Nội dung " + key;
    }

    public static void main(String[] args) {
        List<String> keys = List.of("one", "missing", "three");

        try {
            List<String> results = keys.stream()
                    .map(key -> {
                        try {
                            return read(key);
                        } catch (IOException e) {
                            throw new UncheckedIOException(
                                    "Đọc phần tử thất bại", e);
                        }
                    })
                    .toList();

            System.out.println("Kết quả: " + results);
        } catch (UncheckedIOException e) {
            System.out.println("Wrapper: " + e.getMessage());
            System.out.println("Cause: " + e.getCause().getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 StreamUncheckedIOExceptionDemo.java
java StreamUncheckedIOExceptionDemo
```

**Exact stdout:**

```text
Wrapper: Đọc phần tử thất bại
Cause: Không tìm thấy dữ liệu: missing
```

Key points to understand:

1. `read(key) throws IOException` is a method simulating an I/O operation.
2. `Stream.map` does not allow checked exceptions from the mapper.
3. The lambda **catches in place** and throws `UncheckedIOException`.
4. `toList()` consumes the stream; upon encountering `"missing"`, the mapper throws the exception.
5. Because the terminal operation does not complete, `results` never receives a final result list and the `Kết quả` print line does not execute.
6. The outer handler catches the converted exception and retrieves the cause for diagnostics.

**This does not mean all elements after `"missing"` were processed.** With this sequential stream example, evaluation stops at the error; with parallel streams, error conditions and side effects are more complex, and you should not assume deterministic fail-fast ordering or automatic rollback.

## 10. Crucial Point: Lazy Streams and When Errors Occur

A stream pipeline can be constructed without reading any file or calling any mapper. Only when a terminal operation such as `toList()`, `count()`, `forEach()`, `reduce()`, or another consuming operation runs can the callback be invoked.

Java 17 example **`StreamLazyIoDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.stream.Stream;

public class StreamLazyIoDemo {
    static String read(String name) throws IOException {
        System.out.println("Đang đọc: " + name);
        if ("bad".equals(name)) {
            throw new IOException("Không đọc được bad");
        }
        return name.toUpperCase();
    }

    public static void main(String[] args) {
        Stream<String> pipeline = Stream.of("ok", "bad")
                .map(name -> {
                    try {
                        return read(name);
                    } catch (IOException e) {
                        throw new UncheckedIOException(
                                "Mapper gặp lỗi", e);
                    }
                });

        System.out.println("Đã tạo pipeline");

        try {
            pipeline.forEach(System.out::println);
        } catch (UncheckedIOException e) {
            System.out.println("Bắt: " + e.getCause().getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 StreamLazyIoDemo.java
java StreamLazyIoDemo
```

**Exact stdout:**

```text
Đã tạo pipeline
Đang đọc: ok
OK
Đang đọc: bad
Bắt: Không đọc được bad
```

`pipeline` is created first, but reading starts when `forEach`—the terminal operation—runs. When I/O fails, the wrapped exception is thrown out of `forEach`.

**Do not assume every terminal operation executes every mapper.** For instance, some stream optimizations or short-circuit operations may avoid running certain stages. For I/O code with side effects, choosing the Stream API requires considering laziness, optimizations, and resource-closing policies.

## 11. `Consumer.accept` and `forEach` Also Do Not Declare Checked Exceptions

`Consumer<T>` accepts a value and returns no result; `accept(T)` does not declare checked exceptions. Therefore:

```java
items.forEach(item -> writeToDisk(item));
```

is an **intentionally non-compiling counterexample** if `writeToDisk` declares `throws IOException` (and `items` has an appropriate type).

Intentional conversion:

```java
items.forEach(item -> {
    try {
        writeToDisk(item);
    } catch (IOException e) {
        throw new UncheckedIOException(
                "Ghi phần tử thất bại", e);
    }
});
```

This is **illustrative code** requiring `items`, `writeToDisk`, and class imports. Any error in the callback can escape as an unchecked exception; `forEach` does not automatically catch or retry.

**Greater risk with writing data:** some earlier elements may have already been written successfully. When an error occurs mid-loop, there is no automatic rollback. If writing multiple items must be atomic, you need a transaction, staging, or compensating action mechanism tailored to the target system.

## 12. When Using `Runnable` or Executor Jobs

`Runnable.run()` does not declare checked exceptions. If the work must call an API that throws `IOException`, you can catch and wrap it:

```java
Runnable job = () -> {
    try {
        doIoWork();
    } catch (IOException e) {
        throw new UncheckedIOException(
                "Job thất bại vì I/O", e);
    }
};
```

This is **illustrative code**; `doIoWork() throws IOException` must be defined.

Differences:

- Calling `job.run()` directly can throw `UncheckedIOException` to the caller.
- If `job` is executed by `ExecutorService.submit`, the error can be observed via `Future.get()` as an `ExecutionException` per the executor contract.
- With `CompletableFuture`, a task error can be wrapped in `CompletionException` when `join()` or a corresponding API propagates the failure.
- Framework-created wrappers are a **different layer** from the `UncheckedIOException` thrown by your code. To classify the root cause further, you may need to inspect the cause chain.

**Do not confuse** "unchecked" with "successfully handled by the thread pool." The exception may reside inside the Future result and not be printed to the console automatically the way you might expect.

## 13. `Callable` Can Be an Option That Preserves Checked Exceptions

`Callable<V>.call() throws Exception` **allows checked exceptions**. If you control the callback interface to be used, wrapping is not necessarily required.

Java 17 example **`CallableCheckedDemo.java`**:

```java
import java.io.IOException;
import java.util.concurrent.Callable;

public class CallableCheckedDemo {
    static String read() throws IOException {
        throw new IOException("Nguồn chưa sẵn sàng");
    }

    public static void main(String[] args) {
        Callable<String> task = CallableCheckedDemo::read;

        try {
            task.call();
        } catch (Exception e) {
            System.out.println("Loại: "
                    + e.getClass().getSimpleName());
            System.out.println("Message: " + e.getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 CallableCheckedDemo.java
java CallableCheckedDemo
```

**Exact stdout:**

```text
Loại: IOException
Message: Nguồn chưa sẵn sàng
```

The method `read() throws IOException` is compatible with `Callable.call() throws Exception`. At the call site through the `Callable` variable, the compiler forces the caller to catch/declare `Exception` according to the SAM's broader signature.

**Do not switch to `UncheckedIOException` just out of habit of writing adapters**, if the existing contract already supports checked I/O and the caller is responsible for handling it.

## 14. Designing a Custom Functional Interface with `throws IOException`

If you create your own API, you can express I/O capability directly:

```java
@FunctionalInterface
interface IoFunction<T, R> {
    R apply(T input) throws IOException;
}
```

This is an **illustrative interface**, requiring `import java.io.IOException`. The method reference `Files::readString` can match `IoFunction<Path,String>` because the parameter, return type, and checked exception match.

Standalone example **`IoFunctionCheckedDemo.java`**:

```java
import java.io.IOException;

public class IoFunctionCheckedDemo {
    @FunctionalInterface
    interface IoFunction<T, R> {
        R apply(T input) throws IOException;
    }

    static String read(String name) throws IOException {
        if (name.isBlank()) {
            throw new IOException("Tên nguồn rỗng");
        }
        return "DATA:" + name;
    }

    static <T, R> R execute(IoFunction<T, R> task, T input)
            throws IOException {
        return task.apply(input);
    }

    public static void main(String[] args) {
        IoFunction<String, String> task = IoFunctionCheckedDemo::read;

        try {
            System.out.println(execute(task, "orders"));
            System.out.println(execute(task, ""));
        } catch (IOException e) {
            System.out.println("Đã bắt IOException: "
                    + e.getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 IoFunctionCheckedDemo.java
java IoFunctionCheckedDemo
```

**Exact stdout:**

```text
DATA:orders
Đã bắt IOException: Tên nguồn rỗng
```

No `UncheckedIOException` is needed here, because **the entire chain of callbacks and calling methods** permits checked `IOException`.

This design is useful when API users genuinely need to distinguish I/O failures as part of the compile-time contract. Conversely, standard frameworks accepting `Function` cannot have their `Function.apply` signature altered, in which case an adapter is an option.

## 15. Adapter Converting `IoFunction` to `Function`

To avoid repeating `try/catch` in every lambda, you can create a reusable adapter. The core role of the adapter is to **change the error contract at one clear point**.

Save **`IoFunctionAdapterDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;
import java.util.Objects;
import java.util.function.Function;

public class IoFunctionAdapterDemo {
    @FunctionalInterface
    interface IoFunction<T, R> {
        R apply(T input) throws IOException;
    }

    static <T, R> Function<T, R> unchecked(
            IoFunction<T, R> function) {
        Objects.requireNonNull(function, "function");
        return input -> {
            try {
                return function.apply(input);
            } catch (IOException e) {
                throw new UncheckedIOException(
                        "I/O trong Function.apply", e);
            }
        };
    }

    static String read(String key) throws IOException {
        if ("bad".equals(key)) {
            throw new IOException("Không đọc được bad");
        }
        return "OK-" + key;
    }

    public static void main(String[] args) {
        Function<String, String> mapper =
                unchecked(IoFunctionAdapterDemo::read);

        System.out.println(mapper.apply("good"));

        try {
            List<String> values = List.of("a", "bad", "c");
            System.out.println(values.stream()
                    .map(mapper)
                    .toList());
        } catch (UncheckedIOException e) {
            System.out.println("Wrapper: " + e.getMessage());
            System.out.println("Cause: " + e.getCause().getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 IoFunctionAdapterDemo.java
java IoFunctionAdapterDemo
```

**Exact stdout:**

```text
OK-good
Wrapper: I/O trong Function.apply
Cause: Không đọc được bad
```

Advantages:

1. The method reference `IoFunctionAdapterDemo::read` is accepted by the target type `IoFunction` because the SAM declares `throws IOException`.
2. The adapter returns a `Function` usable in `Stream.map`.
3. I/O failures still emerge as `UncheckedIOException`, preserving the cause.
4. Every call site using the adapter shares **one consistent error-conversion policy**.
5. `Objects.requireNonNull` makes the adapter's precondition explicit.

Disadvantage: the `Function` signature drops the checked exception constraint; callers must read the adapter's contract documentation and know where to catch errors if the pipeline fails.

## 16. Adapters for `Consumer` and `Runnable`

Similar to `IoFunction`, you can build checked interfaces:

```java
@FunctionalInterface
interface IoConsumer<T> {
    void accept(T value) throws IOException;
}

@FunctionalInterface
interface IoRunnable {
    void run() throws IOException;
}
```

These are **two illustrative interfaces** requiring `import IOException`. Simple adapters:

```java
static <T> Consumer<T> uncheckedConsumer(IoConsumer<T> io) {
    return value -> {
        try {
            io.accept(value);
        } catch (IOException e) {
            throw new UncheckedIOException(
                    "Consumer I/O thất bại", e);
        }
    };
}

static Runnable uncheckedRunnable(IoRunnable io) {
    return () -> {
        try {
            io.run();
        } catch (IOException e) {
            throw new UncheckedIOException(
                    "Runnable I/O thất bại", e);
        }
    };
}
```

These are **illustrative methods**, assuming both interfaces above are in scope and `Consumer`, `IOException`, and `UncheckedIOException` are imported.

Before putting adapters into a shared library, determine:

- Are all three types (`IoFunction`, `IoConsumer`, `IoRunnable`) actually needed?
- When I/O fails, where does the final handler live?
- Should the message include a task name or element ID?
- Is it possible for a task to have written **partially** before failing?
- Does the API receiving `Consumer`/`Runnable` have its own policy for unchecked exceptions?

Never create an adapter that "swallows IOException and continues" if the contract requires reporting failure.

## 17. `Files.readString` Still Declares Checked `IOException`

A common misconception: because `UncheckedIOException` exists, all JDK file-reading APIs automatically throw unchecked exceptions. **False.**

For example, `Files.readString(Path)` declares `throws IOException`. When called directly:

```java
String text = Files.readString(Path.of("config.txt"));
```

this is **illustrative code**; the enclosing method must catch/declare `IOException`. Java **does not automatically wrap it into `UncheckedIOException`** here.

If you place it inside `Stream.map`, you can choose to wrap inside the lambda:

```java
Function<Path, String> readText = path -> {
    try {
        return Files.readString(path);
    } catch (IOException e) {
        throw new UncheckedIOException(
                "Không đọc được: " + path.getFileName(), e);
    }
};
```

This is an **illustrative snippet**, requiring imports for `Path`, `Files`, `Function`, `IOException`, and `UncheckedIOException`.

Principle: **read the Javadoc of the specific method**. Some JDK APIs wrap I/O errors during lazy processing, while others continue using checked `IOException` directly.

## 18. `Files.lines`: Errors When Opening the Stream vs. Errors When Consuming the Stream

`Files.lines(Path)` creates a `Stream<String>` that reads lines from a file. The error contract has two distinct moments:

1. **Opening the source / creating the stream:** calling `Files.lines(path)` can throw **checked `IOException`**. The caller must catch/declare it.
2. **Reading further lines during stream consumption:** if an I/O error occurs during lazy processing, the API's behavior may be to throw **`UncheckedIOException`**.

Structural example:

```java
try (Stream<String> lines = Files.lines(path)) {
    lines.forEach(System.out::println);
}
```

This is **illustrative code** with `path` defined and `Stream` and `Files` imported; the enclosing method must handle/declare `IOException` from the open step.

**Important point:** `try-with-resources` closes the stream, releasing the file handle. Closing the stream does not automatically guarantee read errors are handled; you must catch at the appropriate boundary. In a pipeline with side effects, lines before the error occurred may have already been processed.

If you only catch `UncheckedIOException` and omit checked `IOException` when opening the file, the code may fail to compile. Conversely, only catching `IOException` around a pipeline is not enough to catch the unchecked wrapper from the lazy reading phase.

## 19. Java 17 Example: Reading a File Line by Line and Closing the Stream

This example runs using a temporary file created by the program itself, **without depending on a pre-existing file path**. It demonstrates the success path rather than forcing a non-deterministic I/O failure.

Save **`FilesLinesDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class FilesLinesDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("line-demo-", ".txt");

        try {
            Files.writeString(file, "alpha\nbeta\n",
                    StandardCharsets.UTF_8);

            try (Stream<String> lines =
                         Files.lines(file, StandardCharsets.UTF_8)) {
                lines.forEach(line ->
                        System.out.println("Dòng: " + line));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 FilesLinesDemo.java
java FilesLinesDemo
```

**Exact stdout when the filesystem allows creating/reading/deleting temp files:**

```text
Dòng: alpha
Dòng: beta
```

Here, no `UncheckedIOException` occurs because reading succeeds. What matters is that **the `main throws IOException` signature** covers checked operations such as creating, writing, opening, and deleting the file.

The example creates/deletes a temporary file on the learner's machine. If a sandbox forbids filesystem writes, the program may throw `IOException` before printing stdout; that is an environmental condition, not exception-wrapper behavior.

## 20. `BufferedReader.lines()` and `UncheckedIOException`

`BufferedReader.lines()` returns a stream of lines. Because `Stream` has no checked `throws IOException` on standard operations, **I/O errors occurring while reading lines through the stream** are reported per the `BufferedReader.lines()` contract using **`UncheckedIOException`**.

Conceptual example:

```java
try (BufferedReader reader = Files.newBufferedReader(path)) {
    reader.lines().forEach(System.out::println);
}
```

This is **illustrative code** with `path`, required imports, and an enclosing method handling checked `IOException` when opening/closing the reader.

Note:

- `Files.newBufferedReader(path)` can throw **checked IOException**.
- Consuming `reader.lines()` can throw **UncheckedIOException** if the reader encounters an I/O error.
- `reader.lines()` does not independently own/close the reader; in this pattern, **try-with-resources wraps the reader**.
- Do not read from the reader concurrently outside the stream while the stream is being consumed; the Javadoc states you should not manipulate the reader while the stream is operating because results may be undefined.
- Do not assume `BufferedReader.readLine()` (called directly) converts to `UncheckedIOException`; it still declares checked `IOException`.

This difference is a clear example: **for the same data object, the direct API and the stream API can advertise different exceptions**.

## 21. Pattern for Classifying Errors at the File-Reading Boundary

A handler can distinguish:

```java
try (Stream<String> lines = Files.lines(path)) {
    lines.forEach(this::consumeLine);
} catch (UncheckedIOException e) {
    handleReadFailure(e.getCause());
} catch (IOException e) {
    handleOpenOrCloseFailure(e);
}
```

This is **illustrative skeleton code**: `this::consumeLine` must be compatible with `Consumer<String>` without throwing checked exceptions, and the handler methods must exist. The order of the two handlers is not constrained by a subtype relationship because `UncheckedIOException` does not extend `IOException`.

**Do not treat catching the two types separately as proof that the error occurred in one specific step.** For example, `IOException` can also arise from cleanup; if a wrapper was thrown in the body, the cleanup error may be attached as a suppressed exception. Analysis requires operation context and the cause.

If a handler can genuinely recover, make the subsequent handling explicit. Otherwise, rethrow the exception or forward the error to a responsible layer rather than logging a line and silently returning success.

## 22. `Files.list`, `Files.walk`, and Directory Operations

Filesystem-related APIs can also use Streams, for example:

- `Files.list(Path)`: creates a stream of direct entries in a directory; can throw checked `IOException` on open.
- `Files.walk(Path, ...)`: creates a stream traversing a file tree; can throw checked `IOException` on setup.
- I/O errors arising during lazy traversal can be converted to `UncheckedIOException` per the respective API contract.

Pay special attention to:

1. **Closing the stream** with try-with-resources, as the stream may hold OS resources.
2. Part of the directory tree may have already been traversed before an error occurs; there is no automatic rollback.
3. The file tree can change during traversal; "a file just checked to exist" does not guarantee the next operation succeeds.
4. Permissions, symbolic links, deleted files, mounted filesystems, and race conditions can cause I/O errors.
5. Do not throw `UncheckedIOException` merely to express that an entry did not match a filter; filtering out an entry is a **normal branch**, not an I/O error.

One way to clarify issues is to **clearly separate opening the source, processing the stream, and closing the source**, instead of catching a generic `Exception` and losing context.

## 23. `UncheckedIOException` Is Not a Business "Data Not Found" Error

The class name describes **a wrapped IOException**, not domain semantics like `CustomerNotFoundException`.

Examples:

- A required config file is missing → `NoSuchFileException` when accessing the file can be the cause.
- A key does not exist in a `Map` → usually unrelated to I/O; use an empty result or another exception contract.
- A record is absent from a database → may be a normal business outcome, and should not default to creating `UncheckedIOException`.
- A filesystem denies read access due to permissions → an appropriate IOException, which can be wrapped if the API does not declare checked exceptions.
- A valid HTTP response returns 404 → does not mean an `IOException` occurred; handle per the HTTP/domain contract.

**Do not fabricate `new IOException("not found")` just to use `UncheckedIOException`** when the situation is not actually an I/O failure. Exception choice must reflect the **real cause** and the caller's responsibility.

## 24. Why Not Use Generic `RuntimeException` for Every Error?

You could write:

```java
throw new RuntimeException("I/O thất bại", e);
```

when `e` is an `IOException`. It is also unchecked and preserves the cause. However, `UncheckedIOException` offers several contract benefits:

- **The class name clearly expresses that this is an I/O error converted to unchecked**, not an arbitrary runtime failure.
- The specialized constructor enforces a cause of type `IOException`.
- `getCause()` returns `IOException`, helping callers classify and extract I/O details cleanly.
- Handlers can `catch (UncheckedIOException e)` instead of broadly catching `RuntimeException`.
- Code reviews can easily spot the boundary where the error policy changes.

On the other hand, if a new layer wants to represent **a different domain abstraction**, such as `ReportGenerationException` with its own error codes, a custom exception may be more suitable. There is no rule that whenever the cause is IOException you must **always** use `UncheckedIOException`.

Choose the wrapper based on the **API contract you want to publish**, not convenience alone.

## 25. Do Not Wrap Every Checked Exception in `UncheckedIOException`

`UncheckedIOException`'s constructor accepts `IOException`, not an arbitrary `Throwable`. Other checked exceptions need their own policies:

- `SQLException`: not a subclass of `IOException`.
- `ClassNotFoundException`: not a subclass of `IOException`.
- `InterruptedException`: not a subclass of `IOException`.
- Custom domain checked exceptions may be unrelated to I/O.

**Non-compiling** counterexample:

```java
SQLException sqlError = new SQLException("DB lỗi");
throw new UncheckedIOException(sqlError);
```

This is an **invalid illustrative snippet**, assuming `SQLException` and `UncheckedIOException` are imported. The compiler finds no constructor accepting `SQLException`.

If you want to convert general checked exceptions to unchecked, choose a **semantically accurate wrapper** or an API-specific error type. Do not force `new IOException(sqlError)` just to shoehorn a SQL error into the I/O category, unless you are genuinely designing an I/O abstraction with a clear reason.

In particular, `InterruptedException` carries cancellation/interruption semantics; do not treat it as an IOException and discard interruption semantics.

## 26. `UncheckedIOException` and `InterruptedIOException`

`InterruptedIOException` extends `IOException`. Thus it can serve as the cause of `UncheckedIOException` in Java's type system. However, **`InterruptedIOException` does not guarantee that the thread was interrupted** in all cases.

For example, `SocketTimeoutException extends InterruptedIOException` is used to report that a socket wait timeout has expired. **Catching a `SocketTimeoutException` and unconditionally calling `Thread.currentThread().interrupt()` is wrong** if there is no indication that the thread actually received an interrupt.

If an I/O operation was interrupted due to thread cancellation, follow that API's contract (which may require restoring the interrupt flag or propagating the cancellation signal). Wrapping in `UncheckedIOException` does not solve cancellation policy by itself.

A good design separates:

- **Timeout**: the wait budget for the operation expired.
- **Interruption**: a signal that the thread should stop.
- **I/O failure**: the read/write operation failed.
- **Domain failure**: the request did not meet business conditions.

These phenomena can interact, but must not be collapsed into a single contextless success/failure type.

## 27. `UncheckedIOException` Differs from `CompletionException` and `ExecutionException`

A callback may throw `UncheckedIOException`, but when a framework runs the callback **asynchronously**, the caller sometimes receives an additional framework wrapper.

Structural example:

```java
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(
                () -> readUnchecked("some-file"));

String value = future.join();
```

This is **illustrative code**, requiring `readUnchecked` to be defined and `CompletableFuture` imported. If the callback throws `UncheckedIOException`:

- `join()` can report the error as `CompletionException`, whose cause is the callback's error per the future contract.
- `Future.get()` on a failed task reports `ExecutionException`.
- The outer wrapper **is not proof that the original cause was lost**.
- The handler may need to inspect **multiple cause layers** if the failure-classification policy sits at the asynchronous boundary.
- Do not assume all frameworks use the same wrapper, cause ordering, or logging behavior.

Do not catch `CompletionException` and return a default value without inspecting the cause and recovery policy.

## 28. Java 17 Example: Exception Wrapped Through `CompletableFuture.join`

Save **`AsyncUncheckedIOExceptionDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class AsyncUncheckedIOExceptionDemo {
    static String read() {
        try {
            throw new IOException("Không đọc được payload");
        } catch (IOException e) {
            throw new UncheckedIOException(
                    "Callback I/O thất bại", e);
        }
    }

    public static void main(String[] args) {
        CompletableFuture<String> future =
                CompletableFuture.supplyAsync(
                        AsyncUncheckedIOExceptionDemo::read);

        try {
            future.join();
        } catch (CompletionException e) {
            Throwable wrapper = e.getCause();
            System.out.println("Async cause type: "
                    + wrapper.getClass().getSimpleName());

            if (wrapper instanceof UncheckedIOException io) {
                System.out.println("I/O cause: "
                        + io.getCause().getMessage());
            }
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 AsyncUncheckedIOExceptionDemo.java
java AsyncUncheckedIOExceptionDemo
```

**Exact stdout** on Java 17 for a task with the declared behavior:

```text
Async cause type: UncheckedIOException
I/O cause: Không đọc được payload
```

The example does not depend on real file access or task completion timing; `join()` waits for the result. It demonstrates two wrapping layers: `CompletionException -> UncheckedIOException -> IOException`.

In production code, you need cancellation policies, timeouts, and executor shutdown when managing your own executor. The example uses the default common pool solely to demonstrate how errors are observed.

## 29. Catch at the Right Layer: Not Just `catch (IOException)`

When an API propagates `UncheckedIOException`, this handler:

```java
try {
    runPipeline();
} catch (IOException e) {
    handleIoError(e);
}
```

is a **counterexample of a wrong expectation** (helper methods undefined). Because `UncheckedIOException` does not extend `IOException`, the handler above **does not** catch that wrapper. Moreover, if nothing inside `try` is declared to throw checked `IOException`, Java may report an **invalid checked IOException catch**.

Appropriate form when code can propagate both:

```java
try {
    runOperation();
} catch (UncheckedIOException e) {
    handleIoError(e.getCause());
} catch (IOException e) {
    handleIoError(e);
}
```

This is **illustrative skeleton code**; `runOperation` needs a signature allowing checked IOException for the second branch to be valid. Catching both classes depends on the processing path's contract.

More importantly: **do not force every layer to catch both**. If an API publishes one consistent type, handle that type at the responsible boundary.

## 30. Do Not Catch `UncheckedIOException` to Return Fake Success

An anti-pattern:

```java
try {
    return files.stream().map(uncheckedReader).toList();
} catch (UncheckedIOException ignored) {
    return List.of();
}
```

This is **illustrative skeleton code**, without complete variables/methods. If reading required files, an error reading the second file cannot turn into an "empty output list" that the caller believes is a success.

Better options:

1. **Fail the whole operation** if all items are required.
2. **Collect per-element results** in a structured success/error form if the system allows partial success.
3. **Bounded retry** at the right layer when safe and the cause is recoverable.
4. **Fallback** only when genuinely valid backup data exists and the contract explicitly states it.
5. **Record and report failure** at the communication layer instead of silently swallowing it.

Especially with Stream pipelines that have side effects, elements before the error may have already been processed. Catching the exception does not undo changes that already occurred.

## 31. Retrying Must Consider the I/O Operation and Idempotency

Seeing `UncheckedIOException` does not mean you should retry immediately. This type only states that **an IOException was converted to unchecked**, not that the cause is definitely transient.

You need to determine:

- Did the error come from reading a file, writing a file, HTTP, a socket, storage, or a remote mount?
- Was **partial** data already written or sent?
- Could the server-side request have committed while the response was lost?
- Is the operation **idempotent** or does it have a request ID preventing duplicate execution?
- Are there resources that need closing or pipeline state that cannot be reused?
- What are the retry count limit, backoff, and overall deadline?
- Is the error due to a wrong path/permissions/configuration, or a transient interruption?

Examples:

- Reading an immutable file can be retried in a controlled way if the system and data allow it.
- Debiting money or creating an order over the network requires an **idempotency key / status lookup** before retrying.
- A non-existent file due to a user-supplied wrong path needs an appropriate response, not infinite retries.
- An IOException due to a full disk usually requires resource intervention, not rapid repetition.

**The wrapper does not encode a retry policy.** Callers should not infer too much from the `UncheckedIOException` type alone.

## 32. Try-with-resources, Primary, and Suppressed Exceptions

A callback performing I/O may use a resource:

```java
try (Reader reader = openReader()) {
    consume(reader);
} catch (IOException e) {
    throw new UncheckedIOException(
            "Đọc hoặc đóng Reader thất bại", e);
}
```

This is **illustrative code**, requiring `openReader()`, `consume`, `Reader`, and the corresponding imports.

If `consume` throws `IOException`, and then `reader.close()` also throws, try-with-resources can attach the close error to **`e.getSuppressed()`** of the primary error. When wrapped in `UncheckedIOException`, suppressed exceptions **remain on the cause** unless you explicitly create/move a different relationship.

Distinguish:

- `wrapper.getCause()` is the wrapped IOException.
- `wrapper.getSuppressed()` is the list of suppressed exceptions attached **directly** to the wrapper; it may be empty.
- `wrapper.getCause().getSuppressed()` may contain cleanup errors from try-with-resources prior to wrapping.

Do not turn every suppressed exception into a new primary error that loses the original cause. When logging, prefer passing the exception object to the logger so the full cause/suppressed/stack trace is displayed if supported.

## 33. Java 17 Example: Inspecting Suppressed Exceptions on the Cause

Save **`SuppressedIoWrapperDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;

public class SuppressedIoWrapperDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("Lỗi đóng tài nguyên");
        }
    }

    static void perform() {
        try (Resource resource = new Resource()) {
            throw new IOException("Lỗi xử lý chính");
        } catch (IOException e) {
            throw new UncheckedIOException(
                    "Xử lý tài nguyên thất bại", e);
        }
    }

    public static void main(String[] args) {
        try {
            perform();
        } catch (UncheckedIOException e) {
            System.out.println("Cause: "
                    + e.getCause().getMessage());
            System.out.println("Suppressed on cause: "
                    + e.getCause().getSuppressed().length);
            System.out.println("Suppressed message: "
                    + e.getCause().getSuppressed()[0].getMessage());
            System.out.println("Suppressed on wrapper: "
                    + e.getSuppressed().length);
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 SuppressedIoWrapperDemo.java
java SuppressedIoWrapperDemo
```

**Exact stdout:**

```text
Cause: Lỗi xử lý chính
Suppressed on cause: 1
Suppressed message: Lỗi đóng tài nguyên
Suppressed on wrapper: 0
```

Key takeaway: **preserving the cause** also preserves the suppressed list on the original exception. However, suppressed exceptions do not automatically "move" onto the wrapper, because they are two different objects.

This pattern uses a custom `AutoCloseable` solely to demonstrate exception structure, without depending on the filesystem or networking.

## 34. Do Not Re-Wrap Already Unchecked Errors Without Value

If `Function.apply` internally throws `UncheckedIOException`, an adapter that only catches `IOException` will **not re-catch** that wrapper:

```java
try {
    return function.apply(value);
} catch (IOException e) {
    throw new UncheckedIOException(e);
}
```

This is **skeleton code**, with `function.apply` declaring checked IOException. An `UncheckedIOException` escaping from inside `function.apply` passes straight through the `catch (IOException)` handler without extra wrapping, because it is on an unchecked sibling branch.

If you broadly catch `catch (Exception e)` and do `new RuntimeException(e)`, you can create useless nested wrapper chains and accidentally catch programming bugs (`NullPointerException`, `IllegalStateException`). Limit the catch to **only the checked IOException** that the adapter needs to convert.

This is also why specific handlers should be placed at appropriate boundaries: to avoid losing information and avoid redundant wrapping that complicates stack trace analysis.

## 35. Method References Are Still Bound by `throws`

A method reference to `Files.readString` is **not** directly compatible with `Function<Path,String>`. Writing:

```java
Function<Path, String> direct = Files::readString;
```

is a **non-compiling counterexample**. There is no automatic conversion just because `::` is used.

Conversely:

```java
IoFunction<Path, String> checked = Files::readString;
Function<Path, String> adapted = unchecked(checked);
```

is an **illustrative snippet** assuming `IoFunction` and the `unchecked` adapter as defined earlier. The method reference is valid in the first step because the target SAM declares `throws IOException`; the second step intentionally changes the contract to `Function`.

If someone adds `throws IOException` to the method containing `Function<Path,String> direct = Files::readString;`, the compiler still rejects it because the `Function.apply` SAM has not changed.

## 36. You Can Turn Errors into Results Instead of Exceptions

Not every pipeline with I/O should halt completely when one element fails. For tasks processing a list of files, sometimes the requirement is to **keep both successes and per-file errors**.

You can model this with records or a sealed hierarchy, such as:

```java
sealed interface ReadResult permits ReadSuccess, ReadFailure {
}

record ReadSuccess(String file, String content)
        implements ReadResult {
}

record ReadFailure(String file, String reason)
        implements ReadResult {
}
```

These are **illustrative Java 17 types**, without `main`. A reading method can catch `IOException` and return `ReadFailure` instead of throwing a wrapper, when that is an **accepted business branch**.

Advantages:

- The pipeline can finish and collect errors **per element**.
- Callers do not have to catch a generic exception to know which file failed.
- Partial success can be reported transparently.
- Structured results do not rely on exception messages as classification codes.

Disadvantage: code must handle multiple result variants; if the entire operation must fail immediately when a required file cannot be read, a wrapper may still be simpler and more accurate.

**Choose based on task semantics**, not a desire to keep the pipeline "pretty" at all costs.

## 37. Comparing Four Ways to Represent I/O Errors

| Approach | Java contract | When appropriate | Risks |
| --- | --- | --- | --- |
| `throws IOException` | Checked, caller catch/declare | Owned API allows checked I/O | Hard to use directly with standard `Function`/`Consumer` |
| `UncheckedIOException` | Unchecked but cause must be IOException | Callback disallows checked `throws`, need clear I/O error propagation | Callers may overlook it if unaware of the contract |
| Custom domain exception | Checked or unchecked depending on chosen superclass | Want to report errors in business/abstraction-layer terms | Easy to over-wrap or lose cause if poorly designed |
| Result type (`Success/Failure`) | Structured return data | Errors are an expected branch, partial success needed | Callers must inspect/route result states |

Some practical decisions:

- A library API exposing data from files where callers should supply their own fallback → may keep checked `IOException`.
- A mapper in a stream with an existing `Function` contract → use an `UncheckedIOException` adapter if fail-fast makes sense.
- Batch processing all files even if some fail → a `ReadResult` type may fit well.
- A domain API that should not expose filesystem details → custom domain exception with a clear `cause`.

There is no single best choice for every project.

## 38. Testing `UncheckedIOException` Properly

A test should verify not only "an exception was thrown" but also:

1. **Correct wrapper type:** `UncheckedIOException`.
2. **Exact cause object or expected IOException subtype:** do not lose the original exception.
3. **Appropriate message/context:** no sensitive data leaked, sufficient for diagnostics.
4. **Errors are not swallowed:** the task fails according to policy.
5. **Lazy stream:** the exception occurs when the callback actually runs, not by default upon pipeline creation.
6. **Partial results / side effects:** do not assume rollback.
7. **Resources are closed** even when the callback throws.
8. **No infinite retries** or duplicate execution for operations with side effects.
9. **Other runtime types are not mis-wrapped**: e.g., `IllegalArgumentException` from validation should not turn into an I/O error.
10. **Asynchronous boundaries preserve the cause chain** if run in a future/executor.

Use synthetic tests throwing `IOException` to test adapters. Testing directly against file permissions or networking can be flaky; separate integration tests should verify real interactions and resources.

## 39. Java 17 Example: Self-Checking Cause Preservation and Other Runtime Exceptions

Save **`UncheckedIOExceptionAssertionsDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.function.Function;

public class UncheckedIOExceptionAssertionsDemo {
    @FunctionalInterface
    interface IoFunction<T, R> {
        R apply(T input) throws IOException;
    }

    static <T, R> Function<T, R> unchecked(
            IoFunction<T, R> fn) {
        return value -> {
            try {
                return fn.apply(value);
            } catch (IOException e) {
                throw new UncheckedIOException("I/O failed", e);
            }
        };
    }

    public static void main(String[] args) {
        IOException source = new IOException("root");
        Function<String, String> failIo =
                unchecked(value -> { throw source; });

        try {
            failIo.apply("x");
            throw new AssertionError("Thiếu wrapper");
        } catch (UncheckedIOException e) {
            if (e.getCause() != source) {
                throw new AssertionError("Cause không còn cùng object");
            }
            System.out.println("PASS same cause");
        }

        Function<String, String> failValidation =
                unchecked(value -> {
                    throw new IllegalArgumentException("bad argument");
                });

        try {
            failValidation.apply("x");
            throw new AssertionError("Thiếu validation error");
        } catch (IllegalArgumentException e) {
            System.out.println("PASS runtime unchanged");
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 UncheckedIOExceptionAssertionsDemo.java
java UncheckedIOExceptionAssertionsDemo
```

**Exact stdout:**

```text
PASS same cause
PASS runtime unchanged
```

The program proves:

- The adapter keeps the exact original `IOException` object in `getCause()`.
- The handler only catches `IOException`, so it **does not turn `IllegalArgumentException` into an I/O error**.
- The test uses `AssertionError` to fail explicitly; it does not depend on the `-ea` flag.

These are two important checks if you plan to package the adapter as a shared utility.

## 40. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "`UncheckedIOException` is a subclass of `IOException`." | False. It is a subclass of `RuntimeException` and holds `IOException` as its cause. |
| "With `UncheckedIOException`, every `Files.readString` is unchecked." | False. `Files.readString` still declares checked `IOException`. |
| "`Function.apply` automatically understands and converts IOException." | No. The callback must catch/convert it or use a different contract. |
| "Wrapping Stream creation in catch IOException fixes an incompatible method reference." | No. Checked exceptions are part of the SAM; you must change the callback. |
| "`UncheckedIOException` has already handled the error." | False. It only changes how the exception propagates. |
| "`catch (IOException)` also catches `UncheckedIOException`." | No; the two types are in different hierarchy branches. |
| "`UncheckedIOException` accepts `SQLException` as a cause." | No. Its specialized constructor requires `IOException`. |
| "All I/O errors can be safely retried." | No. There may already be side effects or permanent configuration errors. |
| "Adding `throws IOException` to the method containing the lambda lets `Function.apply` throw checked IOException." | False. `Function`'s SAM does not change. |
| "`Files.lines` only has unchecked errors." | False. Opening the stream can throw checked `IOException`; lazy processing can throw `UncheckedIOException`. |
| "A Stream pipeline runs all mappers immediately upon creation." | No. Intermediate operations are generally lazy. |
| "Data written before an error is rolled back by the Stream." | No. Streams do not provide transactions/rollback for side effects. |
| "After `UncheckedIOException`, any resource can still be safely reused." | You cannot assume that; check the protocol and resource state. |
| "Catching `Exception` and wrapping in `RuntimeException` is equivalent." | It can catch programming bugs, lose I/O semantics, and create redundant wrappers. |
| "`UncheckedIOException.getCause()` only returns generic `Throwable`." | Java declares an override returning `IOException`. |
| "Every wrapper automatically moves the cause's suppressed exceptions onto the wrapper itself." | No. Suppressed exceptions belong to each `Throwable` object and must be inspected at the right layer. |
| "Because `SocketTimeoutException extends InterruptedIOException`, you must set the interrupt flag." | Not merely because of a timeout; you need to know the real cancellation contract. |
| "`join()` returns `UncheckedIOException` directly in every Future." | No. `CompletableFuture` can report `CompletionException` with the corresponding cause. |
| "If using `UncheckedIOException`, Javadoc is unnecessary." | False. Callers still need to know the contract, error timing, and recovery policy. |
| "Every data-not-found branch should throw `UncheckedIOException`." | No. Missing business data may not be an I/O error. |

## 41. Self-Check Questions

**1. Is `UncheckedIOException` checked or unchecked?**  
Unchecked, because it extends `RuntimeException`.

**2. Is `UncheckedIOException extends IOException` true?**  
No. It holds an `IOException` as its `cause`.

**3. Why does `Function<Path,String> f = Files::readString` fail to compile?**  
`Files.readString` declares checked `IOException`, whereas `Function.apply` does not allow checked `throws`.

**4. What does wrapping a lambda in `try/catch(IOException)` and throwing `UncheckedIOException` change?**  
The checked IOException no longer escapes the SAM; instead, an unchecked wrapper is thrown when I/O fails.

**5. What is the static return type of `UncheckedIOException.getCause()`?**  
`IOException`.

**6. Can you pass `SQLException` directly to the `UncheckedIOException` constructor?**  
No, because `SQLException` is not an `IOException`.

**7. What API should you consider if you want a callback to keep checked IOException?**  
A custom SAM with `throws IOException`, or an existing API that allows checked exceptions such as `Callable.call`.

**8. Does `Stream.map` always execute immediately when you write `stream.map(fn)`?**  
No. Intermediate operations are generally lazy.

**9. What kind of error can `Files.lines` throw when opening a file?**  
Checked `IOException`.

**10. While lazily consuming a Stream from `Files.lines`, what type can an I/O read error appear as?**  
`UncheckedIOException`.

**11. When calling `BufferedReader.readLine()` directly, does Java automatically wrap it into `UncheckedIOException`?**  
No. `readLine` directly declares checked `IOException`.

**12. Why must you close the stream from `Files.lines`?**  
It may hold file resources; use try-with-resources per the contract.

**13. If a stream has processed three elements and the fourth throws the wrapper, are prior side effects automatically rolled back?**  
No.

**14. Why shouldn't you retry a transaction-creation call based solely on the `UncheckedIOException` type?**  
Because the command may have already executed on the server or been partially written; you need idempotency, status checks, and a retry policy.

**15. In `CompletableFuture.join()`, what wrapper can enclose an error from the callback?**  
`CompletionException`.

**16. Should you preserve the original `IOException` object as the cause when converting errors?**  
Yes, to preserve the error type, message, stack trace, and the cause's suppressed exceptions.

**17. After wrapping a primary error that already has suppressed exceptions, where should you look for them?**  
Typically in `wrapped.getCause().getSuppressed()`, because suppressed exceptions do not automatically move to the wrapper.

**18. If a lambda throws `IllegalArgumentException`, does an adapter that only catches `IOException` convert it to `UncheckedIOException`?**  
No, because `IllegalArgumentException` is not an `IOException`.

**19. Does using `UncheckedIOException` automatically create a deadline or timeout for file reads?**  
No. It has nothing to do with setting deadlines.

**20. If an item does not exist in business terms, are you required to use `UncheckedIOException`?**  
No. It is only appropriate when there is a real I/O error and the contract wants unchecked propagation.

**21. Can you choose a `ReadResult` success/failure type instead of an exception in batch processing?**  
Yes, when you need per-element results or failure is an expected branch.

**22. Can `Callable.call() throws Exception` reference a method with `throws IOException`?**  
Yes, because `IOException extends Exception`.

**23. Which constructor creates `UncheckedIOException` with additional context?**  
`new UncheckedIOException("Mô tả", ioException)`.

**24. Why shouldn't you broadly catch `RuntimeException` and treat every error as "I/O"?**  
Because it could be an argument error, state error, NPE, or another bug.

## 42. Code Review Checklist for Using `UncheckedIOException`

Before shipping to production:

1. **Confirm the root error is genuinely an IOException**, not a business error or another checked exception.
2. **Identify the SAM/API restricting checked throws**: Function, Consumer, Supplier, Runnable, Stream?
3. **Can it be replaced with a custom SAM having `throws IOException`?** If you own the API, consider the checked option.
4. **Do you need fail-fast or partial results?** Consider a result type if needed.
5. **Catch only the `IOException` scope**, rather than catching `Exception` and misattributing semantics.
6. **Use the cause-preserving constructor**: `new UncheckedIOException(message, e)`.
7. **The message adds useful context** without leaking sensitive data.
8. **Know where the exception occurs**: when creating the source, building the pipeline, or running the terminal operation?
9. **Catch the wrapper at the right boundary**; `catch(IOException)` will not catch the wrapper.
10. **If using `Files.lines`/`list`/`walk`**, are streams/resources managed with try-with-resources?
11. **If using `BufferedReader.lines`**, who owns and closes the Reader?
12. **If the callback has side effects**, have partial writes and rollback been considered?
13. **Do not retry blindly** just because the error mentions "I/O".
14. **For requests with side effects**, is there an idempotency key or confirmation state?
15. **If running asynchronously**, are `Future`/`CompletableFuture` wrappers handled per contract?
16. **Is the `Throwable` logged along with cause/suppressed**, rather than storing only the message?
17. **Are there tests verifying exact cause object preservation**, correct subtype, and that other runtime exceptions are not mis-caught?
18. **Are there tests for the timing of lazy stream errors?**
19. **Are any resources left unclosed after an exception?** Check try-with-resources and cleanup.
20. **Is there a risk of unnecessary multi-layer wrapper nesting?**
21. **Is there a separate cancellation/interrupt policy** for I/O timeouts?
22. **Is the unchecked exception documented** in the API/adapter?
23. **Have you avoided turning failures into empty lists or fake successes?**
24. **If changing a public API contract from checked to unchecked**, have callers, catch blocks, tests, and compatibility been reviewed?

## 43. Conclusion

`UncheckedIOException` is **the bridge between checked `IOException` and Java APIs that do not allow callbacks to throw checked exceptions**. It is a subclass of `RuntimeException`, preserves the `IOException` cause in `getCause()`, and is especially useful with lambdas, method-reference adapters, `Function`, `Consumer`, the Stream API, or lazily reading APIs such as `Files.lines` and `BufferedReader.lines`.

What must be distinguished is **propagating an error** versus **handling an error**. Wrapping `IOException` in `UncheckedIOException` lets code pass through a callback signature without checked `throws`; it **does not recover from I/O failures, does not make retries safe, does not close resources for you, and does not roll back side effects**. Errors must still be reported or handled at a responsible layer.

When your API can declare checked `IOException` and callers need explicit handling rights, keeping the checked exception or using a custom SAM with `throws IOException` may be better. If a failure is an expected business branch or partial success is needed, a stateful result type may be more appropriate. Only convert to unchecked **intentionally, preserving the cause, choosing a sensible catch boundary, and testing the failure policy**.
