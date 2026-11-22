# Resources Declared in `try-with-resources` and Their Scope in Java

`try-with-resources` allows Java to **automatically close resources** when exiting a block, even if the `try` body throws an exception or executes a `return`. This syntax is especially useful for files, streams, readers, writers, connections, or objects that manage their own lifecycle. However, to use it correctly, you need to clearly distinguish **where the resource variable is declared**, **where it remains in scope**, and **at what point the object has already been closed**.

A simple example:

```java
try (var reader = java.nio.file.Files.newBufferedReader(path)) {
    String line = reader.readLine();
    System.out.println(line);
}
```

This is an **illustrative snippet**, assuming `path` has type `java.nio.file.Path` and the call is inside a method that handles or declares `IOException`. The `reader` variable is declared in the *resource specification* — the parentheses immediately following `try`. Java closes `reader` when exiting the `try` body; afterward, the variable name `reader` is no longer in scope.

There are two cases to distinguish:

- **Declaring a new resource in `try`:** `try (Reader r = ...) { ... }`. The name `r` can be used in the `try` body and, according to scope rules, in the appropriate parts of the resource declaration list that follow it, but **cannot** be used in `catch`, `finally`, or code after the construct.
- **Using a variable declared outside:** since Java 9, you can write `try (existingResource) { ... }` if the variable is `final` or *effectively final*. The variable name retains the scope of its original declaration and can appear after the `try` block, **but the object has already been closed**. "The variable still has a name in scope" does not mean "the resource is still usable".

## 1. Why does `try-with-resources` need its own scope?

A program typically has to perform two actions on a resource:

1. **Acquire ownership or open the resource:** for example, opening a reader for a file.
2. **Close the resource whether it succeeds or fails:** for example, releasing the file handle.

The manual approach is error-prone:

```java
var reader = java.nio.file.Files.newBufferedReader(path);
String line = reader.readLine();
reader.close();
```

This is **illustrative code that does not yet handle checked exceptions**. If `readLine()` throws an `IOException`, the subsequent `close()` line may not be executed. Writing a manual `try-finally` can partially address this, but you must be careful with errors occurring during opening, reading, and closing.

`try-with-resources` makes closing resources **part of the syntax's semantics**. The resource is closed when the `try` block finishes, regardless of whether you remember to call `close()` in every `return` branch.

```java
try (var reader = java.nio.file.Files.newBufferedReader(path)) {
    return reader.readLine();
}
```

This is an **illustrative method body** with a `String` return type and an appropriate `throws IOException` contract. The reader is closed before the method actually returns the result; if closing throws an exception, the return path may be replaced by an exception-throwing path.

A short scope helps **bound the resource lifetime**: reading/writing stays within the managed region, and statements after that region cannot accidentally continue using an open resource.

## 2. Requirements for an object to be a resource

A resource in `try-with-resources` must have a type compatible with **`java.lang.AutoCloseable`**. This interface has the method:

```java
public interface AutoCloseable {
    void close() throws Exception;
}
```

This is an **illustrative API signature**, not code you need to redeclare in your application. Some commonly used classes:

| Resource | Related interface/class | Typical purpose |
| --- | --- | --- |
| `BufferedReader` | `java.io.Closeable` → `AutoCloseable` | Read text and close the reader |
| `InputStream` | `java.io.Closeable` → `AutoCloseable` | Read bytes, release the input source |
| `OutputStream` | `java.io.Closeable` → `AutoCloseable` | Write bytes and close the output sink |
| `Scanner` | `java.io.Closeable` → `AutoCloseable` | Close the scanner and its underlying source if appropriate |
| `java.sql.Connection` | `AutoCloseable` | Return/close the connection depending on implementation |
| Custom class `implements AutoCloseable` | `AutoCloseable` | Define specific closing work |

An arbitrary object **does not become a valid resource merely because it has a method named `close()`**. Its type must implement `AutoCloseable` to be used directly in a resource specification.

If you write a custom class:

```java
final class LocalResource implements AutoCloseable {
    @Override
    public void close() {
        System.out.println("closed");
    }
}
```

then a variable of type `LocalResource` can be managed by `try-with-resources`. This example is an **illustrative class**; the overridden `close()` does not declare a checked exception, so users of this class do not have to handle checked `Exception` just for calling `close()`.

