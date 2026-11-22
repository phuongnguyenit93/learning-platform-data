# Checked exceptions must be compatible with the target type's `throws` in Java lambdas

## 1. The core problem

Lambdas and method references in Java do not have a standalone function type: they are compiled against a **target functional interface** (target type). That interface's functional abstract method, commonly called the **SAM** (*single abstract method*), determines the parameters, the return type, **and which checked exceptions are allowed to escape**.

For example, **Files.readString(Path)** reads a file's contents and declares **throws IOException**. Meanwhile, **Function<Path,String>** uses the SAM **String apply(Path)**, which declares no checked exceptions. Therefore, the following line **does not compile**:

~~~java
// INTENTIONALLY DOES NOT COMPILE: Function.apply does not declare IOException.
Function<Path, String> read = path -> Files.readString(path);
~~~

This illustration assumes **java.nio.file.Files**, **java.nio.file.Path**, and **java.util.function.Function** are imported. The error is not that a lambda is forbidden from calling an I/O API, but that **IOException can escape the lambda body without being in the SAM's throws contract**.

If you define your own functional interface whose functional method declares **throws IOException**, the same behavior is valid:

~~~java
@FunctionalInterface
interface TextLoader {
    String load(Path path) throws IOException;
}

TextLoader loader = Files::readString;
~~~

This is an **illustrative code snippet** requiring imports for **IOException**, **Files**, and **Path**, not a standalone program. **Files::readString** also works because the referenced method's signature matches **TextLoader.load(Path)** and the exception is permitted.

**Rule of thumb:** A checked exception can escape a lambda or method reference **only if it matches the target SAM's throws clause**, or it must be **caught and handled inside the body**. Having the enclosing method that contains the lambda assignment declare throws **does not widen** the SAM's throws clause.

## 2. How do checked and unchecked exceptions differ?

Java categorizes the main throwables into:

- **Checked exceptions:** subclasses of **Exception** that are not under **RuntimeException** (for example, **IOException**, **SQLException**, **ParseException**). The compiler requires catching or declaring them according to the relevant contract.
- **Unchecked exceptions:** **RuntimeException** and its subclasses (for example, **IllegalArgumentException**, **NullPointerException**, **UncheckedIOException**), along with **Error** and its subclasses. They do not need to be listed in throws for code to compile.
- **Error:** such as **OutOfMemoryError** or **StackOverflowError**, usually reflecting environment or resource issues; do not use Error as a substitute for normal business error reporting.

**throws** in a method signature describes checked exceptions that may propagate to the caller. **throw** is the statement that actually throws a Throwable object:

~~~java
String load(Path path) throws IOException {
    if (path == null) {
        throw new IllegalArgumentException("path required");
    }
    return Files.readString(path);
}
~~~

This is an **illustrative method**, not a standalone program. In it, **IllegalArgumentException** is unchecked so it does not need to be declared; **IOException** coming from Files.readString is checked and is allowed to escape thanks to **throws IOException**.

**Do not confuse:** A lambda can throw a **RuntimeException** without the SAM declaring throws. Compile-time freedom **does not** mean you should arbitrarily convert every error into an unchecked exception.

## 3. The target type determines the allowed exception scope

Consider common functional types:

| Target functional interface | SAM | Can checked exceptions escape directly? |
| --- | --- | --- |
| **Runnable** | **void run()** | Declares no checked exceptions |
| **Supplier<T>** | **T get()** | Declares no checked exceptions |
| **Function<T,R>** | **R apply(T)** | Declares no checked exceptions |
| **Consumer<T>** | **void accept(T)** | Declares no checked exceptions |
| **Predicate<T>** | **boolean test(T)** | Declares no checked exceptions |
| **Callable<V>** | **V call() throws Exception** | Allows checked Exception or a compatible subclass |
| Custom **TextLoader** | **String load(Path) throws IOException** | Allows IOException or a compatible subclass |

Standard interfaces in **java.util.function** do not declare checked exceptions in their primary SAM; this matters when passing callbacks into **Stream.map/filter/forEach**, **Optional.map**, or APIs that accept Function, Consumer, or Supplier.

