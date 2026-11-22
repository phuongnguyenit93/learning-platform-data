# `null` Resources and Automatic `close()` Calls in Java try-with-resources

In Java, **try-with-resources** is the `try (...) { ... }` construct used to manage resources that implement `AutoCloseable`. Upon exiting the block, Java automatically **attempts to call `close()` on resources that were successfully initialized and have a non-`null` reference**. If a resource variable has the value **`null`**, Java **skips calling `close()` for that resource**; a resource being `null` alone does **not** cause the try-with-resources statement to throw a `NullPointerException`.

Short rule:

> **A `null` resource is not closed; a non-`null` resource is attempted to be closed upon exiting scope.** Automatic closing does not turn a `null` variable into a valid object and does not prevent a `NullPointerException` if code inside the `try` body attempts to use the `null` reference.

This lesson explains the nature of automatic `close()` calls, the difference between a **`null` resource** and **resource initialization failing due to an exception**, how Java closes multiple resources, the relationship with `catch`/`finally`, resource-closing errors, checked exception rules, and how to design APIs that avoid confusing situations.

## 1. Recap of the try-with-resources Construct

A typical construct:

```java
try (SomeResource resource = openResource()) {
    useResource(resource);
}
```

This is **illustrative skeleton code**, in which `SomeResource` must implement `AutoCloseable` and the two helper methods must be defined. At runtime, Java proceeds as follows:

1. Evaluates the expression `openResource()` and initializes the variable `resource`.
2. If initialization succeeds, enters the `try` body.
3. Upon exiting the `try` body—whether normally, via `return`, or via an exception—Java **attempts to close** the resource if the reference is non-`null`.
4. After closing, Java moves to the `catch` or `finally` attached to that construct if present, or continues/propagates along the corresponding path.

The initialization order of resources is **left to right**, and the closing order is **the reverse, right to left**. Java only manages resources that have been successfully initialized; the `null`-reference check determines whether `close()` is actually called on each resource.

**`AutoCloseable` does not mean closing is guaranteed to succeed.** `close()` can throw an exception, and try-with-resources applies the rules for primary and suppressed exceptions to handle that case.

## 2. Is a Resource Assigned `null` Valid?

Yes. Java allows declaring a resource variable with an expression of a compatible type whose runtime value is `null`. For example:

```java
try (MyResource resource = null) {
    System.out.println("Thân try vẫn chạy");
}
```

This is an **illustrative snippet**, requiring the `MyResource` class to implement `AutoCloseable` in order to compile. In this case:

- The resource declaration is evaluated normally and results in a `null` reference.
- The `try` body **still runs**; Java does not treat a `null` resource as a failure condition on its own.
- Upon exiting the block, Java **does not call** `resource.close()` because the reference is `null`.
- No `NullPointerException` is thrown solely due to automatic cleanup.
- If inside the `try` body you immediately call `resource.read()`, Java may throw a `NullPointerException` due to **dereferencing `null`**, which is a separate issue from the closing mechanism.

Some APIs are designed to represent "no resource" using `null`, but this is not a good default for every program. In an API that requires a mandatory resource, returning `null` may violate the contract and should be handled separately, for example with a clear error message.

## 3. Complete Java 17 Example: `null` Is Not Closed

Save the following program as **`NullResourceDemo.java`**:

```java
public class NullResourceDemo {
    static class TrackedResource implements AutoCloseable {
        private final String name;

        TrackedResource(String name) {
            this.name = name;
            System.out.println("Tạo: " + name);
        }

        void work() {
            System.out.println("Dùng: " + name);
        }

        @Override
        public void close() {
            System.out.println("Đóng: " + name);
        }
    }

    static TrackedResource openOrNull(boolean available) {
        if (!available) {
            System.out.println("Không tạo tài nguyên");
            return null;
        }
        return new TrackedResource("R");
    }

    static void execute(boolean available) {
        try (TrackedResource resource = openOrNull(available)) {
            System.out.println("resource == null: " + (resource == null));
            if (resource != null) {
                resource.work();
            } else {
                System.out.println("Bỏ qua thao tác cần tài nguyên");
            }
        }
        System.out.println("Sau try-with-resources");
    }

    public static void main(String[] args) {
        execute(false);
        System.out.println("---");
        execute(true);
    }
}
```

Compile/run with Java 17 or later:

```bash
javac -encoding UTF-8 --release 17 NullResourceDemo.java
java NullResourceDemo
```