### `AutoCloseable` and checked exceptions

The `AutoCloseable.close()` interface allows declaring `throws Exception`; concrete classes often declare a narrower type or no checked exception at all. The compiler relies on the **static type of the resource** and related calls to check for checked exceptions that may occur during initialization, use, and closing.

For example, if you hold a resource in a variable of type `AutoCloseable` and `close()` can throw a checked `Exception`, a method using it may need an appropriate `catch` or `throws Exception`. Do not assume every `try-with-resources` only needs `catch (IOException)`.

## 3. Resource specification: declaring in parentheses right after `try`

The new declaration form:

```java
try (ResourceType resource = createResource()) {
    useResource(resource);
}
```

This is an **illustrative structure**, requiring `ResourceType implements AutoCloseable` and the corresponding methods. The clause `ResourceType resource = createResource()` consists of:

- **Resource type:** must be compatible with `AutoCloseable`.
- **Variable name:** e.g., `resource`, used within the scope allowed by Java.
- **Initializer:** an expression that creates or supplies a reference to the resource, evaluated upon entering the construct.

Multiple resources can be declared, separated by semicolons:

```java
try (FirstResource first = openFirst();
     SecondResource second = openSecond()) {
    useBoth(first, second);
}
```

The two types, two open functions, and usage function here are an **illustrative structure**, not a standalone program.

Key properties:

1. Initializers are evaluated **in left-to-right order**.
2. The `try` body runs after resource initialization completes.
3. Upon exit, successfully initialized resources are closed in **reverse order**: the last opened/declared is closed first.
4. If initializing the second resource fails, the first resource that was already initialized is still closed, even though the `try` body never ran.
5. After closing finishes, `catch` and `finally` attached to the `try-with-resources` construct are executed when applicable.

A trailing `;` at the end of the resource list is allowed by Java syntax; it does not create an extra empty resource.

## 4. Scope of newly declared resource variables

With the construct:

```java
try (var reader = java.nio.file.Files.newBufferedReader(path)) {
    System.out.println(reader.readLine());
}
```

the variable `reader` belongs to the resource scope of the construct, **not a local variable of the entire method**.

### Usable inside the `try` body

```java
try (var reader = java.nio.file.Files.newBufferedReader(path)) {
    String first = reader.readLine();
    String second = reader.readLine();
    System.out.println(first);
    System.out.println(second);
}
```

This is an illustrative snippet with `path` and an appropriate `IOException` contract. Both reads use the same managed reader. After the block finishes, Java closes the reader.

### Cannot use that resource name in a `catch` at the same level

The following snippet **intentionally does not compile**:

```java
try (var reader = java.nio.file.Files.newBufferedReader(path)) {
    System.out.println(reader.readLine());
} catch (java.io.IOException ex) {
    reader.close(); // Error: reader is not in scope.
}
```

The fix is not adding `throws` for `close()`, but properly understanding **scope**. `reader` declared in the resource specification is not visible in the `catch` body. Java has already called `close()` when exiting the `try` body anyway, so an extra close statement is unnecessary.

### Cannot use that resource name in a `finally` at the same level

```java
try (var reader = java.nio.file.Files.newBufferedReader(path)) {
    System.out.println(reader.readLine());
} finally {
    // reader.close(); // Wrong scope; resource is already managed automatically.
    System.out.println("read attempt finished");
}
```

This is an illustrative structure, requiring handling or declaring any `IOException` that may arise. `finally` can perform wrap-up work, but cannot directly access the `reader` variable declared in the resource specification. Closing the resource happens **before** the attached `finally`.

### Cannot use the resource name in statements after `try`

```java
try (LocalResource r = new LocalResource()) {
    System.out.println("inside");
}
// r.close(); // Compile error: out of scope.
```

This is an illustrative snippet when `LocalResource` is defined as in the previous section. You should not turn a local resource that only exists within the managed region into a long-lived dependency outside.

**Remember:** "the resource variable is out of scope" and "the resource object has already been closed" are two **distinct** facts that often happen together when leaving a `try-with-resources` construct with a new declaration.

## 5. Multiple resources: a previously declared variable can initialize a later resource