Example of the difference:

~~~java
// Valid: Callable.call declares throws Exception.
Callable<String> operation = () -> Files.readString(path);

// Invalid: Supplier.get does not declare IOException.
// Supplier<String> operation2 = () -> Files.readString(path);
~~~

This illustration requires importing **Callable**, **Supplier**, and **Files**, and having a **path** variable of type Path. It is not two standalone declarations ready to compile in the same context. **Callable.call()** declares **throws Exception**, so IOException is a compatible subclass. When **calling operation.call()**, the caller still has to catch or declare **Exception** according to the static type Callable, even if the concrete lambda can only throw IOException.

### 3.1. A more specific body cannot alter the SAM contract

Suppose a lambda is assigned to **Function<Path,String>**:

~~~java
Function<Path, String> f = path -> {
    return Files.readString(path);
};
~~~

This is an **intentionally non-compiling example**. Adding braces and **return** does not fix the checked exception error. The String return type is compatible, but **IOException is still not allowed to escape through Function.apply**.

Nor can you fix it by declaring the method that creates the lambda as follows:

~~~java
// INTENTIONALLY DOES NOT COMPILE:
static Function<Path, String> makeReader() throws IOException {
    return path -> Files.readString(path);
}
~~~

**throws IOException** on **makeReader** only applies to executing **makeReader** itself; it does not make **Function.apply** declare IOException. Reading the file happens inside the lambda and executes later, so the compiler still checks the throws contract of **Function.apply**.

Similarly, adding **throws IOException** to the **main** method does not allow a lambda assigned to Function to throw an unhandled IOException.

## 4. Reading the direction of exception compatibility correctly

Given the SAM:

~~~java
@FunctionalInterface
interface IoAction {
    void run() throws IOException;
}
~~~

The lambda body is **allowed** to throw:

- **IOException**, or a more specific subclass such as **FileNotFoundException**.
- **Unchecked exceptions** such as **IllegalStateException** without any extra declaration.

However, it is **not allowed** to let a broader or unrelated checked exception escape if the SAM does not declare it:

~~~java
// INTENTIONALLY DOES NOT COMPILE if the method can throw a broader Exception:
IoAction bad = () -> {
    throw new Exception("wider checked exception");
};
~~~

The two snippets above illustrate the rule. **Exception** is a supertype of **IOException**, not a subclass, so it is not within the set of checked exceptions permitted by **throws IOException**.

Conversely, an interface whose SAM has **throws Exception** allows the lambda to throw IOException. The rule mirrors method overriding in Java: an implementation cannot arbitrarily widen the checked exceptions promised to callers of the supertype.

**Remember the direction of compatibility:** "SAM declares IOException" allows **FileNotFoundException**; "SAM declares FileNotFoundException" **does not** allow an arbitrary IOException.

If a lambda has multiple branches throwing multiple independent checked exceptions, the SAM must declare types covering every exception that can escape; or the lambda must catch and translate some of them before returning control.

## 5. Four common handling approaches

### 5.1. Approach A: Catch and handle directly inside the lambda

When an API requires **Function<T,R>**, you can catch IOException and choose an appropriate policy:

~~~java
Function<Path, String> reader = path -> {
    try {
        return Files.readString(path);
    } catch (IOException cause) {
        return "[unavailable]";
    }
};
~~~

This illustration requires importing **Function**, **Files**, **Path**, and **IOException**. It **compiles** because IOException does not escape the lambda.

However, **returning a default value** is only right if the system explicitly defines that "unable to read the file" can be treated as "no content". In most business logic, silently swallowing errors can lead to corrupted data that is hard to detect. If the error matters, do not use this pattern without a clear decision on semantics.

Variations include logging and skipping, returning an Optional, or filtering out broken records. These choices change the business contract: **catching an exception** does not by itself tell you what should happen next.

### 5.2. Approach B: Wrap IOException in UncheckedIOException

If the API accepts Function and a file-reading failure **must fail** the transformation, you can convert the checked IOException into **UncheckedIOException**:

~~~java
Function<Path, String> reader = path -> {
    try {
        return Files.readString(path);
    } catch (IOException cause) {
        throw new UncheckedIOException("Cannot read " + path, cause);
    }
};
~~~

This illustration requires importing **java.io.UncheckedIOException** along with the types already used. **UncheckedIOException** extends RuntimeException, so **Function.apply** does not need to declare it. The **cause** is preserved so error handlers know the original I/O cause.

This does not make a "checked exception automatically succeed": the failure still occurs when the lambda runs, but it is represented as unchecked and can pass through standard APIs.

**Do not catch overly broad Exception to force everything into RuntimeException** without a defined policy. That easily ends up wrapping programming bugs and invariant violations as well.

### 5.3. Approach C: Create a custom functional interface with matching throws

When the callback has an explicit I/O contract, create a SAM with the checked exception declared:

~~~java
@FunctionalInterface
interface TextLoader {
    String load(Path path) throws IOException;
}
~~~

You can pass a lambda:

~~~java
TextLoader loader = path -> Files.readString(path);
~~~

or a method reference:

~~~java
TextLoader loader = Files::readString;
~~~

These illustrations require importing **Path**, **Files**, and **IOException** and belong in their own file or an appropriate context. The advantage is that callers reading **load(...) throws IOException** see the failure mode they must handle. The drawback: a TextLoader object **is not automatically a Function<Path,String>**; **Stream.map** still requires Function and does not directly accept the new interface.

Use this approach when I/O errors are an important part of the **API contract**, especially at boundaries for reading files, connections, data transfer, or resource access.

### 5.4. Approach D: Write an explicit adapter between a throwing type and Function

Create an **IoFunction<T,R>** whose SAM declares IOException, then convert it into a Function using a wrapping policy. An adapter avoids repeating the same try/catch across every pipeline, but it should be named and documented so callers know checked IOException will surface as UncheckedIOException.

~~~java
@FunctionalInterface
interface IoFunction<T, R> {
    R apply(T value) throws IOException;
}

static <T, R> Function<T, R> unchecked(IoFunction<T, R> action) {
    Objects.requireNonNull(action, "action");
    return value -> {
        try {
            return action.apply(value);
        } catch (IOException cause) {
            throw new UncheckedIOException(cause);
        }
    };
}
~~~

This is an **illustrative API snippet**, assuming the **unchecked** method is placed in a class with **Objects**, **Function**, **IOException**, and **UncheckedIOException** imported. It is not a standalone Java program. Inside the adapter, IOException is caught, so the returned lambda satisfies Function.apply.

**Do not confuse:** An adapter converts types according to an **exception policy**; it does not change the **throws** signature of Function.

## 6. Runnable Java 17 example: the same I/O through two contracts

Create **CheckedLambdaDemo.java**:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.function.Function;

@FunctionalInterface
interface TextLoader {
    String load(Path path) throws IOException;
}

