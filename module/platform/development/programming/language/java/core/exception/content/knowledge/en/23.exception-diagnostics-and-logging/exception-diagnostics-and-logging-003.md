# Finding Application Code Frames and Matching Source Lines

## 1. Goal: going from a stack trace to the exact statement in Java code

When Java throws an exception, the most useful information is usually not just the error message, but the **stack trace**: a list of execution locations (*stack frames*) attached to the exception. Each frame can indicate the class, method, source file name, and line number. The diagnostic task is to **find the frame belonging to application code**, open the exact version of the code that was running, and then match that line with its context and actual root cause.

Example of a shortened trace:

~~~text
java.lang.IllegalArgumentException: quantity must be positive
    at com.acme.orders.QuantityValidator.check(QuantityValidator.java:18)
    at com.acme.orders.OrderService.create(OrderService.java:47)
    at com.acme.orders.OrderController.submit(OrderController.java:29)
    at java.base/java.lang.Thread.run(Thread.java:840)
~~~

This is an **illustrative trace**, not the output of the runnable program in a later section. Suppose the `com.acme.orders.*` classes belong to the application under investigation:

- The line `QuantityValidator.java:18` is the top of the trace, usually closest to the statement that threw the exception.
- `OrderService.java:47` is the call site that invoked the validator; it helps explain where the invalid input came from.
- `OrderController.java:29` is the business entry point through the controller layer.
- Frames in `java.base` belong to the platform library; they are usually just the execution scaffolding.

The "first application frame" is not always the place that **needs to be fixed**. If an error occurs inside a library because the application passed an invalid argument, a library frame may appear at the top, while the first application frame is the call site passing the argument that needs to be inspected. Conversely, if an exception is wrapped across multiple layers, the outer trace only shows where it was wrapped; to find the root error, you must read `Caused by` and the individual trace of each cause.

This lesson focuses on a practical workflow: **read the frame structure → distinguish application code from frameworks → follow the cause/suppressed chain → match the exact class/file/line against the deployed artifact → verify the hypothesis with context and reproduction**.

## 2. What does a stack frame contain?

The familiar display format is:

~~~text
at package.Class.method(FileName.java:123)
~~~

Components:

| Component | Interpretation | Question to ask |
| --- | --- | --- |
| `package.Class` | Binary name of the class containing the frame | Does the class belong to an application module/package, a library, or the JDK? |
| `method` | Name of the executing method; may be `<init>`, `<clinit>`, or a synthetic name | Is this a constructor, static initialization, lambda, or regular method? |
| `FileName.java` | Source file name attached to the class at compile time, if metadata is present | Which source version is this file from? |
| `123` | Line number corresponding to the code position according to the class's debug info | Is that line a throw statement or a method call? |
| `at` and frame prefix | Formatting convention when printing a stack trace | Is there a module/class loader or other info before the class name? |

Since Java 9, a trace may display a module or class loader prefix, for example:

~~~text
at java.base/java.util.Objects.requireNonNull(Objects.java:209)
at my.module/com.example.app.PaymentService.pay(PaymentService.java:41)
~~~

The line numbers here are **illustrative only**, not a claim about line numbers across all JDK versions. `java.base/` is a module name, not a package name. To classify a frame, look at the actual class/package name rather than slicing the string after `at` using a fixed format.

### 2.1. File names and line numbers may be missing

Some display formats:

~~~text
at com.example.app.Job.run(Job.java:57)
at com.example.app.GeneratedProxy.invoke(Unknown Source)
at java.base/java.lang.Object.wait(Native Method)
~~~

`Unknown Source` usually means there is insufficient file/line information for that frame. `Native Method` indicates a native method. Depending on the class file and Java runtime, the file name may still appear without a line number, or both may be absent.

**Do not conclude that the program is not running application code** just because the trace does not print line numbers. Check the actual class file being executed, compiler options, bytecode generation, and debug information.

## 3. Frame order: where to start investigating and the call chain

A `Throwable` trace is typically printed in order with **the frame closest to where the stack was captured at the top**, followed by callers going backward down the call stack. For an exception created and thrown at the same typical location, the top frame usually points to the `throw` line or the exception creation statement.

Diagram:

~~~text
HTTP endpoint()
    -> OrderService.create()
        -> Validator.check()
            -> throw IllegalArgumentException

Trace when thrown:
    Validator.check(Validator.java:18)          <-- near the throw site
    OrderService.create(OrderService.java:47)   <-- validator call site
    OrderController.endpoint(Controller.java:29)
    ... framework / thread entry ...
~~~

Points to remember:

1. **Top does not always mean the ultimate root cause**: the exception may be a wrapper such as `CompletionException`, `ExecutionException`, or `InvocationTargetException`.
2. **The first application frame is not always a programming bug in that frame**: it may simply have received bad data from another layer; check invariants and inputs at the callers.
3. **A `catch` frame is not necessarily where the exception started**: if code only does `catch (Exception e) { log(e); }`, the trace of `e` still describes the path that was recorded, without turning into a new trace at the log site.
4. **Do not look only at the last frame or the last printed exception**: in a multi-layered trace, the `Caused by` section has its own trace, which is usually closer to the deepest error.

### 3.1. An exception created at a different time from when it is thrown