Declarations in a resource specification are processed sequentially. A later resource can depend on an earlier resource when initialized.

Example of reading text by wrapping a stream in a reader:

```java
try (var input = java.nio.file.Files.newInputStream(path);
     var reader = new java.io.BufferedReader(
             new java.io.InputStreamReader(
                     input, java.nio.charset.StandardCharsets.UTF_8))) {
    System.out.println(reader.readLine());
}
```

This is an **illustrative snippet**, requiring a valid `path` variable and handling or declaring `IOException`.

- The `input` variable is declared first, so the initializer of `reader` can reference `input`.
- `reader` uses `input` as its data source.
- Java will call `reader.close()` first, then `input.close()` according to the reverse-order rule.
- Because `reader.close()` may have already closed the underlying stream, `input.close()` may be a second close. Many implementations handle repeated closes safely, but you should not assume all resources tolerate double-close equally.

For a stream that is **completely owned** by the reader, it is usually sufficient to register only the **reader** in the resource specification to avoid unnecessary overlapping closes:

```java
try (var reader = java.nio.file.Files.newBufferedReader(
        path, java.nio.charset.StandardCharsets.UTF_8)) {
    System.out.println(reader.readLine());
}
```

Deciding which resource to register depends on **ownership**: which object is responsible for closing which object, and whether each resource independently needs closing.

### Cannot use a later-declared resource in the initializer of an earlier resource

Resource declarations follow Java's scope and definite assignment rules. You cannot use a variable that has not yet been declared or does not yet have a valid value in an earlier resource's initializer.

```java
// Intentionally wrong: second is not yet declared in first's initializer.
try (LocalResource first = second;
     LocalResource second = new LocalResource()) {
    // ...
}
```

When a dependency relationship is needed, declare **the source first and the dependent object later**, and consider lifetime/ownership to avoid double-close bugs.

## 6. Can a resource variable declared in parentheses be reassigned?

**No.** Resource variables declared directly in the resource specification have **`final`** semantics: you cannot assign a different reference to the resource variable inside the `try` body.

```java
try (LocalResource resource = new LocalResource()) {
    // resource = new LocalResource(); // Compile error.
}
```

The commented line is an error if uncommented. However, `final` here **does not make the resource object immutable**. You can still call its valid methods, read data, write to a stream, or mutate internal state according to its API.

Forbidding reassignment is important for cleanup: Java needs to know **the exact object registered for closing**. If you could silently swap the variable to another object, an object could lose its reference and leak resources.

Distinguish between:

- **`final` reference variable:** cannot be reassigned.
- **Resource object:** may have mutable state.
- **Open/closed state:** part of the resource's lifecycle; `final` does not guarantee the object is still open.
- **Thread safety:** `final` does not automatically make the resource's methods thread-safe.

Similar to `catch (final IOException ex)`, the `final` keyword does not mean you cannot call methods on the object.

## 7. Using an externally declared resource — Java 9 and later

Since **Java 9**, a resource specification can also use an **existing variable name** (or an eligible variable access expression), provided the referenced local variable is `final` or **effectively final** and definitely assigned.

Java 17 example:

```java
var reader = java.nio.file.Files.newBufferedReader(path);
try (reader) {
    System.out.println(reader.readLine());
}
```

This is an **illustrative snippet** inside a method with `path` and appropriate `IOException` handling.

Differences from `try (var reader = ...)`:

- `reader` is declared **outside** the resource specification, so the variable name can remain in scope **after** the `try` construct.
- Java still calls `reader.close()` when exiting `try`.
- You cannot reassign `reader` if you are using it as a resource variable-access under the *effectively final* condition.
- Reading again or continuing to write through `reader` **after it has been closed** is usually invalid for its lifecycle and may throw an exception such as `IOException`, depending on the implementation.

Illustrative example:

```java
var reader = java.nio.file.Files.newBufferedReader(path);
try (reader) {
    System.out.println(reader.readLine());
}
System.out.println(reader != null); // Variable still in scope; reader is closed.
```

The boolean print line here only checks that the reference is non-null; it does **not** say that the resource is still open. You should only check open/closed state through an appropriate API contract; many resources do not expose a public `isOpen()` or `isClosed()`.

### What does *effectively final* mean?

