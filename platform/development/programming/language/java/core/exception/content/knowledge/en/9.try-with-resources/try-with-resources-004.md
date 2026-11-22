# Using an Existing `final` or *Effectively Final* Resource Since Java 9

## 1. Learning Objectives

`try-with-resources` is a Java syntax that **automatically calls `close()`** on resources implementing `AutoCloseable` when exiting the `try` scope. Since Java 7, this construct has supported declaring new resources directly inside the `try` parentheses. **Since Java 9**, Java added the ability to reference **an already-existing resource variable** directly, provided that the variable is `final` or *effectively final*.

Key example:

```java
java.io.BufferedReader reader =
        new java.io.BufferedReader(new java.io.StringReader("hello"));

try (reader) { // Valid since Java 9 if reader is effectively final.
    System.out.println(reader.readLine());
}
```

This is a **code snippet** placed inside a method that declares or handles `IOException`. There is no need to redeclare `BufferedReader` in the parentheses, and no need to create an alias variable just to pass it into `try-with-resources`.

After completing this lesson, you will be able to:

- Write the correct syntax for `try (resource)`, `try (first; second)`, and combine existing resources with newly declared resources.
- Distinguish between explicit `final` and *effectively final*; recognize reassignment patterns that cause compilation errors.
- Explain that resources are closed on normal completion, `return`, or thrown exceptions, in reverse order.
- Understand that the resource variable **remains in scope** after `try`, even though the resource object may already be closed.
- Understand exception handling in `close()`, especially *suppressed exceptions*.
- Avoid double closing, reusing a closed resource, improper ownership sharing, and mistakenly using expressions that are not variable accesses.
- Accurately distinguish Java 7/8 from the language enhancement in Java 9; run examples on JDK 17+.

## 2. Review of `try-with-resources` Before Java 9

`try-with-resources` was introduced in **Java 7**. At that time, the resource list inside the parentheses had to contain **resource variable declarations**. For example:

```java
try (java.io.BufferedReader reader =
             new java.io.BufferedReader(new java.io.StringReader("A\nB"))) {
    System.out.println(reader.readLine());
}
```

This is a **code snippet** inside a method that can handle or declare `IOException`. At the end of the block, Java automatically calls `reader.close()`; you do not need to add `finally { reader.close(); }`.

Resource type requirement: the declared expression must have a type compatible with `java.lang.AutoCloseable`. `Closeable` classes are also compatible because `java.io.Closeable` extends `AutoCloseable`.

Before Java 9, if a variable was already declared **outside**:

```java
java.io.BufferedReader reader =
        new java.io.BufferedReader(new java.io.StringReader("A"));

try (java.io.BufferedReader managed = reader) {
    System.out.println(managed.readLine());
}
```

Java 7/8 allowed using a **newly declared variable in the header** such as `managed` to manage the same object that `reader` points to. This mechanism works, but it introduces an extra variable name and can mislead readers into thinking there are two independent readers. In reality, `managed` and `reader` are two references to the **same object**; that object is closed upon exiting the block.

### Changes in Java 9

Java 9 accepts **direct access to a previously declared variable**:

```java
java.io.BufferedReader reader =
        new java.io.BufferedReader(new java.io.StringReader("A"));

try (reader) {
    System.out.println(reader.readLine());
}
```

In the new syntax, `reader` is a *variable access*, not a new resource declaration. The core requirement is that **the accessed variable must be `final` or effectively final**, must have been properly assigned a value before entering `try`, and must have a resource type compatible with `AutoCloseable`.

Quick comparison:

| Aspect | Java 7/8 | Java 9+ |
| --- | --- | --- |
| Declare a resource directly in the header | `try (BufferedReader r = open())` | Still valid |
| Use a previously declared variable | Use an alias: `try (BufferedReader managed = reader)` | `try (reader)` if eligible |
| Must write explicit `final`? | Not required for a new declaration | No, `effectively final` also works |
| Resource closed automatically? | Yes | Yes |
| Closing order with multiple resources? | Reverse of declaration order | Reverse of listing/management order |
| Handling `close()` errors and suppressed exceptions? | Yes | Unchanged |
| Externally declared variable still in scope after `try`? | Yes | Yes |

