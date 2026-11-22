# Scoped Values (Preview in Java 21) for Sharing Immutable Context

## 1. The Problem: Passing Context Across Multiple Calls Without Polluting Method Signatures

In Java, the most explicit way to pass data is through parameters:

```java
void handle(RequestContext context) {
    validate(context);
}
```

However, when a processing call passes through multiple library layers, a whole chain of intermediate methods may have to accept and forward a value that they do not use themselves: a task identifier, authenticated user information, locale, or tracing parameters. `ThreadLocal` solves this implicit passing, but brings issues with mutability from any callee, lifecycle management requiring `remove()`, and overhead when there are very many virtual threads.

**`ScopedValue<T>`** allows a *caller* to bind a key to a value **within a bounded execution scope**, and then directly or indirectly called methods can read the value via that key. When the scope ends, the binding automatically terminates or restores the outer binding. This is a **one-way, read-oriented** context-passing model: the callee only reads the binding provided by the caller, unless the callee itself explicitly opens a child scope with a different binding.

This article focuses on **Java concurrency and thread context in general**, especially tasks using virtual threads. The mechanism does not depend on Spring.

### API Status by Java Version

| Version | `ScopedValue` Status | Practical Consequence |
| --- | --- | --- |
| Java 21 | First preview, JEP 446 | Requires `--enable-preview` when compiling and running; use the API matching the Java 21 documentation. |
| Java 22–24 | Subsequent preview rounds | The API may change; read the JavaDoc for the exact version. |
| Java 25 and later | Standard API, JEP 506 | No need to enable preview specifically for `ScopedValue`. |

In this article, all examples marked **Java 21** apply the JDK 21 preview API and use the exact run commands. Snippets marked **Java 25+** use the standard API; do not arbitrarily mix versions within a single example.

## 2. Mechanism: Keys, Bindings, and Dynamic Scope

Suppose we declare:

```java
private static final ScopedValue<String> TRACE_ID = ScopedValue.newInstance();
```

`TRACE_ID` is only a **key** used to look up a value. It is not a globally updated `String` variable. When running:

```java
ScopedValue.runWhere(TRACE_ID, "REQ-42", () -> handleRequest());
```

JDK 21 executes `handleRequest()` with `TRACE_ID` bound to `"REQ-42"` on the current thread. Any deeper call in that call chain that has access to the key can call `TRACE_ID.get()`. When `runWhere` returns or throws an exception, the binding is removed and the previous binding (if any) is restored. No `try/finally/remove` is needed for binding cleanup.

This scope is a **dynamic scope**: it is determined by the methods that actually execute inside the binding call, including callbacks, rather than simply by the braces of an arbitrary lexical block.

An illustration of the execution path:

```text
Current thread
  |
  +-- TRACE_ID is not bound
  |
  +-- runWhere(TRACE_ID, "REQ-42", () -> service())
  |     |
  |     +-- service()
  |           |
  |           +-- repository()  -> TRACE_ID.get() == "REQ-42"
  |           |
  |           +-- callback()    -> TRACE_ID.get() == "REQ-42"
  |
  +-- end of scope: TRACE_ID returns to its previous state
```

**Do not equate an immutable binding with an immutable object.** The API does not provide a `TRACE_ID.set(...)` operation to modify an existing binding, but if you bind an `ArrayList` or an object with setters, code that receives the reference can still mutate **the internals of the object**. To truly use an "immutable context", bind a `String`, a record containing immutable values, or an object designed to be immutable / use defensive copying.

## 3. Key APIs in Java 21

| API | Purpose |
| --- | --- |
| `ScopedValue.newInstance()` | Creates a new key, initially unbound in all threads. |
| `ScopedValue.runWhere(key, value, runnable)` | Binds the value and runs the `Runnable` within that scope. |
| `ScopedValue.callWhere(key, value, callable)` | Binds the value and returns the result of the `Callable`; can propagate checked exceptions. |
| `ScopedValue.getWhere(key, value, supplier)` | Binds the value and returns the result of the `Supplier`. |
| `ScopedValue.where(key, value).run(runnable)` | Creates a `Carrier` of one or more bindings and executes with them. |
| `ScopedValue.where(k1,v1).where(k2,v2).call(callable)` | Binds multiple keys in a single scope. |
| `key.get()` | Gets the currently bound value; throws `NoSuchElementException` if unbound. |
| `key.isBound()` | Checks whether the key has a binding in the current thread. |
| `key.orElse(fallback)` | Gets the binding or returns `fallback` if unbound. |
| `key.orElseThrow(supplier)` | Throws the supplied exception if the key is unbound. |

On Java 21, both `ScopedValue` and `ScopedValue.Carrier` are **preview APIs**, so preview must be enabled for both compiling and running. `Carrier` is an immutable set of mappings: chaining `where(...)` creates a new carrier without modifying the existing carrier.