A stack trace is tied to the state of the `Throwable` when stack information was captured (normally when the Throwable object was created). For example:

~~~java
IllegalStateException error =
        new IllegalStateException("delayed failure");

doSomethingElse();

throw error;
~~~

This is an **illustrative fragment**, assuming `doSomethingElse` has been declared. The exception is created earlier and thrown later; the trace may point to **the object creation line** rather than the exact `throw error` line. Calling `fillInStackTrace()` again can change the stack information, but it should not be used just to make logs look "nicer"; it alters the source of evidence. An exception can also be created with a constructor that disables writable stack traces or modified via `setStackTrace()`, causing the trace not to reflect the usual execution path.

Therefore, do not assert that "line 12 is definitely the throw statement" when the only evidence is a `StackTraceElement`. Read the code around the line and understand when the exception is created and thrown.

## 4. Seven-step workflow to find the right application frame

When a stack trace appears in production logs, you can follow this sequence:

1. **Preserve the full event:** exception name, message, full stack trace, `Caused by`, `Suppressed`, timestamp, request ID/correlation ID, deployment/build ID, and thread name.
2. **Identify the outermost exception and root cause:** did the wrapper come from async/framework code or is there a real error in a deeper layer? Read each trace block instead of only looking at the first line.
3. **Narrow down application packages/modules:** base this on the actual namespace, such as `com.example.billing`, `vn.company.report`, or known application modules; do not just search for a company name string because an SDK might share the same name.
4. **Select the relevant frame:** in the stack of the appropriate cause, find the application frame closest to the error site; then inspect the application frames below it to understand the inputs and call flow.
5. **Verify the code version:** identify the exact jar/image/build/commit that was running. Open the corresponding source file, rather than automatically using the latest version on the development branch.
6. **Read the context around the line:** inspect the statement, arguments, prior state, catch/rethrow, side effects, and data flow from callers; you may need to read additional frames above or below.
7. **Reproduce and fix at the invariant level:** add a test proving the cause, record errors appropriately, and ensure you are not just changing a log line; for race/async bugs, check threads and completion timing.

The workflow is iterative: after reading the source, you may see that the frame under inspection is a wrapper, leading you back to a deeper cause or a caller frame further down.

### 4.1. Selecting a frame is not about filtering out libraries

If the trace is:

~~~text
java.lang.IllegalArgumentException: negative length
    at java.base/java.util.Arrays.copyOf(Arrays.java:...)
    at com.example.app.DocumentService.copy(DocumentService.java:64)
    at com.example.app.RequestHandler.handle(RequestHandler.java:31)
~~~

The `...` marks are **illustrative placeholders without real line numbers**. The library frame above indicates the error was detected in `Arrays.copyOf`; the application frame `DocumentService.java:64` may be where a **negative length was passed** into the library. You need to inspect the size/input calculation logic there, rather than "fixing the JDK" just because the top frame is in `java.base`.

Conversely, if the top package is a third-party library and the error lies deep inside the library's internals, you may need to check inputs/dependency versions, open the dependency source for the exact release, read release notes, or minimize a reproducer to report a library bug. Do not automatically blame application code for everything.

## 5. Java 17 example: extracting application frames and matching exact lines

The complete example below throws `IllegalArgumentException` in the `parse` method, through callers `load` and `endpoint`. `main` catches the exception, calls `getStackTrace()`, and prints only the frames of the application class.

Save this as **`ApplicationFrameTraceDemo.java`**, starting at line 1 of the code block; do not add blank lines before the class declaration if you want the line numbers in the output to match:

~~~java
public class ApplicationFrameTraceDemo {
    static void parse(String value) {
        if (value.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
    }

    static void load() {
        parse(" ");
    }

    static void endpoint() {
        load();
    }

    public static void main(String[] args) {
        try {
            endpoint();
        } catch (IllegalArgumentException error) {
            System.out.println(error);
            for (StackTraceElement frame : error.getStackTrace()) {
                if (frame.getClassName().equals(ApplicationFrameTraceDemo.class.getName())) {
                    System.out.printf("%s(%s:%d)%n",
                            frame.getMethodName(), frame.getFileName(), frame.getLineNumber());
                }
            }
        }
    }
}
~~~

From the directory containing the file, using JDK 17 or later:

~~~bash
javac --release 17 ApplicationFrameTraceDemo.java
java ApplicationFrameTraceDemo
~~~

Exact stdout of the source version above when compiled with `javac`'s default line metadata:

~~~text
java.lang.IllegalArgumentException: name must not be blank
parse(ApplicationFrameTraceDemo.java:4)
load(ApplicationFrameTraceDemo.java:9)
endpoint(ApplicationFrameTraceDemo.java:13)
main(ApplicationFrameTraceDemo.java:18)
~~~

**Source code mapping:**
- Line **4** is `throw new IllegalArgumentException(...)` in `parse`. This is the site causing the failure in the example.
- Line **9** is `parse(" ")` in `load`, where a whitespace-only string is passed into validation.
- Line **13** is `load()` in `endpoint`.
- Line **18** is `endpoint()` inside `main`'s `try` block.

Line numbers reflect the compiled file, not the line numbers on a documentation page or extra formatting wrapped in an IDE. If you copy the program and add imports/comments/blank lines at the top, the line numbers will shift accordingly. That is expected; open the source **at the exact compiled state**, rather than trying to force the example's line numbers at all costs.

In this source, every frame we print belongs to `ApplicationFrameTraceDemo`. In a real application with many classes in the same namespace, you can filter by one or more package prefixes, but avoid filtering by only a single class so you do not miss related frames.

### 5.1. From trace to fix

Looking only at line 4 shows validation throwing an exception; that is **correct behavior** if the method requires a non-blank name. The place to fix could be:
- `load` passing an invalid `" "` string;
- a controller failing to validate/normalize input;
- or API documentation not clearly stating the valid value rules.

Do not remove validation just to make the stack trace go away. Understand the invariants and data flow through the `load` and `endpoint` frames. This is what distinguishes **locating where the exception appeared** from **identifying the root cause and fixing the right bug**.

## 6. `-g:none`: runnable class without source line information

Using the same `ApplicationFrameTraceDemo.java` file above, recompile with:

~~~bash
javac --release 17 -g:none ApplicationFrameTraceDemo.java
java ApplicationFrameTraceDemo
~~~

Stdout from a Java 17 environment for this program:

~~~text
java.lang.IllegalArgumentException: name must not be blank
parse(null:-1)
load(null:-1)
endpoint(null:-1)
main(null:-1)
~~~

When debug information is disabled with `-g:none`, `getFileName()` may return `null` and `getLineNumber()` returns a negative value (in this experiment, `-1`). The JVM still knows the class and method names, but **cannot directly map line numbers** from those frames.

Options to know:

| Compiler option | Main meaning |
| --- | --- |
| `javac Foo.java` | Default usually includes source and line info for stack traces |
| `javac -g Foo.java` | Generates all supported debug information, including line/source/local variables |
| `javac -g:lines,source Foo.java` | Requests line number and source file metadata |
| `javac -g:none Foo.java` | Generates no debug information |
| `javac --release 17 Foo.java` | Compiles against Java 17-compatible API/target; does not automatically guarantee current source matches the deployed build |

Having only class/method names can still be useful. You can use `javap` to inspect the bytecode/line table if the class has metadata; if the artifact has had line info stripped, no magic command can recover the exact line table from a class that only retains method names. You must locate the source/build artifact or reproduce on a build with debug info.

### 6.1. `javap -l` and `javap -c -l`

For a class compiled in the current directory:

~~~bash
javap -l ApplicationFrameTraceDemo
javap -c -l ApplicationFrameTraceDemo
~~~

`javap -l` lists the line number table / local variable table when present; `-c` helps correlate bytecode with code locations. Output depends on the compiler version and specific bytecode, so there is no single fixed stdout for every class here.

For a jar, specify the proper classpath and fully-qualified class name:

~~~bash
javap -classpath path/to/app.jar -c -l com.example.app.Service
~~~

This command is only a path structure example; replace `path/to/app.jar` and the class name according to your real artifact. If a class is provided by another build/repackaging, use the exact jar/image loaded at runtime rather than a different library sharing the same FQCN.

The line table provides the mapping **bytecode offset → source line**; it does not store the full source code for you to read statement contents. To see the code at line 123, you still need the source file from the exact version.

## 7. `StackTraceElement`: reading frames via API instead of string parsing

In Java, `Throwable.getStackTrace()` returns a `StackTraceElement[]` array. Each element provides notable fields:

| Method | Value | Notes |
| --- | --- | --- |
| `getClassName()` | Name of the class declaring the frame | May contain `$` for nested/anonymous/generated classes |
| `getMethodName()` | Method name | May be `<init>`, `<clinit>`, `lambda$...` |
| `getFileName()` | Source file name or `null` | Not an absolute path |
| `getLineNumber()` | Line number or special value | Negative numbers do not represent a valid Java line |
| `isNativeMethod()` | Whether the frame represents a native method | Has no simple corresponding Java line |
| `getModuleName()` | Module name if present | May be `null` |
| `getModuleVersion()` | Module version if present | May be `null` |
| `getClassLoaderName()` | Class loader name if present | May be `null` |

Do not parse `"at "...` strings to extract file/line when you **already have the `Throwable`**: using `StackTraceElement` directly is more accurate and does not depend on whitespace or module prefixes. When you only have a text log file, you can use a stack trace parser suited to the JVM format, but make sure to preserve `cause`/`suppressed` and `... N more` lines.

### 7.1. Selecting application frames by predicate, not fixed position

This is an **illustrative fragment**, usable inside a class that has imported `java.util.Arrays`, `java.util.Optional` and has a `Throwable failure`:

~~~java
Optional<StackTraceElement> firstAppFrame =
        Arrays.stream(failure.getStackTrace())
                .filter(frame ->
                        frame.getClassName().startsWith("com.example.app."))
                .findFirst();
~~~

`firstAppFrame` holds the frame closest to the exception site in that namespace, if any. However, this predicate is only a **filtering hint**:
- An application may have multiple root packages.
- An internal library using the same prefix might not belong to the responsible module.
- A framework/generator may create classes placed in an application package.
- The exception may originate in a different `cause`, not the outermost `failure`.

You must inspect the full trace and select the right cause and module based on deployment details. Do not treat `findFirst()` as an automatic bug-finding algorithm.

### 7.2. Iterating through causes, but avoid unguarded loops

An exception can have multiple wrapping layers:

~~~text
CompletionException
    -> IllegalStateException
        -> IOException
~~~

To find the ultimate cause, you can follow `getCause()`, but keep in mind:
- A wrapper may carry important business context even if the deep cause is an I/O error.
- Not every `Throwable` is guaranteed to have a cause.
- An exception may intentionally disable writable stack traces.
- If external code constructs an unusual chain, an automated algorithm should bound depth or guard against cycles by identity.

Simple fragment:

~~~java
Throwable cursor = failure;
while (cursor.getCause() != null) {
    cursor = cursor.getCause();
}
System.out.println(cursor.getClass().getName());
~~~

This fragment assumes `failure` already exists; it illustrates the normal acyclic cause chain case. When building a general-purpose log analysis tool, use a visited set keyed by **identity** or a depth limit to guard against unusual chains, rather than assuming every Throwable comes from standard code.

## 8. `Caused by`: which frame is the wrapper site, and which is the root error?

Example:

~~~text
java.lang.IllegalStateException: cannot start service
    at com.example.app.Bootstrap.start(Bootstrap.java:68)
    at com.example.app.Main.main(Main.java:21)
Caused by: java.io.IOException: config unreadable
    at com.example.app.ConfigReader.load(ConfigReader.java:43)
    at com.example.app.Bootstrap.start(Bootstrap.java:64)
    ... 1 more
~~~

This is an illustrative trace. The **outermost** part shows `Bootstrap.start:68` wrapping the error. `Caused by` shows `ConfigReader.load:43` is where the original exception was recorded. If you only read `Bootstrap.start:68` and ignore the cause, you can easily fix the wrong layer.

Proper way to read it:
1. Identify the outermost exception and why it was created: e.g., `IllegalStateException("cannot start service")`.
2. Go into `Caused by` and examine the root error type: `IOException`.
3. Find the application frame in **the cause's trace**.
4. Return to the wrapper's frame to understand at which boundary the exception was translated and what context was added.
5. Use both blocks to decide the action: fix a path/configuration, improve the message, handle retries, or report the error.

### 8.1. `... N more` is not N randomly lost frames

When `Throwable.printStackTrace()` prints multiple exceptions sharing the same tail of the stack, Java can elide the shared frames as `... N more`. This is **a compact notation for frames shared with the enclosing exception's stack**, not hidden source lines, nor N unread exceptions.

If you need the full stack array for each cause in code, `cause.getStackTrace()` still provides that cause's array (unless the stack trace was customized or omitted). When you only have a shortened text log, match the shared frames at the appropriate position or use an IDE/parser that supports it. Do not conclude that the call path between two layers is broken just because `... 1 more` appears.

### 8.2. `throw e` vs. `throw new ...(..., e)`

~~~java
try {
    callRepository();
} catch (IOException e) {
    throw e;
}
~~~

This fragment assumes the enclosing method declares `throws IOException`. It **rethrows the same exception object** `e`; the stack trace still reflects the original capture location and is not replaced with a brand-new stack just because it was rethrown.

Conversely:

~~~java
try {
    callRepository();
} catch (IOException e) {
    throw new IllegalStateException("loading report failed", e);
}
~~~

In this fragment, the **new** exception has its own stack at the wrapping site, and `e` becomes the cause with its own trace. Wrapping is appropriate when translating an exception across an API boundary, provided you preserve `cause`. If you only write `throw new IllegalStateException(e.getMessage())`, you lose the natural cause chain and make finding the original frame much harder.

## 9. `Suppressed`: cleanup errors also have their own stack

With `try-with-resources`, if the body throws exception A and `close()` also throws exception B, B is normally attached to A as a **suppressed exception**, rather than replacing A as the primary exception.

Logs may contain:

~~~text
java.io.IOException: read failed
    at com.example.app.ConfigReader.read(ConfigReader.java:...)
    Suppressed: java.io.IOException: close failed
        at com.example.app.Resource.close(Resource.java:...)
    ...
~~~

The `...` in the example is an illustrative placeholder; in a real run there will be specific file/line or stack details.

Do not treat `Suppressed` as meaningless. A cleanup failure can indicate an inability to flush data, a broken connection, an unreleased lock, or an important infrastructure issue. However, you usually need to investigate **the primary error A first**, then evaluate whether B is a consequence or an independent problem.

### 9.1. Complete Java 17 example for cause and suppressed

Save **`CauseAndSuppressedDemo.java`** with the exact content below, starting at line 1:

~~~java
import java.io.IOException;

public class CauseAndSuppressedDemo {
    static final class FailingResource implements AutoCloseable {
        @Override public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static void readConfig() throws IOException {
        try (FailingResource ignored = new FailingResource()) {
            throw new IOException("read failed");
        }
    }