**Important:** Java 9 **did not** change the requirement that a resource must support `AutoCloseable`, nor did it change the closing rules. The only new addition is allowing an expression form that references an **existing resource variable**.

## 3. What Do `final` and *Effectively Final* Mean?

### 3.1. Explicit `final` Variables

A local variable declared with `final` cannot be reassigned after it has been initialized:

```java
final java.io.BufferedReader reader =
        new java.io.BufferedReader(new java.io.StringReader("input"));

try (reader) {
    System.out.println(reader.readLine());
}
```

This example is a **code snippet** that must be inside a method handling or declaring `IOException`. This usage is valid from Java 9 onward.

`final` applies to the **reference variable**; it does not make the object's contents immutable. While the resource is open, calling `reader.readLine()` still changes the reader's read position; when leaving `try`, the language mechanism still calls `close()`.

### 3.2. *Effectively Final* Variables

A local variable **without the `final` keyword** that is not reassigned after its valid initialization is considered *effectively final*:

```java
java.io.BufferedReader reader =
        new java.io.BufferedReader(new java.io.StringReader("input"));

// No reader = ... statement anywhere afterward.
try (reader) {
    System.out.println(reader.readLine());
}
```

Java 9+ accepts this code. The compiler determines whether a variable is effectively final based on **assignments in the code**, not on the programmer's intention or whether a reassignment line actually executes during a test.

Several distinctions to keep in mind:

- A variable `reader` may omit `final` and still be effectively final.
- You can **call methods that mutate the object's state** through `reader` without losing its effectively final status.
- Reassigning the variable itself with `reader = anotherReader;` or `reader = null;` makes it no longer effectively final.
- This condition is evaluated across the variable's relevant scope, **not only the statements before `try`**. Reassigning the variable after exiting `try` can also cause the compiler to reject `try (reader)`.
- Do not equate effectively final with `AutoCloseable`, object immutability, or thread-safety. These are independent concepts.

### 3.3. Intentionally Non-Compiling Example: Reassigning a Resource

The **`InvalidReassignment.java`** file below is **intentionally incorrect**:

```java
import java.io.StringReader;

public class InvalidReassignment {
    public static void main(String[] args) {
        StringReader reader = new StringReader("first");
        reader = new StringReader("second");

        try (reader) { // ERROR: reader is not effectively final.
            System.out.println(reader.read());
        }
    }
}
```

Check command:

```bash
javac InvalidReassignment.java
```

The compiler rejects it because the variable used as a resource **is neither final nor effectively final**. The exact message may vary between `javac` versions. Do not run `java InvalidReassignment` expecting a successful program, because the code does not compile.

In real programs, you must also avoid creating a first resource and then **losing the reference needed to close it** when overwriting it with a second resource. The solution is not adding `try (reader)` at the end, because the old resource is no longer managed. Manage each resource within its appropriate scope.

### 3.4. Reassignment After `try` Can Still Make the Code Invalid

**Intentionally incorrect** snippet:

```java
java.io.StringReader reader = new java.io.StringReader("A");
try (reader) {
    System.out.println(reader.read());
}
reader = new java.io.StringReader("B"); // reader is not effectively final.
```

With `try (reader)`, the effectively final requirement applies to the variable throughout its scope. Reassigning it **after** the block does not "restore" validity.

If you need to reuse a variable name for a new resource, use separate variables or separate scopes to keep ownership of each resource clear.

## 4. Runnable Example: Using an Existing Variable After Closing the Resource

Create the file **`ExistingResourceDemo.java`**:

```java
public class ExistingResourceDemo {
    static class TrackedResource implements AutoCloseable {
        private final String name;
        private boolean closed;

        TrackedResource(String name) {
            this.name = name;
        }

        void use() {
            if (closed) {
                throw new IllegalStateException("already closed");
            }
            System.out.println("using " + name);
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
        TrackedResource resource = new TrackedResource("A");

        try (resource) {
            resource.use();
        }

        System.out.println("resource closed: " + resource.isClosed());
    }
}
```