**Exact stdout** with a UTF-8 console:

```text
Không tạo tài nguyên
resource == null: true
Bỏ qua thao tác cần tài nguyên
Sau try-with-resources
---
Tạo: R
resource == null: false
Dùng: R
Đóng: R
Sau try-with-resources
```

With `execute(false)`, the initialization expression returns `null`. The `try` body runs, the "no resource" handling branch is taken, and there is no `Đóng: R` line because there is no object to close.

With `execute(true)`, the `TrackedResource` is created, used, and closed upon exiting the block. The statement after the construct only runs after the closing step, provided `close()` completes normally.

Core takeaway: **Java automatically checks that a resource is non-`null` before calling `close()`, so you do not need to write an `if (resource != null)` just to guard against an NPE in the closing step**. However, checking before **using** the resource may still be necessary if the contract allows `null`.

## 4. Null-Safe Cleanup Is Not Null-Safe Usage

Consider the program **`NullUsageDemo.java`**:

```java
public class NullUsageDemo {
    static class Resource implements AutoCloseable {
        void use() {
            System.out.println("Đã dùng");
        }

        @Override
        public void close() {
            System.out.println("Đã đóng");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = null) {
            System.out.println("Vào try");
            resource.use();
            System.out.println("Sau use");
        } catch (NullPointerException e) {
            System.out.println("Bắt NullPointerException");
        }
        System.out.println("Sau try/catch");
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 NullUsageDemo.java
java NullUsageDemo
```

**Exact stdout:**

```text
Vào try
Bắt NullPointerException
Sau try/catch
```

The statement `resource.use()` attempts to invoke an instance method on a `null` reference and throws a `NullPointerException`. After the `try` body is aborted, Java evaluates cleanup, sees that `resource` is `null`, and therefore **does not call `close()`**. The `catch` block receives the `NullPointerException` from the `use` operation, not from automatic closing.

Do not mistakenly infer that "`try-with-resources` handles `null`" means every operation on a `null` object is safe. The mechanism only skips the **automatically generated `close()` call**; it does not guard every expression inside the `try` body.

If the resource is mandatory, a clearer design can use `Objects.requireNonNull` at the boundary to fail fast with context:

```java
import java.util.Objects;

class RequiredResource {
    static void run(AutoCloseable resource) throws Exception {
        Objects.requireNonNull(resource, "resource là bắt buộc");
        try (resource) {
            System.out.println("Có tài nguyên hợp lệ");
        }
    }
}
```

This is an **illustrative class without `main`**, using Java 9+ syntax for a previously declared resource variable. The `requireNonNull` check occurs **before entering `try-with-resources`**, in order to make the "non-`null` required" contract explicit. The `throws Exception` declaration comes from the static type `AutoCloseable.close()`, which can throw a checked `Exception`.

## 5. Why Doesn't Java Call `null.close()`?

You can roughly picture try-with-resources as the following cleanup snippet:

```java
Resource resource = openOrNull();
try {
    doWork(resource);
} finally {
    if (resource != null) {
        resource.close();
    }
}
```

This is **conceptual pseudocode**, not a complete translation of all try-with-resources semantics. It helps illustrate the **`resource != null` check** before closing. Java's actual mechanism is more complex: it must preserve the primary exception, handle exceptions when `close()` fails, and close multiple resources in the proper order.

Do not use this skeleton as a direct replacement for try-with-resources if you need to preserve the original exception. If `doWork` throws exception A and `close` also throws B, a simple `finally` like the one above can cause **B to mask A**. By contrast, try-with-resources keeps A as the primary exception and typically attaches B as a **suppressed exception**.

Takeaway: **skipping `close()` for `null` references** is only one part of the resource-management contract; managing concurrent errors is just as important.

## 6. Distinguishing `null` from Failed Resource Initialization

The following two situations are completely different:

**Situation A: the factory returns `null` normally.**

```java
Resource resource = openOrNull(); // Returns null.
```

In try-with-resources, the initialization expression completes normally, the `resource` variable is assigned `null`, and the `try` body begins. Upon exiting the block, the `null` resource is skipped during the closing step.

**Situation B: the factory throws an exception during initialization.**

```java
Resource resource = openOrThrow(); // Throws an exception.
```

In this case, the initialization expression does not complete normally. **The `try` body has not started**; Java performs cleanup on the resources **already successfully initialized earlier in the same resource specification**, if any, and then propagates the exception according to exception-handling rules.