**Security and API design:** only code that has access to the key object can call `get()`. Therefore, keys are typically kept in `private static final` fields, exposing only read helpers as needed. Making the key public across the entire application increases the number of places that can access the context.

## 4. Complete Java 21 Example: Binding, Deep Calls, Rebinding, and Restoration

Save as `ScopedValueDemo.java`:

```java
public class ScopedValueDemo {
    private static final ScopedValue<Context> CONTEXT =
            ScopedValue.newInstance();

    record Context(String traceId, String userId) {}

    static String readInDeepMethod() {
        return CONTEXT.get().traceId();
    }

    static String service() {
        return "trace=" + readInDeepMethod();
    }

    public static void main(String[] args) throws Exception {
        System.out.println("Before: " + CONTEXT.isBound());

        String result = ScopedValue.where(
                CONTEXT, new Context("REQ-42", "an")).call(() -> {

            System.out.println("Outer: " + service());

            String nested = ScopedValue.where(
                    CONTEXT, new Context("REQ-99", "an"))
                    .call(ScopedValueDemo::service);

            System.out.println("Inner: " + nested);
            System.out.println("Restored: " + service());
            return "ok";
        });

        System.out.println("Result: " + result);
        System.out.println("After: " + CONTEXT.isBound());
    }
}
```

Use **JDK 21** to compile and run:

```bash
javac --enable-preview --release 21 -encoding UTF-8 ScopedValueDemo.java
java --enable-preview ScopedValueDemo
```

Compilation may emit a notice that the program uses preview APIs; that is expected. **Stdout from the program**:

```text
Before: false
Outer: trace=REQ-42
Inner: trace=REQ-99
Restored: trace=REQ-42
Result: ok
After: false
```

Explanation:

1. Before entering the scope, `CONTEXT.isBound()` is `false`.
2. `Carrier.call(...)` binds the record for the current thread; `service()` and `readInDeepMethod()` can read `REQ-42` even without a context parameter.
3. The nested scope **rebinds** the same key to `REQ-99`; it does not mutate the outer record.
4. When the child scope ends, `REQ-42` is restored. When the outer scope ends, the key is unbound again.
5. The result of the `Callable` is returned from `call`. There is no manual cleanup step.

The `Context` record uses immutable `String` components; if a record holds a `List`, `Map`, or other mutable objects, consider `List.copyOf`, `Map.copyOf`, or an appropriate form of defensive copying.

## 5. Exceptions Also Terminate the Scope Properly

When a task inside a scope throws an exception, the binding mechanism is still unwound/restored. Java 21 example, save as `ScopedValueFailureDemo.java`:

```java
public class ScopedValueFailureDemo {
    private static final ScopedValue<String> TRACE =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        System.out.println("Before: " + TRACE.isBound());

        try {
            ScopedValue.runWhere(TRACE, "REQ-error", () -> {
                System.out.println("During: " + TRACE.get());
                throw new IllegalStateException("boom");
            });
        } catch (IllegalStateException e) {
            System.out.println("Caught: " + e.getMessage());
        }

        System.out.println("After: " + TRACE.isBound());
    }
}
```

```bash
javac --enable-preview --release 21 -encoding UTF-8 ScopedValueFailureDemo.java
java --enable-preview ScopedValueFailureDemo
```

```text
Before: false
During: REQ-error
Caught: boom
After: false
```

Binding restoration is handled by the scope mechanism, even when an exception is thrown. This solves a common `ThreadLocal` bug: forgetting to call `remove()` after an early return branch or an exception. However, **`ScopedValue` does not automatically close resources** pointed to by the value. If the value holds a connection, file, or `AutoCloseable` resource, you must manage closing it separately with `try-with-resources` or an explicit lifecycle.

## 6. Cross-Thread Visibility and Structured Concurrency

A `ScopedValue` binding belongs to the **currently running thread**, not a global variable. Another thread running independently will not automatically see the current thread's binding.

**Important characteristic:** `ScopedValue` can be **inherited in a structured way** by child threads created with `StructuredTaskScope.fork(...)` inside a suitable scope. The parent-child structure allows child threads to share **references to the immutable context** without needing to copy a full `ThreadLocalMap` for each child.

In **Java 21**, `StructuredTaskScope` is also a **preview API** (JEP 453). You must enable `--enable-preview`. The following snippet uses the exact Java 21 API style; save as `ScopedValueChildrenDemo.java`:

```java
import java.util.concurrent.StructuredTaskScope;

public class ScopedValueChildrenDemo {
    private static final ScopedValue<String> TRACE =
            ScopedValue.newInstance();

    static String work(String name) {
        return name + "=" + TRACE.get();
    }

    public static void main(String[] args) throws Exception {
        String joined = ScopedValue.where(TRACE, "REQ-7").call(() -> {
            try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {
                var first = scope.fork(() -> work("first"));
                var second = scope.fork(() -> work("second"));

                scope.join().throwIfFailed();
                return first.get() + ", " + second.get();
            }
        });

        System.out.println(joined);
        System.out.println("Parent bound: " + TRACE.isBound());
    }
}
```