Compile/run with JDK 17+:

```bash
javac ExistingResourceDemo.java
java ExistingResourceDemo
```

`stdout`:

```text
using A
close A
resource closed: true
```

**Analysis:**

1. `resource` is declared **before** the `try` header.
2. The variable does not have the `final` keyword, but it is assigned exactly once and never reassigned, so it is effectively final.
3. `try (resource)` begins managing the lifecycle of the existing resource; it does not create a new `TrackedResource` object.
4. When the body completes normally, Java calls `resource.close()`. The example prints `close A`.
5. The variable `resource` remains in scope after `try`, so `resource.isClosed()` can still be called and returns `true`.

The last point is crucial: **still in scope does not mean still open**. After `try`, the variable still points to the same object, but the object has been closed. Calling `resource.use()` again will throw `IllegalStateException` according to the example's self-defined contract.

### Responsibility of the Resource User

When you pass an existing resource into `try (resource)`, you are accepting that **the block will close the resource**. If the resource is managed by another component and must remain open after the call, you cannot arbitrarily use `try (resource)` and ignore the ownership contract.

Practical examples: do not arbitrarily close an `InputStream` owned by a framework, a container-managed HTTP request, or a connection shared across a lifecycle longer than the current scope.

## 5. Using an Explicit `final` Variable: Standalone Example

Create the file **`ExplicitFinalResourceDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public class ExplicitFinalResourceDemo {
    public static void main(String[] args) throws IOException {
        final BufferedReader reader =
                new BufferedReader(new StringReader("alpha\nbeta"));

        try (reader) {
            System.out.println(reader.readLine());
            System.out.println(reader.readLine());
        }

        System.out.println("finished reading");
    }
}
```

```bash
javac ExplicitFinalResourceDemo.java
java ExplicitFinalResourceDemo
```

`stdout`:

```text
alpha
beta
finished reading
```

`BufferedReader.readLine()` can throw `IOException`; the `close()` operation is also managed automatically. `main throws IOException` satisfies checked exception checking. `StringReader` provides in-memory data for deterministic output without depending on the filesystem.

The `reader` variable still exists after `try`, but the reader has been closed. The `finished reading` line does not attempt to read from the resource again. Do not infer from the variable's continued existence that you can keep performing I/O through it.

## 6. Multiple Existing Resources: Right-to-Left Closing Order

When managing multiple resources in one header, each resource must satisfy the type requirement and the final/effectively final requirement. Java closes them in **reverse order** of their declaration or listing in the header.

Create the file **`ExistingResourcesOrderDemo.java`**:

```java
public class ExistingResourcesOrderDemo {
    static class Tracked implements AutoCloseable {
        private final String name;

        Tracked(String name) {
            this.name = name;
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        Tracked first = new Tracked("first");
        final Tracked second = new Tracked("second");

        try (first; second) {
            System.out.println("body");
        }

        System.out.println("after try");
    }
}
```

```bash
javac ExistingResourcesOrderDemo.java
java ExistingResourcesOrderDemo
```

`stdout`:

```text
body
close second
close first
after try
```

Explanation:

- `first` is effectively final; `second` is explicitly final.
- `try (first; second)` manages both, even though they were created **before** the `try` statement.
- When the block ends, `second`'s `close()` is called before `first`'s `close()`.
- This rule matters for dependent resources: if `second` wraps `first`, design ownership and closing order accordingly.

The header also allows an optional **trailing semicolon**; for example, `try (first; second;)` is valid. However, using semicolons as separators between resources is clearest.

### What Are the Risks of Creating Resources Before `try`?

Consider:

```java
Resource first = openFirst();
Resource second = openSecond(); // May fail.
try (first; second) {
    work();
}
```

This is an **illustrative snippet**, not a standalone program; the types/methods are undeclared. If `openSecond()` throws an exception before executing `try`, the program **has not yet entered the resource-management scope of try-with-resources**. `first` may still remain open and would need to be handled by an outer management scope.

This is a drawback worth considering when creating multiple resources before the header. The common safe approach is to declare resources directly inside a single `try-with-resources`:

```java
try (Resource first = openFirst();
     Resource second = openSecond()) {
    work();
}
```

This is also an **illustrative snippet** requiring `Resource` and the corresponding methods to be declared. When `openSecond()` fails **during initialization of the header's resources**, Java automatically closes the `first` resource that was already initialized and managed.

**Conclusion:** Java 9's shorter syntax does not mean it is always better than declaring resources in the header. Consider **when the resource is created** and **which scope is responsible for closing it**.

## 7. Combining Existing Resources with Resources Declared in the Header

Java 9+ can combine both kinds of elements in the resource list:

```java
java.io.StringReader source = new java.io.StringReader("first\nsecond");

try (source;
     java.io.BufferedReader buffered =
             new java.io.BufferedReader(source)) {
    System.out.println(buffered.readLine());
}
```

This is a **code snippet** inside a method that declares/handles `IOException`. `source` already exists and is effectively final; `buffered` is a newly declared resource variable in the header. When exiting the block, Java closes `buffered` first, then closes `source`.

However, watch out for **nested ownership**: `BufferedReader.close()` also closes the reader it wraps. Therefore, this example may call `close()` on `source` more than once. Some implementations handle repeated closing, but not every `AutoCloseable` guarantees idempotency. In applications, you should usually manage only the **wrapper that owns the delegate** once:

```java
java.io.StringReader source = new java.io.StringReader("first\nsecond");

try (java.io.BufferedReader buffered =
             new java.io.BufferedReader(source)) {
    System.out.println(buffered.readLine());
}
```

This is a Java 7+ style illustrative snippet in which closing `buffered` closes the underlying `source`. When choosing the combined syntax, clearly identify who owns the underlying resource to avoid double closing.

### Combining Two Independent Resources

When you genuinely need to mix both header forms without wrapper/delegate risks, you can use two resources that do not wrap each other. Create the file **`MixedResourcesDemo.java`**:

```java
public class MixedResourcesDemo {
    static class Tracked implements AutoCloseable {
        private final String name;

        Tracked(String name) {
            this.name = name;
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        Tracked existing = new Tracked("existing");

        try (existing; Tracked temporary = new Tracked("temporary")) {
            System.out.println("working");
        }

        System.out.println("done");
    }
}
```

```bash
javac MixedResourcesDemo.java
java MixedResourcesDemo
```

`stdout`:

```text
working
close temporary
close existing
done
```

`existing` is referenced directly using the Java 9 feature; `temporary` is declared inline as in Java 7. The two resources are closed in reverse order of the header list. The `temporary` variable does not exist outside `try`; the `existing` variable still exists in the outer scope, but its resource is closed.

## 8. `try-with-resources` Closing on Normal Completion, `return`, and Exceptions

The closing mechanism does not depend on whether the `try` body completes normally. When exiting via `return`, `break`, `continue`, or an exception, Java performs closing according to the `try-with-resources` rules.

Create the file **`EarlyReturnResourceDemo.java`**:

```java
public class EarlyReturnResourceDemo {
    static class Tracked implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("close called");
        }
    }

    static int calculate() {
        Tracked resource = new Tracked();

        try (resource) {
            System.out.println("inside");
            return 7;
        }
    }

    public static void main(String[] args) {
        System.out.println("returned=" + calculate());
    }
}
```

```bash
javac EarlyReturnResourceDemo.java
java EarlyReturnResourceDemo
```

`stdout`:

```text
inside
close called
returned=7
```

The `return 7` statement prepares the result first, the resource is closed, and then the caller receives `7`. If `close()` throws an exception while a `return` is pending, the close exception can cause the call to terminate with an error instead of returning the expected value.

**Distinguish** between the variable remaining in scope after `try` and the timing of `close()`: the resource is closed **when leaving the `try-with-resources` block**, not when the local variable goes out of scope or when the garbage collector runs.

### Null Resources in Java 9

A resource variable of a compatible type that holds `null` can still appear in the header. Java does not call `close()` on a null reference. For example:

```java
AutoCloseable resource = null;
try (resource) {
    System.out.println("body runs");
}
```