A local variable is considered **effectively final** when it is never reassigned according to Java's rules, even without writing the `final` keyword.

Valid example:

```java
LocalResource reusable = new LocalResource();
try (reusable) {
    System.out.println("using reusable");
}
```

The `reusable` variable is assigned once at declaration and never reassigned.

Example that **intentionally does not compile**:

```java
LocalResource reusable = new LocalResource();
reusable = new LocalResource(); // Reassigning the variable.
try (reusable) {
    System.out.println("using reusable");
}
```

Because `reusable` is reassigned, it is no longer *effectively final*. Do not fix this by adding `final` in an inappropriate place; the right way is to clearly manage a single resource reference throughout its usage scope or declare a new one directly inside `try`.

**Version note:** the `try (existingResource)` syntax does not work in Java 7/8. For Java 17+, this is valid syntax as long as the language constraints are met.

## 8. Complete Java 17+ example: resources declared inside and outside

Save the file as **`ResourceScopeDemo.java`**:

```java
public class ResourceScopeDemo {

    static final class TrackedResource implements AutoCloseable {
        private final String name;
        private boolean closed;

        TrackedResource(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        void use() {
            if (closed) {
                throw new IllegalStateException(
                        name + " is already closed");
            }
            System.out.println("use " + name);
        }

        boolean isClosed() {
            return closed;
        }

        @Override
        public void close() {
            closed = true;
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        System.out.println("CASE declared-inside");

        try (TrackedResource first = new TrackedResource("first");
             TrackedResource second = new TrackedResource("second")) {
            first.use();
            second.use();
        }

        System.out.println("CASE declared-outside");

        TrackedResource external = new TrackedResource("external");

        // Java 9+: variable outside try, not reassigned.
        try (external) {
            external.use();
        }

        System.out.println(
                "external still in scope=" + (external != null));
        System.out.println(
                "external closed=" + external.isClosed());
    }
}
```

Compile/run commands:

```bash
javac -encoding UTF-8 ResourceScopeDemo.java
java ResourceScopeDemo
```

**Exact stdout:**

```text
CASE declared-inside
open first
open second
use first
use second
close second
close first
CASE declared-outside
open external
use external
close external
external still in scope=true
external closed=true
```

### Explanation

**Case declared inside `try`:**

1. Creates `first` then `second`, printing `open first`, `open second`.
2. Inside the `try` body, both variables are in scope; calling `use` is valid.
3. Upon exiting the block, Java closes `second` before `first`, so the close lines appear in reverse order.
4. After this construct, the names `first` and `second` are no longer accessible from `main`; the program intentionally contains no out-of-scope references.

**Case declared outside `try`:**

1. `external` is created in `main`'s scope, then used with `try (external)`.
2. `external.use()` runs while the resource is open.
3. Java calls `external.close()` before reaching the last two print statements.
4. The `external` variable is still in scope, but the mock class's `isClosed()` method returns `true`. Calling `external.use()` at this point would actively throw `IllegalStateException`.

The `TrackedResource` class is written so that output does not depend on real files, operating systems, or logging policies. It also demonstrates that **variable scope** and **resource lifecycle state** are two different characteristics.

## 9. Which resources are closed when initialization fails?

Consider:

```java
try (ResourceA a = openA();
     ResourceB b = openB()) {
    process(a, b);
}
```

This is an illustrative diagram. If `openB()` throws an exception:

- `a`, which initialized successfully, will be closed.
- `b` did not initialize successfully, so there is **no** valid `b` object for Java to close under that declaration.
- The body `process(a,b)` **does not run**.
- The exception from `b`'s initializer will continue to be handled by the matching `catch` of the construct after closing already-initialized resources.
- If `a.close()` also fails, the closing exception may be recorded in the **suppressed exceptions** of the primary exception from `b`'s initializer.

It is incorrect to think that Java "only closes resources once it has entered the `try` body". Resources initialized before the failure point are still managed during exit when a later resource fails to initialize.

### Closing timing relative to `catch` and `finally`

If you write:

```java
try (LocalResource r = new LocalResource()) {
    process(r);
} catch (RuntimeException ex) {
    handle(ex);
} finally {
    afterAttempt();
}
```

this is an illustrative skeleton with appropriately defined methods. The standard sequence is:

1. Initialize the resource.
2. Execute the `try` body.
3. Close the resource when leaving the `try` body (or after an error during initialization).
4. Transfer to a matching `catch`, if an exception occurred.
5. Execute the attached `finally`, if present.

This explains why a `catch` handler can observe **errors from `close()`** even though a newly declared resource variable name is not in the handler's scope. The handler receives the **exception object**; it does not need and must not rely on access to that resource variable.

## 10. Complete Java 17+ example: body failure, close failure, and initialization failure

Save the code as **`ResourceFailureDemo.java`**:

```java
public class ResourceFailureDemo {

    static final class Tracked implements AutoCloseable {
        private final String name;
        private final boolean failOnClose;

        Tracked(String name, boolean failOnClose) {
            this.name = name;
            this.failOnClose = failOnClose;
            System.out.println("open " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);

            if (failOnClose) {
                throw new IllegalStateException(
                        "close failed: " + name);
            }
        }
    }

    static Tracked open(
            String name, boolean failOpen, boolean failClose) {
        if (failOpen) {
            System.out.println("open failed: " + name);
            throw new IllegalArgumentException(
                    "init failed: " + name);
        }

        return new Tracked(name, failClose);
    }

    static void bodyAndCloseFailure() {
        System.out.println("CASE body-and-close");

        try (Tracked first = open("A", false, true);
             Tracked second = open("B", false, true)) {
            System.out.println("body: failed");
            throw new IllegalArgumentException("body failed");

        } catch (IllegalArgumentException ex) {
            System.out.println("primary: " + ex.getMessage());
            System.out.println(
                    "suppressed count: " + ex.getSuppressed().length);

            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println(
                        "suppressed: " + suppressed.getMessage());
            }
        }
    }

    static void initializationFailure() {
        System.out.println("CASE initializer");

        try (Tracked first = open("X", false, false);
             Tracked second = open("Y", true, false)) {
            System.out.println("body: never runs");

        } catch (IllegalArgumentException ex) {
            System.out.println("caught: " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        bodyAndCloseFailure();
        initializationFailure();
    }
}
```

Run with JDK 17+:

```bash
javac -encoding UTF-8 ResourceFailureDemo.java
java ResourceFailureDemo
```

**Exact stdout:**

```text
CASE body-and-close
open A
open B
body: failed
close B
close A
primary: body failed
suppressed count: 2
suppressed: close failed: B
suppressed: close failed: A
CASE initializer
open X
open failed: Y
close X
caught: init failed: Y
```

### Result analysis

**Case where the body and both close calls throw exceptions:**

- Resource A opens first, B opens second.
- The body throws `IllegalArgumentException("body failed")`. This is the **primary exception**.
- Java calls `B.close()` first, then `A.close()`; each method throws `IllegalStateException`.
- The two closing errors are added to the primary exception's `getSuppressed()` list in the order B then A.
- `catch (IllegalArgumentException)` runs **after the closing process completes**, so it reads `getSuppressed().length == 2`.

**Case where the second initializer fails:**

- `first` initializes successfully from `open("X", false, false)`.
- `open("Y", true, false)` throws an error before creating the second `Tracked`.
- Java closes `first`; the `try` body does not execute.
- The handler catches `IllegalArgumentException("init failed: Y")`.
- The `second` object was never created, so there is no `close Y` line.

Common takeaway: successfully initialized resources are closed before the caller proceeds, regardless of whether the exit reason is an initializer error or a body error.

## 11. Scope, lifetime, ownership: three non-interchangeable questions

Three concepts are frequently confused:

| Aspect | Question | How to determine |
| --- | --- | --- |
| **Scope** | Can the current code see the resource variable name? | Java declaration and block scope rules |
| **Lifetime / closed state** | Is the resource open or closed? | Contract of `AutoCloseable` and the specific API |
| **Ownership** | Who is responsible for closing the resource? | Function/API design and ownership conventions |

Example of a method that **receives** a reader from the caller:

```java
static String readOneLine(java.io.BufferedReader reader)
        throws java.io.IOException {
    return reader.readLine();
}
```

If the caller still owns the reader and wants to read multiple times, `readOneLine` usually **should not close** a reader it does not own. Conversely, a function that opens a file itself for a single operation should usually close it with `try-with-resources` within that scope.