```bash
javac --enable-preview --release 21 -encoding UTF-8 ScopedValueChildrenDemo.java
java --enable-preview ScopedValueChildrenDemo
```

```text
first=REQ-7, second=REQ-7
Parent bound: false
```

Although the two children can finish in any order, the final result concatenates `first.get()` before `second.get()`, so stdout is deterministic. `scope.join()` waits for the children to complete, and `throwIfFailed()` reports an error if any task failed. When `try-with-resources` ends, the task scope is closed. Both children read the same `REQ-7` value from the binding that the scope captured at creation time; the key is not re-set on each child.

**Limitation to understand:** this inheritance mechanism is tied to *structured task scope*; it does not mean every way of starting a thread propagates the binding. Specifically, do not assume `Thread.ofVirtual().start(...)` or an arbitrary executor automatically receives the context from the submitting thread. If context is needed in an independent task, bind it directly inside that task or organize the tasks using an appropriate structured scope.

When the value is immutable, multiple children can safely reference it for reading. If the value is mutable, inheriting the binding **does not make the object thread-safe**; you must synchronize access or choose an immutable object.

### Why Does Structuredness Matter?

If a child thread continues running after the parent's scope ends, the meaning of the context becomes hard to define. `StructuredTaskScope` ties the lifetime of child tasks to the parent block, giving context propagation and binding cleanup a clear start and end point. Do not separate binding propagation from the lifetime design and error handling of child tasks.

Version note: the `StructuredTaskScope` API continued to evolve in later Java releases; the snippet above is **Java 21 preview** and is not guaranteed to compile verbatim on all newer JDKs.

## 7. Comparing ScopedValue and ThreadLocal

| Criterion | `ScopedValue` | `ThreadLocal` |
| --- | --- | --- |
| Best use case | **Read-oriented** context passing within a clear scope | Per-thread state needing flexible `get/set/remove` |
| Setting a value | Caller binds inside `run/call` | Any code with the key can `set` |
| Modifying binding in callee | No setter to mutate the active binding; can open a child scope to temporarily rebind | Can `set` and affect subsequent calls on the thread |
| Lifecycle | Automatically restored when the scope ends | Remains attached to the thread until `remove` or thread termination |
| Reading outside scope | `get` throws `NoSuchElementException`; `isBound/orElse` are safe | `get` returns `null` or initial value |
| Propagation to child | Has inheritance mechanism via structured task scope | `ThreadLocal` is normally not inherited; `InheritableThreadLocal` has different rules |
| Many virtual threads | Well suited for reading scope-shared immutable context | Can consume significant memory if each virtual thread holds large separate data |
| Value immutability | **Does not automatically enforce deep immutability** | Does not enforce immutability |
| Availability | Preview in Java 21–24, standard since Java 25 | Long-established stable API |

Performance evaluation must be based on real workloads. `ScopedValue` typically has lower overhead when passing read-only context to many structured virtual threads, but **should not be treated as an automatic speedup** for every algorithm.

## 8. Designing Immutable Context and Access Boundaries

A convenient design is to group data with the same lifecycle into a record:

```java
import java.util.Map;

record RequestContext(String traceId, String principal,
                      Map<String, String> tags) {
    RequestContext {
        tags = Map.copyOf(tags);
    }
}
```

This is a **data-type illustration snippet**, not a standalone Java program. `Map.copyOf` creates a map that disallows modification through the map API; here both keys and values are `String`, so there are no deeply nested mutable objects. If a field is another mutable object, a record only makes the **reference** immutable, not the object itself.

Some guidelines:

- Data in the context should be **small, essential, and immutable**: trace ID, correlation ID, locale, normalized read-only query parameters.
- Do not put an entire request body, large buffers, caches, or open connections into the context without a clear reason and exact lifecycle.
- The `ScopedValue` key field should be accessible from as few places as possible (usually `private static final`), providing read helpers if needed to reduce implicit coupling.
- If processing only passes through one or two methods, **explicit parameter passing** is usually easier to understand and test.
- Do not confuse "unable to re-set the binding in the callee" with a sandbox or complete security access-control mechanism; code with access to the key can still read the bound value.

## 9. Common Pitfalls

### Pitfall 1: Calling `get` outside a binding

Calling `TRACE.get()` when the key is unbound throws `NoSuchElementException`. Create the scope before calling, or use `TRACE.isBound()`, `TRACE.orElse(fallback)`, or `TRACE.orElseThrow(...)` depending on the API contract.