This is an **illustrative snippet** that may require handling/declaring checked `Exception` depending on the resource's static type, because `AutoCloseable.close()` declares `throws Exception`. The `try` body still runs, and there is no object to close at the end. Even though the language allows it, using null to mean "no resource" should not mask a bug where a required resource is missing.

## 9. Exceptions in `close()` and *Suppressed Exceptions*

A resource is only closed automatically if execution actually passes through the `try-with-resources` closing mechanism. When `close()` throws an exception, Java does not simply ignore that error.

There are three main scenarios:

1. The `try` body completes normally, and `close()` throws an exception: the exception from `close()` propagates out (if uncaught).
2. The `try` body throws an exception, and then `close()` also throws: the exception from the **`try` body** is typically kept as the primary exception; the close exception is added to the **suppressed** list.
3. Multiple resources are present: they are still closed one by one in reverse order; subsequent close exceptions can become suppressed exceptions on the primary exception according to language rules.

This differs from a manual `finally` block where a `close()` call in `finally` throws a new exception and accidentally masks the original error.

### Runnable Example: Preserving Both the Body Exception and the Close Exception

Create the file **`SuppressedCloseDemo.java`**:

```java
public class SuppressedCloseDemo {
    static class ExplodingResource implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("close failed");
        }
    }

    public static void main(String[] args) {
        ExplodingResource resource = new ExplodingResource();

        try (resource) {
            throw new IllegalArgumentException("body failed");
        } catch (IllegalArgumentException failure) {
            System.out.println("primary: " + failure.getMessage());
            System.out.println("suppressed count: "
                    + failure.getSuppressed().length);
            System.out.println("suppressed: "
                    + failure.getSuppressed()[0].getMessage());
        }
    }
}
```

```bash
javac SuppressedCloseDemo.java
java SuppressedCloseDemo
```

`stdout`:

```text
primary: body failed
suppressed count: 1
suppressed: close failed
```

`resource` is an effectively final variable created before `try`. The exception from the `try` body is `IllegalArgumentException`; the exception from `close()` becomes suppressed. This information can be inspected via `getSuppressed()`; when diagnosing resource errors, check the primary exception, its cause, and its suppressed exceptions.

If `close()` can throw a **checked exception**, the compiler requires catching or declaring that type, even if nothing inside the `try` body throws a checked exception. This rule **does not change** just because the resource is referenced using Java 9 syntax.

### Checked Exception Example on Close

Create the file **`CheckedCloseDemo.java`**:

```java
import java.io.IOException;

public class CheckedCloseDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("closing");
            throw new IOException("cannot close");
        }
    }

    public static void main(String[] args) {
        Resource resource = new Resource();

        try (resource) {
            System.out.println("processing");
        } catch (IOException failure) {
            System.out.println("caught: " + failure.getMessage());
        }
    }
}
```

```bash
javac CheckedCloseDemo.java
java CheckedCloseDemo
```

`stdout`:

```text
processing
closing
caught: cannot close
```

`Resource.close()` declares `throws IOException`; the implicit close call generated by the language at the end of `try` still participates in checked exception checking. There is no need to call `resource.close()` manually in the `try` body.

## 10. Things **Not** Allowed by Java 9

The Java 9 feature does not accept an arbitrary expression in the resource list. A resource element using the new reference syntax must be a valid **variable access**, such as a local variable name or a field that meets the language rules.

**Intentionally non-compiling** example:

```java
try (new java.io.StringReader("A")) {
    // Cannot write a new expression directly in the resource header.
}
```

To create a new resource in the header, use a **resource declaration**:

```java
try (java.io.StringReader reader = new java.io.StringReader("A")) {
    System.out.println(reader.read());
}
```

Both are **illustrative snippets**; the first is a syntax error, while the second is valid when placed inside an appropriate Java method/class.

### Static Type Must Implement `AutoCloseable`

This snippet is **intentionally non-compiling**:

```java
Object resource = new java.io.StringReader("A");
try (resource) {
    System.out.println("read");
}
```