You should not treat "returning `null`" and "throwing an exception" as equivalent ways of reporting failure. They differ in execution flow, API contract, and the ability to produce a valid result.

## 7. Multiple Resources with One `null` Variable: The Others Are Still Closed

A `null` resource does not prevent other resources from being closed. When multiple variables are declared in `try (...)`, Java processes them in **reverse order of declaration**, skipping any variable whose value is `null`.

Save the program **`MultipleNullResourcesDemo.java`**:

```java
public class MultipleNullResourcesDemo {
    static class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
            System.out.println("Mở " + name);
        }

        @Override
        public void close() {
            System.out.println("Đóng " + name);
        }
    }

    public static void main(String[] args) {
        try (Resource first = new Resource("A");
             Resource middle = null;
             Resource last = new Resource("C")) {
            System.out.println("Trong try: middle null = " + (middle == null));
        }
        System.out.println("Sau try");
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 MultipleNullResourcesDemo.java
java MultipleNullResourcesDemo
```

**Exact stdout:**

```text
Mở A
Mở C
Trong try: middle null = true
Đóng C
Đóng A
Sau try
```

Resources A and C are created, while `middle` is assigned `null`. Closing proceeds from C → middle (skipped) → A. Therefore, there is no "Đóng middle" line. Java still closes C and A even though the middle resource is `null`.

If the `try` body throws an exception, the successfully initialized non-`null` resources are still attempted to be closed in this order before the exception is passed to an appropriate handler.

## 8. Earlier Resource Opened, Later Resource Returns `null`

When a factory in the middle of the list returns `null`, Java still continues **initializing the subsequent resources**. Returning `null` does not abort initialization.

Example:

```java
try (Resource a = open("A");
     Resource optional = optionalResource(); // May be null
     Resource b = open("B")) {
    process(a, optional, b);
}
```

This is **illustrative skeleton code**; the methods and classes must be defined. If `optionalResource()` returns `null` normally, Java still calls `open("B")` and then enters the `try` body. Only when an initialization expression **throws an exception** is there an abnormal exit path.

The `process` method needs to be designed knowing that `optional` may be `null`. If it dereferences `optional` without checking, a `NullPointerException` can occur inside the `try` body; in that case, A and B are still closed normally according to the construct.

This differs from some other conditional-programming constructs: **`null` is just a reference value**, not a signal that the try-with-resources statement automatically interprets as "skip the entire block".

## 9. If Initializing the Second Resource Throws an Exception, the First Resource Is Closed

Save **`InitializationFailureDemo.java`**:

```java
public class InitializationFailureDemo {
    static class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
            System.out.println("Mở " + name);
        }

        @Override
        public void close() {
            System.out.println("Đóng " + name);
        }
    }

    static Resource open(String name) {
        if ("B".equals(name)) {
            System.out.println("Không mở được B");
            throw new IllegalStateException("Lỗi khởi tạo B");
        }
        return new Resource(name);
    }

    public static void main(String[] args) {
        try (Resource a = open("A");
             Resource b = open("B");
             Resource c = open("C")) {
            System.out.println("Trong try");
        } catch (IllegalStateException e) {
            System.out.println("Catch: " + e.getMessage());
        }
        System.out.println("Sau cấu trúc");
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 InitializationFailureDemo.java
java InitializationFailureDemo
```

**Exact stdout:**

```text
Mở A
Không mở được B
Đóng A
Catch: Lỗi khởi tạo B
Sau cấu trúc
```

Resource A was successfully initialized; B threw `IllegalStateException` before returning a resource object; C was not initialized. Java attempts to close A and then passes the error to `catch`. There is no "Trong try", "Mở C", or "Đóng C" line.

This example shows that try-with-resources safely handles **a partially initialized list of resources**, not only the case where all resources were opened. When a resource returns `null` instead of throwing an exception, the initialization flow is not interrupted in this way.

## 10. When Is `close()` Called?

For non-`null` resources, Java attempts to call `close()` when exiting the resource scope after the `try` body. Common paths:

| Path exiting the `try` body | Is a non-`null` resource attempted to be closed? | Where does execution go after closing? |
| --- | --- | --- |
| `try` body completes normally | Yes | Continues after try-with-resources if closing succeeds normally |
| `try` body throws an exception | Yes | Exception is evaluated by `catch` outside the resource scope |
| `try` body executes `return` | Yes | Returns to caller if closing completes normally |
| `try` body executes a valid `break` or `continue` | Yes | Transfers control per the construct if closing succeeds normally |
| Initializing a later resource throws an exception | Previously initialized resources: yes | Propagates to an appropriate handler |
| Specific resource is `null` | **`close()` is not called for that resource** | Remaining resources still follow the rules |

**There is no absolute guarantee** if the JVM is forcibly terminated, the process crashes, or in other severe situations. "Automatic" here means according to Java execution rules when exiting the construct, not magic that guarantees physical resources always close successfully.

An important detail: for a construct with `catch` and `finally` attached directly to try-with-resources, **closing resources completes/is attempted before that `catch` handler or `finally` block runs**.

## 11. `try` Body Throws an Exception, Non-`null` Resource Is Closed

Example **`CloseOnFailureDemo.java`**:

```java
public class CloseOnFailureDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("Đóng resource");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("Trong try");
            throw new IllegalArgumentException("Lỗi nghiệp vụ");
        } catch (IllegalArgumentException e) {
            System.out.println("Catch: " + e.getMessage());
        } finally {
            System.out.println("Finally");
        }
        System.out.println("Kết thúc");
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 CloseOnFailureDemo.java
java CloseOnFailureDemo
```

**Exact stdout:**

```text
Trong try
Đóng resource
Catch: Lỗi nghiệp vụ
Finally
Kết thúc
```

Even though the `try` body throws an exception, the `close()` call still happens before the construct's `catch`. In the case where `resource = null`, the "Đóng resource" line would not appear; the handler still catches the exception thrown from the `try` body.

## 12. When `close()` Itself Throws an Exception

`AutoCloseable.close()` is allowed to throw an exception. In that case, we must consider whether there was already a **primary exception** from the `try` body.

### 12.1. Only `close()` Fails

Save **`CloseOnlyFailureDemo.java`**:

```java
public class CloseOnlyFailureDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("Trong close");
            throw new IllegalStateException("Không đóng được");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("Thân try thành công");
        } catch (IllegalStateException e) {
            System.out.println("Catch: " + e.getMessage());
        }
        System.out.println("Sau try/catch");
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 CloseOnlyFailureDemo.java
java CloseOnlyFailureDemo
```

**Exact stdout:**

```text
Thân try thành công
Trong close
Catch: Không đóng được
Sau try/catch
```

Here, the `try` body completes, but `close()` throws an exception. The closing error becomes the **primary exception** of the construct. `catch` receives that error. You cannot conclude that the entire operation succeeded just because the `try` body completed.

If the `resource` is actually `null`, Java does not call `close()`, so there is no closing error from that resource.

### 12.2. Both the `try` Body and `close()` Fail

Save **`PrimarySuppressedDemo.java`**:

```java
public class PrimarySuppressedDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("Trong close");
            throw new IllegalStateException("Lỗi đóng");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("Trong try");
            throw new IllegalArgumentException("Lỗi chính");
        } catch (IllegalArgumentException e) {
            System.out.println("Primary: " + e.getMessage());
            System.out.println("Suppressed: "
                    + e.getSuppressed().length);
            System.out.println("Phụ: "
                    + e.getSuppressed()[0].getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 PrimarySuppressedDemo.java
java PrimarySuppressedDemo
```

**Exact stdout:**

```text
Trong try
Trong close
Primary: Lỗi chính
Suppressed: 1
Phụ: Lỗi đóng
```

The `IllegalArgumentException` from the `try` body is the **primary** exception. The `IllegalStateException` from `close()` is attached to the primary exception via `addSuppressed` by the try-with-resources mechanism, and accessed using `getSuppressed()`.

This differs from manual cleanup in `finally`: if `finally` throws a new exception, it can **mask the original error**. With try-with-resources, Java preserves the primary error and records the closing error as a suppressed exception.

**If the resource is `null`, `close()` does not run, so there is no suppressed exception from that resource.** Do not assume that any exception in the `try` body guarantees a suppressed element; only access `getSuppressed()[0]` after checking that the array is non-empty in real code.

## 13. Multiple Resources: Closing Errors from a `null` Object Do Not Exist

Suppose resource A is non-`null`, B is `null`, and C is non-`null`. When the `try` body fails, Java attempts to close C, skips B, and then closes A. If both C's and A's `close()` throw exceptions, both closing errors can be attached as suppressed exceptions to the primary exception in closing order.