Example of a method that owns its reader:

```java
static String readFirstLine(java.nio.file.Path path)
        throws java.io.IOException {
    try (var reader = java.nio.file.Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
```

`reader` is only in the scope of `try`; the caller receives the `String` result without holding the resource. This helps encapsulation and reduces the risk of using a resource after closing.

Do not open a resource, directly return an object that depends on that resource, and close the resource before the caller uses it, unless the API clearly defines that the returned data is independent of the resource. For example, returning a lazy `Stream<String>` reading from a file after the reader has been closed can fail when the caller traverses the stream.

## 12. Using a resource after `try`: a remaining variable name does not mean it is still usable

With an externally declared variable:

```java
var stream = java.nio.file.Files.newInputStream(path);

try (stream) {
    System.out.println(stream.read());
}

int next = stream.read(); // Intentionally wrong regarding resource lifetime.
```

The snippet above may be **valid in terms of scope and types**, but reading after closing violates the contract of most file-reading streams and may throw `IOException`. Remove the last read line.

If a method needs to use a resource across multiple steps, group all steps that actually need the resource **before exiting `try`**:

```java
try (var stream = java.nio.file.Files.newInputStream(path)) {
    int first = stream.read();
    int second = stream.read();
    consume(first, second);
}
```

This is an **illustrative snippet**, assuming `consume` is defined and the code handles `IOException`. If data is needed after closing, read/copy the data into an independent form before leaving the block, instead of passing a still-dependent resource to the caller.

### A resource does not necessarily only "close once"

When closing wrapped streams, readers, wrappers, or resources shared across components, an object may have `close()` called on it multiple times through different management paths. Java does not guarantee that **all `AutoCloseable` classes tolerate multiple closes identically**. Read the specific resource's contract and avoid registering the same object for closing redundantly when unnecessary.

If a resource is still being used by another component, closing it in the current `try-with-resources` can break external work. Therefore, `try-with-resources` should apply to resources that the current scope **is responsible for owning and closing**.

## 13. Resources in nested `try` blocks

Multiple resource-management regions can be nested:

```java
try (OuterResource outer = openOuter()) {
    useOuter(outer);

    try (InnerResource inner = openInner(outer)) {
        useInner(inner);
    }

    continueWithOuter(outer);
}
```

This is an **illustrative structure**; the types/methods need to be defined. Meaning:

1. `outer` is opened and is in scope throughout the entire outer `try` body.
2. `inner` is opened in the inner `try`; its name is only in the inner scope.
3. Upon exiting the inner `try`, `inner` is closed.
4. `outer` is still inside the outer `try`'s managed region and can continue to be used **if the API/ownership does not cause closing `inner` to also close `outer`**.
5. Upon exiting the outer `try`, `outer` is closed.

This example emphasizes that scoping order is nested. However, an `inner` wrapper may own the `outer` resource and close it when `inner.close()` runs. In that case, `continueWithOuter(outer)` may be invalid in terms of **lifetime**, even though it is valid in terms of **scope**. Read the wrapper class's ownership contract.

## 14. Closing exceptions and when `catch` runs

An easy-to-remember model:

```text
Initialize resources in declaration order
                 ↓
          Run try body
                 ↓
Exit try: normal / return / throw
                 ↓
Close initialized resources, in reverse order
                 ↓
        Matching catch, if any
                 ↓
        Attached finally, if any
                 ↓
Continue, return value, or throw exception per final result
```

Because closing happens before a `catch` at the same level, the handler can catch exceptions thrown by `close()`. In cases where the `try` body also throws an error, the close error object is typically present as a suppressed exception on the primary error under `try-with-resources` rules.

### What if the body intends to `return` but `close()` throws an error?

Suppose:

```java
static int readValue() {
    try (ClosingResource r = new ClosingResource()) {
        return 42;
    }
}
```

This is an **illustrative skeleton**; `ClosingResource` must be a defined `AutoCloseable` class. If `close()` throws an unchecked `IllegalStateException`, the method **does not return `42`**; the closing exception can propagate. If `close()` throws a checked exception, the method must also satisfy the `catch`/`throws` contract.