Even though the runtime object is a `StringReader`, the **static type** of the `resource` variable is `Object`, which is not a subtype of `AutoCloseable`. The resource specification is rejected by the compiler. Declare the variable with an appropriate type, such as `StringReader`, `Reader`, `Closeable`, or `AutoCloseable`, depending on the API you need to use.

### `final` Does Not Mean the Resource Stays Open Forever

You can write `final StringReader reader = ...`, but when using `try (reader)`, **the object will still be closed**. `final` only guarantees that the variable cannot be reassigned; it does not prevent `close()` from being called and does not make the resource state immutable.

### Do Not Use the Same Object in Two Positions Without Understanding Close Semantics

If two different variables point to **the same `AutoCloseable` object**, a header like `try (first; second)` can call `close()` on **that same object twice**. Java guarantees that the close operations are executed according to the resource list, but does not guarantee that every implementation accepts repeated closing or has no side effects.

Manage ownership clearly, especially with wrapped or shared resources.

## 11. Testing the Java 8 vs. Java 9 Version Boundary

The `try (resource)` feature was introduced in **Java 9**. When using JDK 17, you can instruct the compiler to target a specific language level and API using the `--release` option.

Assuming the `ExistingResourceDemo.java` file from Section 4 is saved:

```bash
javac --release 9 ExistingResourceDemo.java
java ExistingResourceDemo
```

The program compiles and runs successfully because Java 9 already supports this syntax. You can also use `--release 17` or compile normally on JDK 17.

Try:

```bash
javac --release 8 ExistingResourceDemo.java
```

The compilation command will **fail with an error** because direct variable-access resource syntax is not supported at the Java 8 source level. The exact message depends on the compiler; do not treat this as a successful build.

If you are maintaining source code that must remain compatible with Java 8, use the resource declaration form in the header:

```java
TrackedResource resource = new TrackedResource("A");
try (TrackedResource managed = resource) {
    managed.use();
}
```

This is an **illustrative snippet in a context where the `TrackedResource` class** from Section 4 is available. The `managed` alias form works in Java 7/8 and later versions. It closes the exact object that `resource` and `managed` both point to, without creating a new independent resource.

Do not confuse **the JDK version you are running** with **the source language level configured for the project**. You can run JDK 17 while building with `--release 8`, and Java 9 syntax will still be invalid in that project.

## 12. Resource Fields: More Caution Needed Than Local Variables

Java 9 allows certain forms of **field** access in a resource specification when language rules are satisfied, such as a field declared `final` with a valid resource type. However, special care is needed when a field holds a long-lived resource tied to an object's lifecycle.

Conceptual code snippet:

```java
class ReaderOwner {
    private final java.io.StringReader reader =
            new java.io.StringReader("data");

    void readOnce() throws java.io.IOException {
        try (this.reader) {
            System.out.println(reader.read());
        }
    }
}
```

This is a **class definition for illustration**, without `main`. `this.reader` is a `final` field access, which differs from an effectively final local variable. After the first `readOnce()` call, the `reader` field still points to a closed object. Calling `readOnce()` again may fail when attempting to read because the resource is no longer open.

**Design consideration:** if a field owns a long-lived resource, it is usually better to let a lifecycle-management method such as `close()` on the owning class close it at the appropriate time, rather than closing it silently during a short method call. Distinguish between language-level `final` access and resource ownership/lifecycle.

## 13. Common Misconceptions

**“Only variables written with the `final` keyword can be used in `try (resource)`.”** False. Java 9+ allows *effectively final* local variables, meaning they are not reassigned even without the keyword.

**“You can reassign the resource after `try` because the block has already ended.”** False with respect to effectively final: the compiler checks assignments to the variable across the relevant scope, not just before the `try` statement.

**“If you call `reader.readLine()`, `reader` is no longer effectively final.”** False. Calling a method changes **the object's state**, not a reassignment of **the reference variable**.

**“Using `try (reader)` creates a copy of `reader`.”** False. It manages **the exact object** being referenced; it does not clone the resource.

**“If the variable is still visible after `try`, the resource is still open.”** False. The object may already be closed; variable scope and open resource lifetime are two different things.