There is no "phantom" closing error for B: because Java does not call `close()` on B, B does not generate an additional suppressed exception from cleanup.

Skeleton example:

```java
try (Resource a = open("A");
     Resource b = null;
     Resource c = open("C")) {
    throw new IllegalArgumentException("Work failed");
}
```

This is an **illustrative skeleton**, requiring a valid `Resource` class and `open` method. If A's or C's `close()` throws an error, you can inspect `getSuppressed()` in the corresponding handler. The closing order **C before A** remains unchanged because B is `null`.

The right way to reason about this is to consider **each successfully initialized non-`null` resource**, and then consider the exceptions thrown by those closing operations.

## 14. `try (resource)` with a Previously Declared Variable: `null` Is Still Skipped

Since **Java 9**, a resource specification can use a previously declared resource reference variable, provided that variable is `final` or *effectively final* and has been definitely assigned. Java 17 supports this syntax:

```java
Resource resource = mayReturnNull();
try (resource) {
    System.out.println("Trong try");
}
```

This is **skeleton code**. The `resource` variable exists in the outer scope and remains visible after the `try` block. If the reference is `null`, Java skips calling `close()`; if non-`null`, Java attempts to close it upon exiting the block.

Standalone example **`ExistingVariableNullDemo.java`**:

```java
public class ExistingVariableNullDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("Đóng");
        }
    }

    public static void main(String[] args) {
        Resource resource = null;

        try (resource) {
            System.out.println("Trong try");
        }

        System.out.println("Vẫn truy cập tên resource: "
                + (resource == null));
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 ExistingVariableNullDemo.java
java ExistingVariableNullDemo
```

**Exact stdout:**

```text
Trong try
Vẫn truy cập tên resource: true
```

There is no `Đóng` line because `resource` is `null`. `resource` is declared in the outer scope so the name can still be used after the construct, but using `try (resource)` does not mean Java code can freely reassign the variable; this syntax requires it to be `final` or *effectively final*.

If the variable has not been **definitely assigned** before being used in the resource specification, the compiler will reject it. If reassigning it makes it no longer effectively final, the `try (resource)` syntax will also be invalid. This is a **compile-time** rule, distinct from the fact that the reference may be `null` at runtime.

## 15. The Value Closed Is Determined from the Resource in the Resource Specification

With the declaration form:

```java
try (Resource resource = createResource()) {
    // ...
}
```

the expression `createResource()` is evaluated at initialization. Whether the resource is `null` is determined from **the initialized reference value**. Java does not re-evaluate `createResource()` when reaching the closing step.

This matters if the factory has side effects or its result changes over time. Resource initialization is a step with a clear effect; you should not write code assuming the factory will be called again at cleanup time.

With the Java 9+ form `try (resource)`, the variable is final/effectively final. That does not guarantee the **object's internal state** is immutable: the resource can still change state, while try-with-resources attempts to call `close()` on the object selected by the resource specification.

The object may already have been closed earlier by other code, and `close()` may be called again when exiting `try`. The `AutoCloseable` interface does not make all implementations completely idempotent, so you must clearly define resource ownership and avoid casually sharing closing responsibility.

## 16. `null` Does Not Mean Java Skips Checked Exception Checking

Automatic `close()` rules are also subject to **compile-time type checking**. According to the standard API, `AutoCloseable.close()` declares `throws Exception`, whereas subclasses may override it with a narrower checked exception type or throw no checked exceptions at all.

Example:

```java
static void useGeneric(AutoCloseable resource) throws Exception {
    try (resource) {
        System.out.println("Trong try");
    }
}
```

This is an **illustrative method**, with `resource` as an effectively final parameter using Java 9+ syntax. The `throws Exception` signature is appropriate because the static type of `resource` is `AutoCloseable`; by contract, `close()` can throw `Exception`.

If you pass a `null` reference to this call, **the runtime will skip `close()`**, but the compiler still checks the method's static type contract. You should not assume that "because this variable is `null` at runtime, you can remove all `throws` or `catch` clauses related to `close()`" in every case.

If you define your own class implementing `AutoCloseable` and override `close()` **without declaring any checked exception**, like `Resource` in the examples above, callers working with the static type `Resource` generally do not have to handle `Exception` just because of try-with-resources.

## 17. When Should a Factory Be Allowed to Return `null`?