Conversely, if **the body throws exception E1** and then `close()` throws E2, `try-with-resources` prioritizes E1 as the primary error and adds E2 to suppressed. This differs from a manual `finally` where throwing E2 can directly overwrite E1.

### Even if the body succeeds, `close()` can still fail

`try-with-resources` does not "swallow all close errors" to guarantee success. If there is only a close error, that error becomes the exception that is handled/propagated. Thus, a write operation might finish writing in the body but encounter an error during flush/close, leading to an overall failure; handle it based on the specific operation's contract.

## 15. API design guidelines and choosing scope

### Open resources as close to their usage scope as possible

When a step only needs a reader within one method, it is usually best to write:

```java
static long countLines(java.nio.file.Path path)
        throws java.io.IOException {
    try (var reader = java.nio.file.Files.newBufferedReader(path)) {
        long count = 0;
        while (reader.readLine() != null) {
            count++;
        }
        return count;
    }
}
```

This is an illustrative method that can be placed in a Java class. The reader is closed upon leaving the scope, even if an exception occurs while reading. The method returns a `long` independent of the reader's state, so the caller does not have to manage the resource.

### Do not extend scope just to log the resource name

If you need context in `catch`, store **appropriate descriptive data** outside the resource specification:

```java
String logicalName = "configuration";

try (var reader = java.nio.file.Files.newBufferedReader(path)) {
    System.out.println(reader.readLine());
} catch (java.io.IOException ex) {
    System.out.println("Cannot read " + logicalName);
}
```

Here `logicalName` is outside `try` so the handler can access it. There is no need to move `reader` outside just to read a descriptive string; the resource name is not in the handler's scope and the resource has already been closed before the handler runs.

### Do not accidentally close a resource you do not own

For example, `System.in` is the process's standard input stream. If a short scope closes a wrapper that owns `System.in`, other parts of the program may no longer be able to read input. Before registering a resource in `try-with-resources`, determine **who allocates it, who continues using it, and who is responsible for closing it**.

### Combine with logging and handlers at the right layer

The operation layer should manage its own reader or stream; the caller layer only needs to handle `IOException` per the contract. Do not require the caller to know what the resource is named or to call `close()` manually on a variable it does not own.

An overly broad `catch` that returns "fake success" data can hide read errors. Only choose a fallback if that is the actual policy. If the data is required, reporting the error appropriately is usually better than returning `null` or an empty string.

## 16. Common mistakes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Using a resource name declared in `try (...)` inside `catch` | The resource variable is not in the handler's scope | Use metadata declared outside; do not access the resource to close it again |
| Calling a resource after `try (existingResource)` ends | The variable may still be in scope, but the object is already closed | Perform all dependent operations before exiting `try` |
| Reassigning a resource variable declared in parentheses | The resource variable is implicitly `final` | Do not reassign; use a new variable when needed |
| Reassigning a variable and then using `try (variable)` | The local variable is no longer *effectively final* | Declare it fresh inside `try` or keep a single unassigned reference |
| Assuming `AutoCloseable` only ever throws `IOException` | `close()` can declare checked `Exception` or other types | Check the resource type's signature and `throws` contract |
| Assuming the first resource won't close if opening the second fails | Java closes resources that have already been initialized | Rely on `try-with-resources` initialization/closing semantics |
| Assuming multiple resources close left-to-right | Java closes them in reverse order | Check dependencies to manage ownership |
| Trying to catch `close()` errors by closing again in `catch` | The automatic close has already happened, and this may cause new errors | Handle exceptions, suppressed exceptions, and operational policy |
| Returning a lazy stream depending on an already-closed reader | The caller consumes data after the source is closed | Keep ownership lifetime in the right scope or return materialized data |
| Wrapping a stream and unnecessarily registering both wrapper and source for closing | May double-close and obscure ownership | Determine which class closes the underlying source |
| Closing a resource borrowed from the caller | Can break the caller's work | Agree on the contract for who closes the resource |
| Ignoring suppressed exceptions when both body and close fail | Loses context on secondary closing failures | Inspect `getSuppressed()` when diagnosing |

## 17. Self-check exercises

**Exercise A.** Can a resource declared as `try (var reader = open())` be used in a `catch` at the same level?

**No.** The name `reader` is not in `catch`'s scope. However, exceptions from initializing, reading, or closing the reader can still reach the appropriate handler.