### Pitfall 2: Assuming rebinding changes the parent's value

In a nested scope, rebinding only takes effect **for the child scope**. When the child ends, the parent reads the old value. Do not use rebinding to pass return values back from callee to caller; return a value or use an explicit result channel instead.

### Pitfall 3: Binding a mutable object and treating it as immutable

Two child threads can see the same `ArrayList` or `HashMap` reference and mutate it concurrently, leading to a data race. Use immutable values/defensive copies or synchronize if shared mutable state is truly required.

### Pitfall 4: Assuming every thread inherits context

Bindings are per-thread. Structured inheritance has specific boundaries; a task submitted to an independent executor may not receive the value. Do not rely on implicit context when the concurrency model does not guarantee propagation.

### Pitfall 5: Using Java 25 syntax while running JDK 21

Java 21 has its own preview API and requires preview flags:

```bash
javac --enable-preview --release 21 ScopedValueDemo.java
java --enable-preview ScopedValueDemo
```

If the machine is running JDK 25, do not use `--release 21` to "simulate Java 21 preview" from the JDK 25 compiler: preview features are tied to the running compiler version. To verify the Java 21 API, you must run an actual **JDK 21**.

### Pitfall 6: Overusing hidden context

If all logic relies on many secret keys, data becomes hard to trace and test. Group related fields into a clearly named record and reserve `ScopedValue` for information that genuinely spans many call layers.

## 10. Migrating from ThreadLocal to ScopedValue When Appropriate

A `ThreadLocal`-style API often looks like this:

```java
private static final ThreadLocal<String> TRACE = new ThreadLocal<>();

static void handle(String id) {
    TRACE.set(id);
    try {
        process();
    } finally {
        TRACE.remove();
    }
}
```

The snippets in this section **illustrate the method pattern**; `process()` is provided by the application. If the data is read-only and no branch genuinely needs `TRACE.set()` mid-way, with Java 21 preview you can write:

```java
private static final ScopedValue<String> TRACE = ScopedValue.newInstance();

static void handle(String id) {
    ScopedValue.runWhere(TRACE, id, () -> process());
}
```

The benefit is that the caller decides the binding within a clear scope; the callee `process()` only reads `TRACE.get()`, and the mechanism automatically restores it when the execution block ends.

**Do not replace mechanically** if legacy code actively updates state throughout the thread's lifetime, relies on values outliving the scope, interacts with unsupported libraries, or requires propagating context across unstructured asynchronous tasks. Determine the processing scope, ownership, and lifecycle before migrating.

When using Java 25+, the `ScopedValue.where(KEY, value).run(...)` API is available without enabling preview. Preview convenience methods such as `runWhere` in the Java 21 documentation should not be treated as a stable common API across all JDKs.

## 11. Self-Check Questions

**Q:** How does `ScopedValue` differ from a `static final String` variable?  
**A:** A `static final String` is a single fixed shared value; a `ScopedValue` is a **key** that can hold different bindings per thread and scope, automatically restored when the scope ends.

**Q:** The outer scope binds `A`, the child scope binds `B`; after the child scope ends, what is read?  
**A:** `A`; the child binding `B` exists only within the child scope.

**Q:** If a task throws an exception before finishing, is it necessary to call `remove()`?  
**A:** No; the scope automatically restores the binding. Resources held inside the value still need to be closed separately.

**Q:** Why does a record not necessarily provide deep immutability?  
**A:** A record only prevents reassigning fields; a field may point to a mutable object. For safe sharing, choose immutable types or appropriate defensive copies.

**Q:** Does using `Thread.ofVirtual().start(...)` inside a parent scope automatically propagate `ScopedValue`?  
**A:** Not by default. Inheritance of scoped values is tied to the structured task scope model, not every API that creates virtual threads.

**Q:** What commands must be run on Java 21 for code using `ScopedValue`?  
**A:** `javac --enable-preview --release 21 ...` and `java --enable-preview ...`, on **JDK 21**.

**Key takeaway:** `ScopedValue` passes **read-oriented context** within an execution scope that has a clear end point; bindings can be nested, are automatically restored, and are propagated to child threads when using the appropriate structure. To make sharing truly safe, bind **small, immutable context**, and understand both the Java version and task lifecycle.

## Official Documentation

- [OpenJDK JEP 446 — Scoped Values (Preview), Java 21](https://openjdk.org/jeps/446)
- [Oracle Java 21 — ScopedValue API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ScopedValue.html)
- [Oracle Java 21 — ScopedValue.Carrier API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ScopedValue.Carrier.html)
- [OpenJDK JEP 453 — Structured Concurrency (Preview), Java 21](https://openjdk.org/jeps/453)
- [OpenJDK JEP 506 — Scoped Values, Java 25](https://openjdk.org/jeps/506)
- [Oracle Java 25 — ScopedValue API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html)