Some legacy APIs or integration boundaries may allow a factory to return `null` to mean "no resource". Try-with-resources handles cleanup in this case according to the rules, but API design still needs to answer:

- Is `null` an **expected, valid state**?
- If there is no resource, is there any work the `try` body is allowed to continue doing?
- Should a result type such as `Optional` or another status representation be used to express absence more clearly?
- Could callers confuse `null` with a technical initialization error that should have thrown an exception?
- When there is no resource, should the task return a result early, report an error, or use a genuinely valid fallback?

For example, if a configuration source is optional, having no reader may legitimately lead to a default configuration. But if a transaction requires a connection, having a factory return `null` and letting the program silently continue can produce corrupt data.

**Try-with-resources does not define the business meaning of `null`.** It only provides the rule of not calling `close()` on `null` during cleanup. Clarify the contract before relying on this behavior.

## 18. Safe Habits When Opening and Using a Resource

How you write the code depends on whether the absence of a resource is permitted.

### 18.1. Mandatory Resource: Check Explicitly

```java
import java.util.Objects;

class RequiredResourceExample {
    static void process(AutoCloseable resource) throws Exception {
        Objects.requireNonNull(resource, "resource không được null");
        try (resource) {
            // Perform the operation that the contract requires a resource for.
        }
    }
}
```

This is a valid class **without `main`**. If the caller passes `null`, the program throws a `NullPointerException` at the explicit check step, with a message stating the precondition clearly. Note: `Objects.requireNonNull` does not close anything itself; it only makes the contract explicit.

### 18.2. Optional Resource: Check Before Use

```java
static void processOptional(Resource resource) {
    try (resource) {
        if (resource == null) {
            System.out.println("Không có dữ liệu cần xử lý");
            return;
        }
        resource.work();
    }
}
```

This is an **illustrative method** with `Resource` implementing `AutoCloseable` and having a `work()` method. `Resource` declares no checked exception on `close()` in this hypothetical example. Make sure the `resource` parameter is not reassigned, so that it satisfies the Java 9+ requirement.

When the value is `null`, the handler decides to do nothing and `return`. Java evaluates cleanup for `try-with-resources`, sees a `null` reference, and skips `close()`; when non-`null`, it executes `work()` and then closes the resource.

Avoid building APIs that "sometimes return `null`, sometimes throw an error" without clearly explaining which cases represent a valid absence of data and which represent a technical failure.

## 19. Common Mistakes

| Misconception | Correct rule |
| --- | --- |
| "`try (Resource r = null)` immediately throws `NullPointerException`." | No. The `try` body still runs, and cleanup skips `close()` for the `null` resource. |
| "A `null` resource still has `close()` called on it; Java just catches the error." | No. Java **does not call** `close()` on a `null` reference. |
| "You can call `r.work()` freely because try-with-resources handles `null`." | No. Dereferencing `null` inside the `try` body can still throw a `NullPointerException`. |
| "If a middle resource is `null`, the remaining resources are not closed." | Wrong. Successfully initialized non-`null` resources are still attempted to be closed in reverse order. |
| "A factory returning `null` is the same as a constructor throwing an exception." | No. Returning `null` is normal completion; throwing an exception aborts initialization and closes earlier resources. |
| "Every resource is closed when initializing a later resource fails." | Only resources that were already successfully initialized earlier are managed for closing; uncreated resources have no object to close. |
| "`close()` cannot throw an error because Java calls it automatically." | Wrong. `close()` can throw an exception, which becomes primary or suppressed depending on the situation. |
| "You only need `getCause()` to see resource-closing errors." | In try-with-resources, a closing error that occurs when a primary exception already exists is typically in `getSuppressed()`. |
| "If there is an exception in the `try` body, there is definitely a suppressed exception." | No. If closing succeeds normally or the resource is `null`, there may be no suppressed exceptions. |
| "Java 9 `try (resource)` allows reassigning the resource variable freely." | No. A variable used in the resource specification must be `final`/effectively final and definitely assigned. |
| "If the runtime resource is `null`, the compiler ignores checked exceptions on `close()`." | Compile-time obligations are determined by the static type contract, not just the runtime value. |
| "Try-with-resources guarantees `close()` succeeds under all circumstances." | Java only attempts to call `close()` upon exiting scope; closing errors, crashes, or forced termination can still occur. |

## 20. Self-Check Scenarios