**Exercise B.** Is a `reader` variable declared before `try (reader)` (Java 17) still in scope after the construct?

**Yes**, according to its outer declaration scope. However, the reader has already been closed; you should not keep reading just because the variable name is still usable.

**Exercise C.** In `try (R a = openA(); R b = openB())`, which resource is closed first?

**`b`**, then `a`, if both were successfully initialized.

**Exercise D.** `openA()` succeeds, `openB()` throws an error. Does the `try` body run, and does `a` close?

**The body does not run; `a` is closed.** If `a.close()` also fails, the close error may be suppressed under `b`'s initialization error.

**Exercise E.** Can you write `try (resource)` when `resource` is a local variable that has been reassigned?

**No** under this Java 9+ syntax: the local variable must be `final` or *effectively final*. Use a new non-reassigned variable or declare it directly in the resource specification.

**Exercise F.** `close()` throws an `IllegalStateException` while the `try` body already threw `IllegalArgumentException`. With `try-with-resources`, which error is the primary error?

Typically **`IllegalArgumentException` from the `try` body** is the primary error; the close error appears in its `getSuppressed()`.

**Exercise G.** The `try` body prepares to `return 42`, but the resource's `close()` throws an error. Is the caller guaranteed to receive `42`?

**No.** If the error from `close()` is not handled, the call may terminate with an exception instead of returning `42`.

**Exercise H.** A reader wraps an input stream and closes the input stream itself when the reader closes. Is it necessary to declare both in the resource list?

**Not necessarily.** If the reader owns and closes the stream, registering only the reader is usually sufficient. Read the class contract and ownership rules to avoid repeated closing or use-after-close.

**Exercise I.** Can a resource variable declared in the resource specification mutate the object's state?

**Yes**, if the API allows it. An implicitly `final` resource variable only forbids **reassigning the reference**, not making the object immutable.

**Exercise J.** Should a method receiving a caller-owned reader close it in all cases?

**Not by default.** Decide based on the ownership contract. A method borrowing a reader to read from it usually should not close it if the caller still needs to use it.

## 18. Checklist for applying in a Java project

Before writing `try-with-resources`, check:

1. **Does the resource implement `AutoCloseable`?** If not, it is not a valid resource for this syntax.
2. **Who owns the resource?** Should the current scope close it when finished?
3. **Where should the variable be declared?** Declare it fresh in `try` parentheses if used only locally; use `try (existingResource)` when an outer variable is `final`/*effectively final* and the lifecycle management goal fits.
4. **Are all operations needing the resource placed before the block ends?** Do not return an object that still depends on a closed resource.
5. **Are there multiple resources?** Verify left→right initialization and right→left closing order, especially with wrappers that own their sources.
6. **Can an initializer throw an error?** Previously initialized resources will be closed; the `try` body may never have run.
7. **What checked exceptions can `close()` throw?** Identify the static type and `throws` signature to handle.
8. **Is `catch` running at the right time?** Resources are closed before a same-level handler receives the error.
9. **Do suppressed exceptions need investigation?** When both body and close fail, do not just look at the primary message and miss the cleanup status.
10. **Is the resource variable reassigned?** Variables declared in the resource specification are implicitly `final`; outer variables must remain `final`/*effectively final* when using `try (variable)`.
11. **Does the caller know how to handle errors?** Low layers manage resources; the appropriate layer decides recovery, error return, or retry.
12. **Is the resource used after closing?** Scope and lifetime are not the same. Stop using a resource once its managed region ends.

## Conclusion

`try-with-resources` binds a **resource's lifetime** to a **defined execution region**. When declaring a new resource in `try (...)`, the variable name can be used within the resource specification and the `try` body, but not in `catch`, `finally`, or statements after the construct. When using `try (existingResource)` from Java 9 onward, the outer variable may still be in scope, but **the object has already been closed**. With multiple resources, Java **initializes left-to-right, closes right-to-left**, closes already-opened resources if a later initializer fails, and provides **suppressed exceptions** so the primary error is not lost when closing a resource also fails.

Understanding **scope, lifetime, and ownership** helps you write Java code that honors contracts, avoids using resources after closing, and prevents resource leaks and masked errors.