**“Once a resource is declared before `try`, any error during resource initialization is managed by `try-with-resources`.”** False. If an error occurs **before entering `try`**, that `try`'s auto-closing mechanism has not taken effect yet. This is why declaring resources directly in the header remains very useful.

**“Resources are closed from left to right.”** False. Java closes them in reverse order, from right to left in the header.

**“With `try-with-resources`, `close()` errors are ignored.”** False. The error may propagate out or be recorded as a *suppressed exception* if a primary exception already exists.

**“A variable of type `Object` is accepted as long as the runtime object has `close()`.”** False. Resource type checking happens at compile time; the static type must be compatible with `AutoCloseable`.

**“Java 9 allows `try (new MyResource())`.”** False. A bare object-creation expression is not a valid resource variable access; declare a new resource instead: `try (MyResource r = new MyResource())`.

**“Using the same resource in two slots of the header will be automatically detected and closed only once.”** False. Do not rely on deduplication during closing. Avoid managing two aliases to the same object without understanding the `close()` contract.

**“A closed `StringReader` can still be read because its data is in RAM.”** False. The reader's contract still governs its closed state; having data in memory does not mean you can read indefinitely after `close()`.

## 14. Self-Check Exercises

1. **When is `BufferedReader r = ...; try (r) { ... }` valid in Java 17?** When `r` is definitely assigned before `try`, has a type compatible with `AutoCloseable`, and is `final` or effectively final.
2. **Without the `final` keyword and with no reassignment, will the compiler accept it?** Yes, it is effectively final.
3. **What happens if you write `r = anotherReader;` after `try (r)`?** The variable is no longer effectively final; the compiler can reject the resource specification.
4. **Can you mutate the resource's state inside `try`?** Yes, if the API allows it. The effectively final requirement only constrains **variable** assignment.
5. **After `try (r)`, is the variable `r` still in scope?** Yes, if it was declared in an outer scope; however, the object has already been closed.
6. **In what order does `try (a; b)` close resources?** `b` first, then `a`.
7. **Is `try (new FileInputStream(path))` valid directly since Java 9?** No; it requires a resource declaration or a valid existing variable.
8. **If `close()` throws while the `try` body has already thrown an exception, what usually happens?** The body exception is the primary exception, and the close exception is suppressed; inspect with `getSuppressed()`.
9. **If creating resource A succeeds and creating B fails before `try (a; b)`, is A automatically closed by this `try`?** No, because execution has not yet entered the `try` block's auto-management scope.
10. **For Java 8, how do you use an externally declared resource?** Create a new resource variable in the header, for example `try (Reader managed = reader)`.
11. **Does using a `final` variable make the resource immutable?** No, it only prevents the reference from being reassigned.
12. **If `AutoCloseable.close()` declares a checked exception, does Java 9 syntax remove the `catch/throws` requirement?** No. The caller still needs to handle or declare the appropriate checked exception.
13. **Should you close a framework-managed connection using `try (connection)`?** Only if the ownership contract permits it; if the framework manages the lifecycle, closing it yourself can be wrong.

## 15. Official References

- [Java Language Specification 17 — §14.20.3, try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): resource syntax and semantics, automatic closing, closing order, and suppressed exceptions.
- [Java Language Specification 17 — §4.12.4, final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): `final` and effectively final variables.
- [Java SE 17 API — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): the `close()` contract and notes on idempotency.
- [Java SE 17 API — Closeable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html): I/O resource closing variant.
- [Java SE 17 API — Throwable.getSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getSuppressed()): inspecting suppressed exceptions.
- [JEP 213 — Milling Project Coin](https://openjdk.org/jeps/213): `try-with-resources` syntax enhancement using existing resource variables since Java 9.

**Key takeaway:** Since Java 9, you can write `try (resource)` for an **existing** resource variable if the variable is `final` or *effectively final* and has a type compatible with `AutoCloseable`. Java automatically closes **the referenced object** when exiting the block; the variable may remain in scope, but the resource is no longer open. Syntactic conciseness does not replace proper management of ownership, resource creation timing, and exceptions from `close()`.