**Question 1.** `try (Resource r = null) { System.out.println("ok"); }`, where `Resource` is `AutoCloseable`. Does it print `ok`? Is `close()` called?  
**Answer:** It prints `ok` if the `try` body does not throw an error; `close()` is not called on `r` because it is `null`.

**Question 2.** Inside the `try` body, the program calls `r.read()` when `r == null`. Is this an error caused by automatic cleanup?  
**Answer:** No. The `NullPointerException` (if any) arises from using a `null` reference inside the `try` body. The cleanup step still skips the `null` resource.

**Question 3.** There are three resources A, B, and C; B is `null` while A and C are non-`null`. What is the closing order?  
**Answer:** C then A. Java inspects B in between but does not call `close()` because B is `null`.

**Question 4.** The factory for resource A succeeds, then the factory for B returns `null`. Does the program continue initializing C?  
**Answer:** Yes, unless another exception occurs. Returning `null` normally does not cut short resource initialization.

**Question 5.** The factory for A succeeds, and the factory for B throws `IOException`. Does the `try` body run?  
**Answer:** No. Java attempts to close A before the initialization exception from B is handled or propagated.

**Question 6.** The `try` body throws exception A, and `close()` throws B. Which one does the caller receive as primary?  
**Answer:** With try-with-resources, A is primary, and B is typically attached in `A.getSuppressed()`.

**Question 7.** The `try` body succeeds, but `close()` throws B. Does B disappear automatically because it happened during automatic cleanup?  
**Answer:** No. B becomes the primary exception if there is no primary exception from the `try` body.

**Question 8.** Can `try (AutoCloseable r = ...)` force handling of checked `Exception`, even if at runtime `r` is sometimes `null`?  
**Answer:** Yes. The static type contract `AutoCloseable.close()` declares `throws Exception`, which the compiler checks during analysis.

**Question 9.** Does Java 17 allow `Resource r = null; try (r) {...}`?  
**Answer:** Yes, if `r` is `final`/effectively final and has been assigned before use; since `r` is `null`, `close()` is not called.

**Question 10.** If `null` is an invalid state for an API, should you let the `try` body throw an NPE at a random statement?  
**Answer:** You should validate early with a clear contract, such as `Objects.requireNonNull`, or have the factory throw an appropriate exception instead of returning an ambiguous `null`.

## 21. Checklist When Reviewing try-with-resources That May Receive `null`

1. **Factory contract:** can it return `null`, or must it return an object? Is `null` a valid case or a bug?
2. **Resource type:** does the resource implement `AutoCloseable`, and what checked exceptions can `close()` throw?
3. **At initialization:** does the expression return `null` normally or throw an exception? Those two paths differ.
4. **`try` body:** does it dereference a resource that has not been checked for `null`?
5. **`close()` call:** only occurs for non-`null` references that were successfully initialized.
6. **Multiple resources:** initialization order is left→right, closing order is right→left, skipping `null`.
7. **Partial initialization:** if a later resource fails, are previously opened resources attempted to be closed?
8. **Primary/suppressed exceptions:** when both the body and `close()` fail, does the caller check `getSuppressed()`?
9. **Java 9+ syntax:** when using `try (resource)`, is the outer variable `final`/effectively final and definitely assigned?
10. **Error preservation:** do you avoid having `finally` throw a new error that masks the primary error?
11. **Ownership:** could the resource be closed twice or used after closing because it is shared?
12. **Testing:** do tests cover non-`null` resources, `null` resources, initialization errors, and `close()` errors?

## 22. Key Takeaways

**Try-with-resources automatically attempts to close resources that implement `AutoCloseable`, but it only calls `close()` on successfully initialized non-`null` references.** A `null` resource variable does not cause the statement itself to throw a `NullPointerException`, the `try` body still runs, and Java skips the `close()` call for that variable. However, any statement inside the `try` body that attempts to use a `null` object can still throw a `NullPointerException`.

With multiple resources, Java initializes left to right, closes right to left, and skips `null` resources. If an initialization expression **throws an exception**, the `try` body is not entered; previously opened resources are attempted to be closed. If `close()` fails, the closing error can become the primary exception when the body succeeds, or a suppressed exception when a primary error already exists.

Treat the absence of a resource as an **API contract design decision**, not something try-with-resources automatically "fixes" for your program. When a resource is mandatory, validate explicitly; when a resource is optional, handle the `null` branch deliberately, and let try-with-resources take care of cleanup.