    static void start() {
        try {
            readConfig();
        } catch (IOException cause) {
            throw new IllegalStateException("startup failed", cause);
        }
    }

    public static void main(String[] args) {
        try {
            start();
        } catch (IllegalStateException outer) {
            Throwable cause = outer.getCause();
            System.out.println("outer: " + outer.getMessage());
            System.out.println("cause: " + cause.getMessage());
            System.out.println("suppressed: "
                    + cause.getSuppressed()[0].getMessage());
            StackTraceElement first = cause.getStackTrace()[0];
            System.out.println("origin: " + first.getMethodName()
                    + "(" + first.getFileName() + ":" + first.getLineNumber() + ")");
        }
    }
}
~~~

Run:

~~~bash
javac --release 17 CauseAndSuppressedDemo.java
java CauseAndSuppressedDemo
~~~

Exact stdout:

~~~text
outer: startup failed
cause: read failed
suppressed: close failed
origin: readConfig(CauseAndSuppressedDemo.java:12)
~~~

**Explanation:**

- The outermost exception is `IllegalStateException("startup failed")`, created at line **20**, in `start()`.
- `getCause()` returns `IOException("read failed")`, created/thrown at line **12**, in `readConfig()`.
- Upon exiting try-with-resources, `FailingResource.close()` also throws `IOException("close failed")` at line **6**. Because the body already threw an error, this close error is attached to `cause.getSuppressed()`.
- Because the code takes the first frame from **cause**, `origin` accurately reflects `readConfig(...:12)` rather than the wrapping line in `start`.

The program assumes at least one suppressed exception to focus on the mechanism we intentionally triggered. In a general library, always check the length of `getSuppressed()` before accessing index 0; many normal exceptions have no suppressed errors.

### 9.2. Do not arbitrarily apply suppressed rules to every callback

`try-with-resources` has suppressed semantics defined by Java. However, two asynchronous callbacks both throwing exceptions, or a `whenComplete` action throwing when the source has already failed, **does not automatically guarantee** that the callback exception appears in `getSuppressed()` of the original error. Only infer suppressed behavior when the actual API/logic guarantees it. To record two independent errors, you need a pre-designed observation channel or aggregated result.

## 10. Matching the exact source line requires the exact artifact version

Suppose a production log says:

~~~text
at com.example.billing.InvoiceService.issue(InvoiceService.java:142)
~~~

If you open the current source and line 142 is only a comment, do not conclude the log is wrong. Possible reasons:
- Production is running a jar/image from an older commit.
- Your open branch added or removed lines earlier in the file.
- The build uses generated sources or annotation processing.
- A dependency has two versions or multiple copies on the classpath.
- Shading/repackaging/obfuscation renamed classes or altered bytecode layout.
- Source code was compiled with options that strip debug information.
- Some classes were transformed/instrumented at load time.

**Line numbers in a stack trace correspond to the running class file**, not automatically to the latest Git branch. Matching workflow:

1. Identify the actual application version via build ID, git commit, container image digest, or release artifact.
2. Check the class name, module, and jar containing the class loaded at runtime.
3. Open the source corresponding to **that exact build**; in a monorepo, locate the right module.
4. Go to the file/line recorded in the trace; read about 10–20 lines around it, not just a single isolated line.
5. Check the line table from the class file if the source and trace still do not match.
6. If the bug depends on concurrency/data, reproduce with the same inputs/configuration/dependency versions, rather than just editing code to match line positions.

### 10.1. File name alone is not enough to uniquely identify source

A repository may have multiple files named `Service.java` across different modules. `StackTraceElement.getFileName()` usually returns only the file name, not the absolute path. You must combine **the full class name and package** to locate the right file.

For example, `com.example.billing.internal.InvoiceService` usually corresponds to a source path like `com/example/billing/internal/InvoiceService.java` in the owning module. However, classes can be generated or transformed; that is a common organizational convention, not an absolute mapping for every compiler.

For nested classes:
- `Outer$Inner` may live in the same `Outer.java`.
- `Outer$1` may be an anonymous class or compiler-generated class.
- `Outer$$Lambda$...`/`lambda$method$0` may relate to a lambda, with no file literally named after the synthetic class.

So do not look for a file named `Outer$Inner.java` just because the frame prints that binary class name.

### 10.2. Duplicate classes on the classpath

Two jars containing the same class name can cause the program to load a different version from the one you have open. To investigate runtime code, you can query `ProtectionDomain`/`CodeSource` of the running class in an appropriate environment. Example fragment:

~~~java
var source = InvoiceService.class.getProtectionDomain().getCodeSource();
System.out.println(source == null ? "unknown" : source.getLocation());
~~~

This fragment assumes `InvoiceService` is available; `CodeSource` may be `null` for some class loaders/modules, and the returned location is not complete proof of container/deployment provenance. Still, it can help locate the jar from which the class was loaded. Do not print sensitive server paths/URLs to public logs; use internal diagnostic channels.

### 10.3. Jars and class files can be inspected with JDK tools

Find class names inside a jar using:

~~~bash
jar tf path/to/application.jar
~~~

Inspect a class's line number table:

~~~bash
javap -classpath path/to/application.jar -l com.example.billing.InvoiceService
~~~

The lines above are **reference commands**, not runnable as-is because the file and class names are illustrative. `jar tf` lists entries; `javap -l` reads line/local variable info from the class if present. With executable fat jars or custom class loaders, the classpath and layout may differ from a standard jar; verify the actual class file instead of applying commands mechanically.

To inspect specific bytecode, use `javap -c -l`. You still need to understand calls and invariants in the source; bytecode and line tables do not directly tell you whether input data is valid.

## 11. Do not confuse the logger's stack trace with the exception's trace

In logging, three cases must be separated:

1. **Logging the exception object:** `logger.error("failed", e)` with a logging framework supporting a Throwable parameter usually prints `e`'s stack.
2. **Logging only the message:** `logger.error("failed: {}", e.getMessage())` may only print a string, with no frames.
3. **Calling `Thread.currentThread().getStackTrace()` or `StackWalker` at the log site:** creates a snapshot of the **current thread's call stack at log time**, which is not necessarily the trace where the exception was originally created.

For example, `e.printStackTrace()` prints the exception according to the current handler; in real programs, it is usually better to pass `e` into a structured logging system to preserve context/request IDs rather than printing freely to stderr from multiple threads. Yet even a good logger cannot fix an exception that lost its cause due to improper rethrowing.

### 11.1. `Throwable.getStackTrace()` differs from `StackWalker`

`Throwable.getStackTrace()` returns the frames attached to a Throwable object. `StackWalker`, introduced in Java 9, can inspect the **current thread's** call stack via `walk`/`forEach`. It does not let you read backward into the vanished call stack of another worker just because you hold a `Future` object.

In async code, when `Future.get()` throws `ExecutionException` on the thread receiving the result, the frames of `ExecutionException` and the frames of its cause can belong to **two different execution stages/layers**. To see what the worker was doing, inspect `getCause().getStackTrace()`; do not look at the catching thread's current stack and conclude the worker threw the error at the `get()` line.

## 12. Lambdas, reflection, proxies, and frameworks make frames harder to read

Not every application frame prints a "clean" method name. In Java 17 you may encounter:

~~~text
at com.example.app.TaskService.lambda$execute$0(TaskService.java:74)
at java.base/java.lang.reflect.Method.invoke(Method.java:...)
at jdk.proxy1/jdk.proxy1.$Proxy0.fetch(Unknown Source)
at com.example.app.TaskService.execute(TaskService.java:61)
~~~

This is an **illustrative trace**; exact positions/lines and proxy names depend on the runtime/compiler. Common frame patterns:

| Indicator | How to read |
| --- | --- |
| `lambda$someMethod$0` | Synthetic method for a lambda body; open the enclosing source method and go to the corresponding line |
| `<init>` | Constructor |
| `<clinit>` | Static initializer |
| `$Proxy...`, `$$Enhancer...`, Byte Buddy/CGLIB | Generated/delegating class; look for the application callback/target class |
| `Method.invoke` or `Constructor.newInstance` | Reflection; check the cause/target method or wrapped exception |
| `CompletableFuture$...` / `ForkJoinPool...` | Async infrastructure; look for the application lambda/callable and its cause |
| `Thread.run` / executor worker | Thread entry point; usually not where business logic needs fixing |

A frame like `lambda$run$0(MyService.java:74)` can still point accurately to the line inside the lambda in `MyService.java`. There is no need to look for a `lambda$run$0.java` file.

### 12.1. Async does not have a single conventional "cross-thread stack"

When work moves from thread A to executor B and then callback C, the call stack on A is no longer "below" the stack on B. Therefore, the worker's trace does not necessarily contain the controller that submitted the task. Without a task ID, request ID, trace ID, or context propagated across async boundaries, you may not know which request the worker belongs to.

Diagnostic approach:
- Attach an `operationId`/`correlationId` as soon as the task is submitted.
- Record the submission point and task start/end milestones when needed.
- Capture errors via `Future.get()`, `CompletableFuture.join()`, and analyze `getCause()`.
- Use tracing/instrumentation with async context support if the system requires correlation across multiple threads/services.
- Read application frames in **the exception's actual trace**, and do not assume a missing caller is unrelated.

Do not stitch stack traces from two different threads together and treat them as a single continuous call stack. You can correlate two events via a correlation ID, but that is **a business/orchestration relationship**, not a natural Java call stack relationship.

### 12.2. `CompletionException` and `ExecutionException`

For example, suppose a task created by `CompletableFuture.supplyAsync` throws `IllegalStateException`. A caller invoking `join()` may receive `CompletionException`. A caller invoking `Future.get()` may receive `ExecutionException`. In this case:
1. Note the wrapper to understand which layer observed the failure.
2. Read `getCause()` to find the worker's error.
3. Find the application frame in the cause's stack.
4. Do not fix only the `future.join()` or `future.get()` line just because it appears in the outermost stack.

Note that timeout or cancellation also have their own exception types and do not automatically prove the underlying work has stopped; capturing a stack trace is no substitute for managing state and side effects.

## 13. The source line is only the starting point: context analysis

After finding the frame `OrderService.java:47`, you still need to read enough context:

- What call is it? Where were the arguments computed? Could null/empty/negative values have slipped past an earlier layer?
- Is there a special branch for bad data not covered by tests?
- Is that line inside a loop or stream? Which element caused the failure?
- Did the error come from a constructor/static initializer executed when the class was first loaded?
- Is a transaction open? Have side effects already been committed?
- Is another worker mutating the same state?
- Did a wrapper layer only add a message or change the exception type without preserving the cause?
- Which **release**, environment, and build flags does that line exist in?

A common example:

~~~java
return orders.get(index).customer().name().trim();
~~~

This is an illustrative fragment. A `NullPointerException` points to a single line containing multiple dereferences. The line number alone does not tell you whether `orders`, `orders.get(index)`, `customer()`, or `name()` was null. Modern Java can generate **helpful NullPointerException messages** when conditions allow, but you should not rely on that alone. Read the expression, extract intermediate values into named variables if needed, and add tests for specific states.

A call line:

~~~java
repository.save(order);
~~~

may fail inside JDBC/transaction/framework code. The line indicated in the service shows **the call path to storage**, not necessarily that the service code is where the root cause originated. Inspect the SQL exception cause, constraint violations, connection state, and input data to decide the fix.

## 14. Common mistakes when matching files and line numbers

### 14.1. Opening the latest branch instead of the running build

If the log came from an older build image, line 87 on the current branch may be unrelated. **Verify the commit/tag/build ID before making a fix.** This is one of the most common reasons engineers "cannot find the failing line."

### 14.2. Searching for a file by name without checking package/module

`Service.java` can exist in many places. Use the FQCN and the class's module/jar, not just `FileName.java`.

### 14.3. Taking the first application frame of the outermost exception and ignoring the cause

The outermost exception may be a wrapper. Read `Caused by`, especially with I/O, JDBC, reflection, and `CompletableFuture`.

### 14.4. Treating `... N more` as missing lines

It describes shared suffix frames across traces, not randomly truncated stack frames. However, loggers/libraries can also genuinely **truncate** stack traces by configuration; distinguish the two phenomena.

### 14.5. Assuming every frame must have a file name and line number

`Unknown Source`, `Native Method`, dynamically generated classes, classes compiled with `-g:none`, or special source maps can lack line numbers. Do not invent line numbers; investigate using method names, bytecode, source/build artifacts, and reproduction.

### 14.6. "Fixing" the first library frame

The error may be due to the application passing bad arguments; read the nearest application frame and input invariants. At the same time, do not rule out a library bug if evidence points to an internal bug.

### 14.7. Searching only for `throw` statements, not where exceptions are constructed

A Throwable can be created before being thrown or reused; the trace is tied to the object's stack capture, not necessarily the nearest `throw e` line. Look for how the exception is created and rethrown.

### 14.8. Logging `e.getMessage()` instead of the whole throwable

A message does not contain the stack trace, cause, or suppressed exceptions. When diagnosing unknown errors, log the throwable to a trusted internal channel while controlling sensitive data and log volume.

### 14.9. Ignoring exceptions in `Suppressed`

Cleanup errors can provide a crucial second clue; check `getSuppressed()` when `try-with-resources` is involved.

### 14.10. Treating the catching thread's frame as the worker's frame

Exceptions across `Future`/`CompletableFuture` have a wrapper on the caller thread; the root error has the trace of the thread executing the task. Keep the two layers of evidence separate.

## 15. Testing and tools to prove the mapping

A small, repeatable QA loop:

1. Write a small Java file that triggers a controlled failure.
2. Compile with the exact Java level you need to support, e.g. `javac --release 17`.
3. Call `Throwable.getStackTrace()` and print `getClassName()`, `getMethodName()`, `getFileName()`, and `getLineNumber()`.
4. Open the compiled source file, count lines, and verify the call sites.
5. Recompile the same file with `-g:none`; observe the loss of file/line info while class/method names remain.
6. If needed, run `javap -c -l` to inspect the corresponding line number table.
7. Add a wrapper `throw new ...(..., e)` and verify that the outer trace and cause trace point to two different locations.
8. Add a `try-with-resources` block whose `close()` throws to verify suppressed exceptions.
9. When working on a real system, repeat using **verifiable production artifacts** rather than assuming a small Java test file behaves identically to every environment.

### 15.1. JUnit 5 example

This is a **test fragment**, assuming JUnit 5 is configured, `ApplicationFrameTraceDemo` is in test scope, and `assertThrows`, `assertEquals`, and `assertTrue` are statically imported:

~~~java
IllegalArgumentException ex = assertThrows(
        IllegalArgumentException.class,
        () -> ApplicationFrameTraceDemo.parse(" "));

StackTraceElement top = ex.getStackTrace()[0];
assertEquals("parse", top.getMethodName());
assertEquals("ApplicationFrameTraceDemo.java", top.getFileName());
assertTrue(top.getLineNumber() > 0);
~~~

Usually you should not hardcode line number 4 in business unit tests, because adding a comment at the top of the file will break the test even though the program is still correct. When the goal is **an exercise verifying the line table**, asserting against the actual line number is valid; for production unit tests, assert the exception type/message/invariants, and only check for a positive line number if you want to ensure debug metadata is present.

### 15.2. When logs lack source lines in production

Checklist table:

| Symptom | Reasonable check |
| --- | --- |
| Frame shows `(Unknown Source)` | Check class file debug metadata and compiler/ProGuard settings |
| Frame shows file/line that does not match the repo | Check build ID, commit, generated sources, and the running jar |
| Frame belongs to `lambda$...` | Open the enclosing method of the lambda and the corresponding source line |
| Frame belongs to `$Proxy...` | Identify the target method, interceptor, and cause |
| Only `CompletionException`/`ExecutionException` is visible | Open `getCause()` and inspect the original task's trace |
| Trace is truncated by logger config | Adjust stack trace logging policy with bounded limits and data protection |
| Multiple exceptions share the same message | Use timestamps, correlation IDs, and class/method/cause rather than message text alone |
| Error only appears under load | Capture thread/trace context, inputs, and shared state; reproduce the race with coordination |
| Negative line number | Check `-g` and the line table; do not guess the line from the method name |

## 16. Safe and sufficiently contextual logging

In production applications, record enough diagnostic data while avoiding exposing sensitive information:

- **Exception type + cause chain**: know which error actually occurred and where it was wrapped.
- **Notable application stack frames**: class, method, file, line; keep the full trace in internal channels when needed.
- **Correlation ID or operation ID**: connect logs across threads/tasks.
- **Build/release ID**: identify the exact source.
- **Thread name and module/service**: know the execution environment.
- **Safe business attributes**: state, operation type, stable error codes; avoid raw tokens, passwords, personal data, or SQL containing sensitive values.

Avoid both extremes: logging only `e.toString()` which leaves too little evidence, or logging entire request payloads/tokens which leaks sensitive data. Use structured logging with appropriate levels and retention policies; do not build a single massive log line containing all data.

### 16.1. Log once at the appropriate boundary

An exception might be logged in the repository, service, controller, and again in a job handler, producing multiple identical stack traces. Normally you should **preserve the cause when crossing layers** and choose the logging point that owns error reporting, rather than logging an error and rethrowing the same exception everywhere. Still, there are cases where each layer has its own metrics or audit needs; in those cases, distinguish the records clearly so you do not multiply the apparent incident count.

If a method catches an error to recover successfully, record an appropriate recovery metric instead of emitting a high-severity error log as if the final request failed. A stack trace is meaningful when correlated with **the final processing outcome**.

## 17. Decision tree from a frame to an investigation path

~~~text
Have a Java stack trace
|
+-- Has Caused by / Suppressed?
|     +-- Yes -> read the separate traces and identify the primary error
|     +-- No -> start from the current throwable
|
+-- Is the top frame in application code?
|     +-- Yes -> match file:line, then inspect callers below
|     +-- No -> find the nearest application frame and check inputs/cause
|
+-- Is there a valid line number?
|     +-- Yes -> open the exact source version, inspect lines around it
|     +-- No -> check debug info/class/jar/generated source
|
+-- Certain the source matches the deployed artifact?
|     +-- No -> verify release/build/commit/classloader
|     +-- Yes -> inspect expressions, invariants, actual state
|
+-- Reproducible?
      +-- Yes -> write a specific test and fix the root cause
      +-- No -> add safe telemetry and diagnose race/async behavior
~~~

The decision tree is a guiding method, not a program that automatically deduces bugs. The goal is to shorten the time from **a symptom in logs** to **a root cause provable with code and data**.

## 18. Checklist when reading a Java stack trace

- [ ] Preserved the full stack trace, including `Caused by`, `Suppressed`, and `... N more` if present.
- [ ] Distinguished the outermost exception, root exception, and cleanup errors.
- [ ] Found the application frame **in the trace of the appropriate cause**, not only in the outer trace.
- [ ] Read `class.method(File.java:line)` accurately, including module/class loader prefixes when present.
- [ ] Matched the right package, module, jar/image, and deployed build/commit.
- [ ] Inspected source around the line and the callers, rather than editing only the top line of the trace.
- [ ] Accounted for lambdas, constructors, static initializers, generated proxies, reflection, and async wrappers.
- [ ] Understood that `Unknown Source`/negative lines are information limits, not line numbers to guess.
- [ ] Verified debug metadata when source lines are missing or shifted; used `javap -l` when appropriate.
- [ ] Preserved `cause` when wrapping exceptions and avoided losing evidence by logging only the message.
- [ ] Distinguished the exception's trace from a stack snapshot at the log site.
- [ ] Checked business state, input data, side effects, and concurrency before concluding the root cause.
- [ ] Added a test proving the cause/fix without making it brittle by hardcoding development source line numbers.
- [ ] Protected sensitive data and controlled log volume in production.

### Practice exercise

Suppose an invoice export service throws `CompletionException` when an asynchronous data-fetching callback fails. The trace contains frames from `CompletableFuture`, an `InvoiceService.lambda$generate$0`, and a `SQLException` cause.

1. Explain why you should not fix the `future.join()` line just because the wrapper appears there.
2. Find the deepest cause and the application frame closest to the error site, then trace back through callers to identify the input data.
3. Verify whether the deployed artifact matches the IDE source and use `javap -l` if lines are shifted.
4. If `SQLException` was wrapped in `IllegalStateException` without preserving the cause, explain what evidence was lost.
5. If the task already wrote a file before failing, explain why identifying the throwing frame **does not mean the file was rolled back**.
6. Write a test that intentionally passes invalid data to `InvoiceService`, captures the exception, and verifies the error type, cause, and business code; do not rely on a fixed line number to test functionality.

**Conclusion:** Application frames pinpoint **a location along the execution path**, but accurate diagnosis requires combining them with **cause/suppressed exceptions, caller context, and the exact compiled source version**. Reading `File.java:line` is the start of the investigation, not a verdict that that line is always the bug to fix.