public class CheckedLambdaDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("checked-lambda-", ".txt");
        try {
            Files.writeString(file, "Xin chào\n");

            TextLoader checked = Files::readString;

            Function<Path, String> wrapped = path -> {
                try {
                    return Files.readString(path);
                } catch (IOException cause) {
                    throw new UncheckedIOException(cause);
                }
            };

            System.out.println("checked: "
                    + checked.load(file).strip());
            System.out.println("wrapped: "
                    + wrapped.apply(file).strip());
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Compile and run with **JDK 17 or later**:

~~~bash
javac -encoding UTF-8 CheckedLambdaDemo.java
java CheckedLambdaDemo
~~~

Stdout in an environment with permission to create/read/delete temporary files:

~~~text
checked: Xin chào
wrapped: Xin chào
~~~

**Boundary-by-boundary analysis:**

1. **Files.createTempFile** and **Files.writeString** can throw IOException in main; main declares **throws IOException**, so they are allowed to propagate to the caller.
2. **TextLoader.checked** uses the method reference **Files::readString**. The SAM **load(Path) throws IOException** permits the corresponding exception.
3. **Function<Path,String> wrapped** declares no checked exceptions. The lambda catches IOException and throws **UncheckedIOException**, so the Function contract is respected.
4. **checked.load(file)** calls a SAM that declares a checked exception; main already has a matching **throws IOException**.
5. **wrapped.apply(file)** does not require compile-time checked exception handling; if an I/O error occurs, UncheckedIOException propagates.
6. **finally** deletes the temporary file even if the read fails; if deletion also encounters an IOException, that error can propagate out of main.

Stdout does not depend on the temporary file name because the program only prints the written contents. **The example code does not mean IOException cannot happen**; filesystem permissions remain a required environmental condition.

## 7. Checked exceptions and Streams: pipelines do not widen throws

Common Stream APIs accept standard functional interfaces:

~~~java
<R> Stream<R> map(Function<? super T, ? extends R> mapper);
Stream<T> filter(Predicate<? super T> predicate);
void forEach(Consumer<? super T> action);
~~~

These are **abbreviated descriptive signatures**, not complete methods to copy into a program. Because **Function**, **Predicate**, and **Consumer** do not declare IOException, the snippet below **does not compile**:

~~~java
// INTENTIONALLY DOES NOT COMPILE:
List<String> contents = paths.stream()
        .map(Files::readString)
        .toList();
~~~

Assume **paths** is a List<Path> and the relevant classes are imported. A method reference gets no special exemption: it must also be compatible with the target SAM's **throws**. Since **Files::readString** has a checked IOException, **Stream.map** does not catch it automatically.

**How to solve it:** translate IOException according to a policy (for example, UncheckedIOException), or handle I/O before/after the pipeline using APIs with appropriate throws. If per-element errors need to be kept alongside data rather than halting the whole stream, design a result type such as **ReadResult(content, error)** with a clear success/failure contract.

### 7.1. Lazy evaluation changes when errors appear

When you write:

~~~java
Stream<String> pipeline = paths.stream().map(unchecked(Files::readString));
~~~

this is an **illustrative snippet**, assuming the **unchecked** adapter is defined and necessary imports are present. Creating the pipeline normally **does not read any files yet** because map is an intermediate operation. An IOException wrapped as UncheckedIOException will surface **when a terminal operation actually requests data**, such as **toList()**, not when the pipeline is declared.

This has two consequences:

- If the stream is never consumed, the I/O work inside the mapper may never run.
- When reading data has side effects or fails partway through, some elements may already have been processed before the exception is thrown. Do not assume a failed pipeline means all work is rolled back.

With parallel streams, exceptions can occur on another execution thread, and the order/count of side effects should not be relied upon as a business contract. Keep data pipelines simple and separate I/O responsibilities when that gives better error control.

## 8. Java 17 example: IoFunction adapter and Stream.map

Create **CheckedStreamDemo.java**:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Stream;

@FunctionalInterface
interface IoFunction<T, R> {
    R apply(T input) throws IOException;
}

public class CheckedStreamDemo {
    static <T, R> Function<T, R> unchecked(IoFunction<T, R> action) {
        Objects.requireNonNull(action, "action");
        return value -> {
            try {
                return action.apply(value);
            } catch (IOException cause) {
                throw new UncheckedIOException(cause);
            }
        };
    }

    public static void main(String[] args) throws IOException {
        Path first = Files.createTempFile("source-a-", ".txt");
        Path second = Files.createTempFile("source-b-", ".txt");

        try {
            Files.writeString(first, "alpha\n");
            Files.writeString(second, "beta\n");

            IoFunction<Path, String> read = Files::readString;

            List<String> contents = Stream.of(first, second)
                    .map(unchecked(read))
                    .map(String::strip)
                    .toList();

            System.out.println(contents);

            IoFunction<String, String> failing = value -> {
                throw new IOException("invalid input");
            };

            try {
                unchecked(failing).apply("x");
            } catch (UncheckedIOException failure) {
                System.out.println("cause: "
                        + failure.getCause().getMessage());
            }
        } finally {
            Files.deleteIfExists(first);
            Files.deleteIfExists(second);
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 CheckedStreamDemo.java
java CheckedStreamDemo
~~~

Stdout when temporary file operations succeed:

~~~text
[alpha, beta]
cause: invalid input
~~~

**Why is this code valid?**

- **IoFunction<Path,String> read = Files::readString** is valid because the SAM declares IOException.
- **unchecked(read)** returns a **Function<Path,String>** accepted by Stream.map. Inside the Function, IOException is wrapped and thrown as UncheckedIOException.
- **Stream.of(first, second)** preserves encounter order for a sequential stream; **toList()** collects the two contents after stripping newlines.
- **failing** is an IoFunction that intentionally throws IOException; when invoked through the adapter, the program catches UncheckedIOException and retrieves the cause **IOException("invalid input")**.
- **finally** attempts to delete both files so the example leaves no temporary data behind in the normal case.

This pattern fits when the expected policy is to **stop the pipeline if data cannot be read**. If you need to continue and record failed files, a Result-style wrapper or a per-file try/catch loop may be clearer. **How you handle exceptions is a business-contract decision**, not merely a compiler-error workaround.

## 9. Callable and Runnable: direct comparison in the standard library

These two functional interfaces are easy to confuse when passing tasks:

- **Runnable.run()** returns void and **declares no checked exceptions**.
- **Callable<V>.call() throws Exception** returns V and **allows checked exceptions** (including IOException).

Therefore:

~~~java
Callable<String> checked = () -> Files.readString(path);

// INTENTIONALLY DOES NOT COMPILE:
// Runnable cannotDirectlyRead = () -> Files.readString(path);
~~~

This illustration requires importing Callable, Runnable, Files, and Path, and having a suitable path variable. Even though the return value of Files.readString can be ignored in a Runnable, **checked IOException is still incompatible with Runnable.run**. Discarding the return value does not remove the obligation to handle checked exceptions.

A short program **CallableExample.java**:

~~~java
import java.io.IOException;
import java.util.concurrent.Callable;

public class CallableExample {
    public static void main(String[] args) {
        Callable<String> task = () -> {
            throw new IOException("offline");
        };

        try {
            task.call();
        } catch (Exception failure) {
            System.out.println(failure.getClass().getSimpleName()
                    + ": " + failure.getMessage());
        }
    }
}
~~~

Run:

~~~bash
javac CallableExample.java
java CallableExample
~~~

Stdout:

~~~text
IOException: offline
~~~

Note that **Callable.call** is declared **throws Exception**, so the caller catches **Exception** for demonstration purposes. If you submit a Callable to **ExecutorService.submit**, checked exceptions in the task are typically delivered to the result waiter via **ExecutionException** (when calling Future.get), rather than being thrown directly from submit. That is the error-reporting mechanism of Executor/Future, **not** proof that Callable ignores checked exceptions.

Similarly, **CompletableFuture.supplyAsync** accepts a Supplier, which declares no checked exceptions, so I/O inside the lambda must be handled or wrapped according to policy. When retrieving the result, CompletableFuture may report errors via CompletionException or ExecutionException depending on the retrieval method.

## 10. Lambda `throws` cannot be written on the arrow

Lambdas have no syntax for declaring their own **throws** right after the parameter list. Checked exception rules come from the target SAM:

~~~java
@FunctionalInterface
interface IoTask {
    void execute() throws IOException;
}

IoTask task = () -> {
    throw new IOException("not available");
};
~~~

This is an **illustrative snippet** requiring IOException to be imported. **There is no syntax** like **() throws IOException -> {...}** to grant checked exception permission to a lambda.

If you write a method reference **service::load**, the compiler likewise checks the checked exceptions declared by load against the SAM. Merely switching from a lambda to a method reference **does not** eliminate throws errors. A method reference to a generic or overloaded method also needs to match parameter and return types just like regular lambdas.

### 10.1. Overloads can change the target type

Suppose there are two different overloads accepting Function and IoFunction. A lambda or method reference may be compatible with both in different ways or cause ambiguity, depending on the exact signatures and context. **Do not rely solely on a lambda throwing a checked exception to always pick the right overload**. If ambiguity is possible, specify the target type up front:

~~~java
IoFunction<Path, String> checkedReader = Files::readString;
// Pass checkedReader to the overload accepting IoFunction.
~~~

This illustration assumes a suitable IoFunction is declared. Explicit naming and type declarations make APIs easier to read and reduce the risk of complex type-inference issues.

### 10.2. Generic SAMs and exceptions

You can generalize it:

~~~java
@FunctionalInterface
interface ThrowingFunction<T, R, E extends Exception> {
    R apply(T value) throws E;
}
~~~

This is an **illustrative interface declaration**. When assigned to **ThrowingFunction<Path,String,IOException>**, the compiler allows IOException; when assigned to **ThrowingFunction<Path,String,FileNotFoundException>**, the compiler only allows FileNotFoundException and its subclasses.

Generic checked exceptions are useful in internal helper libraries, but they can complicate public APIs. If you only need a file-reading operation, **TextLoader throws IOException** is easier to understand than three generic type parameters. Choose the level of abstraction based on whether it genuinely helps callers identify their error-handling obligations.

## 11. Do not swallow or lose the root cause

Some "compiler-error fixes" easily create operational bugs:

| Approach | Problem | Intentional alternative |
| --- | --- | --- |
| **catch(IOException e) { return null; }** | Can mask bad data; callers hit NPEs far from the source | Use Result/Optional if null has a clear meaning, or throw an appropriate error |
| **catch(Exception e) { return ""; }** | Collapses every kind of failure into an empty string | Catch the required exception type and define a fallback |
| **throw new RuntimeException(e.getMessage())** | Loses the original cause and stack trace | **throw new UncheckedIOException(e)** for IOException; or RuntimeException with cause |
| Declaring **throws IOException** on the method enclosing the lambda and assuming it suffices | Does not change the SAM's throws | Catch inside the lambda or use an appropriate SAM |
| Casting **(Function<T,R>)** hoping to avoid the error | A cast does not fix incompatible checked exceptions | Fix the target type or choose an adapter |
| **catch(Throwable)** to hide all errors | Can catch Error as well and make system failures hard to diagnose | Catch expected checked exceptions; handle other errors according to policy |
| Catching and silently continuing in a Stream | Can produce incomplete output without anyone noticing | Report structured errors, use controlled logging/metrics, or stop processing |

**Preserving the cause** is an important requirement when translating an error into another exception class. For example, **UncheckedIOException** holds the original IOException; code inspecting the cause can use **getCause()**, as shown in the program above.

When you want per-record error handling, a semantically rich result can be better than throwing an exception for the whole pipeline:

~~~java
record ReadResult(Path path, String text, IOException error) {
    boolean successful() {
        return error == null;
    }
}
~~~

This is an **illustrative record type**. A real design should clearly define its invariants: on success, text must be present; on failure, error must be present. Do not assume three independent fields automatically enforce that invariant. A Result structure preserves error details per data source, though it also requires callers to handle both cases.

## 12. Method reference exceptions can be harder to spot

When writing:

~~~java
TextLoader reader = Files::readString;
~~~

no throws keyword appears on the assignment line, yet the referenced method still has **throws IOException**. The compiler does not just match parameter types and return value; it also checks checked exceptions against the SAM.

Conversely:

~~~java
Function<Path, String> reader = Files::readString;
~~~

this is an **intentionally non-compiling example** (assuming the relevant imports) because Function.apply does not let IOException escape. Rewriting it as **path -> Files.readString(path)** is also invalid.

When you hit an error on a method reference, check the **source method's declaration**, the **target functional interface**, the **SAM's throws**, **overloads**, and **exceptions arising from conversions/invocations**. Do not just look at a line with **::** and assume there are no checked exceptions.

## 13. Practice testing both success and failure

A thorough test should verify both paths:

1. **Success path:** the lambda returns the expected result when there is no I/O error.
2. **Failure path:** the checked exception is declared, caught, or wrapped as the right type per contract; errors are not accidentally turned into successful results.

Cases to include:

- **TextLoader**: readable file, **load** returns the expected String.
- **TextLoader**: unreadable or missing file, caller handles IOException per contract.
- **unchecked adapter**: mock IoFunction throws IOException, caller receives **UncheckedIOException** with **getCause() instanceof IOException**.
- **Function fallback**: if there is a fallback, verify it only triggers in cases accepted by policy.
- **Stream lazy**: verify the pipeline only starts I/O when the terminal operation demands data.
- **Cleanup**: I/O resources are closed/deleted via **try-with-resources** or **finally** appropriately, even when an exception occurs.

For impure functions and mutable data, unit tests should control the filesystem, timing, and data sources. The learning programs here use temporary files so they do not depend on a fixed personal path.

### 13.1. Distinguishing compile-time from runtime

There are three distinct points in time:

~~~text
1. Compile time:
   Does the lambda/method reference have checked exceptions compatible with the SAM?
   → Incompatible: code does not compile.

2. Callback creation:
   Creates the lambda/method reference; usually has not run the I/O body yet.
   → Does not mean the file has been read successfully.

3. Invoking the callback or running the terminal operation:
   Performs I/O and may encounter IOException or UncheckedIOException.
   → Caller handles it according to the chosen contract.
~~~

Do not use a single successful run to conclude that the throws structure is well designed, and do not catch errors only where the callback is created assuming later file-reading errors will automatically be caught. Exceptions raised when executing behavior must be managed at the boundary where that behavior actually executes.

## 14. Exercises

### Exercise 1: Spot compile errors

Classify the following lines. Assume **path** is a Path and everything is imported:

~~~java
Callable<String> a = () -> Files.readString(path);
Supplier<String> b = () -> Files.readString(path);
TextLoader c = Files::readString;
Function<Path, String> d = Files::readString;
~~~

This is a **set of examples containing intentionally non-compiling lines**; do not copy the whole block into a practice file. **Answer:** a and c are valid with respect to checked exceptions; b and d are invalid because Supplier.get and Function.apply do not declare IOException.

### Exercise 2: Convert error reporting

Write a **Function<Path,String>** that reads a file, but in catch(IOException) throws **UncheckedIOException** preserving the cause. Also write a test invoking the Function with a mock IoFunction that always throws IOException and verify the root cause.

### Exercise 3: Choose the right contract

A library needs to accept a file-reading callback and callers must know it can fail with IOException. Explain why **TextLoader.load(Path) throws IOException** can be more appropriate than **Function<Path,String>**, and the drawback when using it directly in Stream.map.

### Exercise 4: Plug an adapter into a pipeline

Write **Stream.of(path1, path2).map(unchecked(Files::readString)).toList()** with an unchecked method accepting IoFunction. Explain why the exception can occur when calling **toList()**, not when constructing the pipeline.

### Exercise 5: Compare throws of supertype and interface

Create an interface with a SAM that has **throws IOException**, then try lambdas throwing FileNotFoundException, IOException, and Exception. Which ones are valid? Explain using the inheritance relationship among checked exceptions.

## 15. Takeaways

- **Lambdas and method references must obey the target SAM's throws clause**. A compatible return type **is not enough**.
- **Function, Consumer, Predicate, Supplier, and Runnable** do not let checked IOException escape directly; **Callable.call throws Exception** and a custom SAM **throws IOException** can allow it.
- **An enclosing method's throws does not widen a lambda's throws**; nor can you add throws syntax after the lambda arrow.
- When using standard APIs that disallow checked exceptions, **catch and handle**, **wrap while preserving the cause**, or build an **explicit adapter**; when the contract requires checked I/O, consider a custom functional interface.
- **Method references do not bypass exceptions**, **Stream.map does not widen throws**, and **laziness** can make errors surface only when the pipeline is consumed.
- Choose error handling based on **business semantics**, not just to "make the compiler error go away".

The core question before assigning a lambda is: **"Which checked exceptions does the target type's SAM allow to escape, and what contract will the caller use to handle them?"**