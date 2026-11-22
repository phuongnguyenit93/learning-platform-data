# Error and VirtualMachineError in Java

## 1. Learning Objectives

After this lesson, you will be able to:

- Place `Error` and `VirtualMachineError` in their proper positions within the `Throwable` hierarchy.
- Distinguish `Error` from `Exception`/`RuntimeException` and understand why `Error` belongs to the *unchecked* category.
- Identify common types of `VirtualMachineError`, their frequent causes, and their scope of impact.
- Know the limits of `catch`, `finally`, the uncaught exception handling mechanism, and safe handling options when JVM resources fail.
- Analyze a specific scenario without confusing a "serious error" with "the JVM has definitely stopped".

The classes in this lesson belong to `java.lang` and do not require `import`.

## 2. Position in the Exception Hierarchy

`Throwable` is the root type of objects that can be thrown (`throw`) and caught (`catch`) in Java. Its two main branches are `Exception` and `Error`:

```text
java.lang.Object
└── java.lang.Throwable
    ├── java.lang.Exception
    │   └── java.lang.RuntimeException
    │       └── ... (other unchecked exceptions)
    └── java.lang.Error
        ├── java.lang.AssertionError
        ├── java.lang.LinkageError
        │   ├── java.lang.NoClassDefFoundError
        │   └── java.lang.ExceptionInInitializerError
        └── java.lang.VirtualMachineError (abstract)
            ├── java.lang.InternalError
            │   └── java.util.zip.ZipError
            ├── java.lang.OutOfMemoryError
            ├── java.lang.StackOverflowError
            └── java.lang.UnknownError
```

This is a **diagram of representative branches**, not an exhaustive list of all subclasses of `Error`. The four **direct** subclasses of `VirtualMachineError` in Java 17 are `InternalError`, `OutOfMemoryError`, `StackOverflowError`, and `UnknownError`. `ZipError` is an example of an **indirect** subclass through `InternalError`.

The "is-a" relationship operates through inheritance:

- Every `OutOfMemoryError` is a `VirtualMachineError`, `Error`, and `Throwable`.
- Every `AssertionError` is an `Error`, but not a `VirtualMachineError`.
- An `IOException` belongs to the `Exception` branch, not the `Error` branch.

### Is `Error` a checked exception?

No. In compile-time exception checking, `Error` and all its subclasses are considered *unchecked*, similar to `RuntimeException`. The compiler does not force a method to declare `throws OutOfMemoryError` and does not force callers to write `catch`.

This **does not mean** errors cannot be caught; `catch (Error e)` or `catch (Throwable t)` still match syntactically and by type. It means Java does not require developers to handle them using the checked exception mechanism, because in most situations they cannot be properly fixed at the business logic layer.

## 3. `Error`: Meaning and Boundary with `Exception`

According to the Java API contract, `Error` indicates serious problems that a reasonable application should not try to catch and continue as if nothing happened. Not every `Error` originates from a broken JVM engine.

| Category | Examples | Typical Meaning | Handling Approach |
| --- | --- | --- | --- |
| Checked `Exception` | `IOException`, `SQLException` | Issues that calling code is normally required to consider handling/declaring | Catch, recover, return an error, or propagate appropriately |
| `RuntimeException` | `IllegalArgumentException`, `NullPointerException` | API misuse, invalid program state, or violated invariants | Fix the root bug; catch at appropriate boundaries |
| Non-`VirtualMachineError` `Error` | `AssertionError`, `NoClassDefFoundError` | Violated assumptions or class linking/loading failures | Fix configuration, dependencies, or program bugs |
| `VirtualMachineError` | `OutOfMemoryError`, `StackOverflowError` | The JVM encountered an internal failure or exhausted required resources | Collect evidence, fix the root cause, evaluate whether the process can continue |

**Two common points of confusion:**

1. `NoClassDefFoundError` is not `ClassNotFoundException`. The former belongs to `LinkageError → Error`; the latter belongs to `Exception` and is a checked exception. They occur in different scenarios and have different handling interfaces.
2. `AssertionError` usually arises from a violated `assert` statement (when assertions are enabled), or is explicitly thrown by code. It is an `Error`, but by itself it does not prove that the JVM has run out of memory or encountered an internal failure.

You should not manually create `new Error(...)` or `new OutOfMemoryError(...)` to represent invalid data, a non-existent account, or a rejected transaction. Use an exception type that accurately represents the business or programming error.

## 4. What is `VirtualMachineError`?

Class declaration in Java 17:

```java
public abstract class VirtualMachineError extends Error
```

This class is used to indicate that the JVM is broken or has run out of resources necessary for it to continue operating normally. It is **abstract**, so you normally work with its concrete subclasses.

| Direct Subclass | Meaning | Common Origin / Investigation Direction |
| --- | --- | --- |
| `OutOfMemoryError` | The JVM cannot allocate requested memory/resources | Heap full, references held too long, Metaspace, or other memory/resource limits; inspect the message and environment |
| `StackOverflowError` | A thread's execution stack has overflowed | Infinite recursion, overly deep recursion, repeated method call cycles |
| `InternalError` | The JVM reports an unexpected internal error | Check JDK/JVM version, native libraries, JVM logs; may need to report a bug to the vendor |
| `UnknownError` | The JVM reports a serious error whose specific nature cannot be determined | Analyze incident details and JVM logs; do not guess from the class name alone |

### 4.1. `OutOfMemoryError`

The error message provides crucial clues, though **there is no single standard message across all JVMs**. On common HotSpot/JDK implementations, you may encounter:

- `Java heap space`: the heap region cannot satisfy an allocation request.
- `GC overhead limit exceeded`: the VM's GC checking policy detects that most of the time is being spent in GC with very little memory recovered.
- `Metaspace`: insufficient memory region for class metadata.
- `unable to create native thread`: unable to create an operating system thread; may be due to process/system resource limits.

An `OutOfMemoryError` **does not by default mean "the Java heap is full"**. Depending on the allocation type and runtime, the error may involve off-heap memory, address space, container limits, or operating system resources. The specific message and the JVM in use determine the diagnostic direction.

An excessively large single allocation can also be rejected even while the program can still perform other work. Therefore, the assumption that "any `OutOfMemoryError` immediately kills the entire process" is false. However, when the error is due to genuine resource exhaustion, **you must not assume the application state is still safe to continue serving requests**.

### 4.2. `StackOverflowError`

Each thread has a stack region for method calls, local variables, and necessary execution frames. If a program continuously recurses or creates an overly deep call chain, stack demand exceeds the limit and the JVM may throw `StackOverflowError`.

Example **for reading only, do not run**:

```java
// Incorrect illustrative example: no termination condition.
static void recurseForever() {
    recurseForever();
}
```

The proper fix is to find the missing termination condition, reduce recursion depth, or convert the algorithm to an iterative form/explicit data stack where appropriate. Increasing the stack size only shifts the failure threshold; it does not fix infinite recursion.

A `StackOverflowError` may only disrupt the work of **one thread**, without necessarily stopping all threads and the entire JVM immediately. Even so, continuing to treat a failed request as successful will mask the algorithmic bug.

### 4.3. `InternalError` and `UnknownError`

These two classes indicate issues in the runtime layer or low-level operations; it is very difficult to determine the root cause from the class name alone. When encountering them, preserve the error message, stack trace, JDK information, environment details, and related logs. `InternalError` also has specialized indirect subclasses, such as `java.util.zip.ZipError`; do not assume every `InternalError` is a "spontaneous" VM bug without inspecting the call site.

## 5. Runnable Example: Checking Inheritance Relationships

Create the file `ErrorHierarchyDemo.java`:

```java
public class ErrorHierarchyDemo {
    public static void main(String[] args) {
        System.out.println("Error parent: "
                + Error.class.getSuperclass().getSimpleName());
        System.out.println("VirtualMachineError parent: "
                + VirtualMachineError.class.getSuperclass().getSimpleName());
        System.out.println("OutOfMemoryError is VirtualMachineError: "
                + VirtualMachineError.class.isAssignableFrom(OutOfMemoryError.class));
        System.out.println("StackOverflowError is Error: "
                + Error.class.isAssignableFrom(StackOverflowError.class));
        System.out.println("AssertionError is VirtualMachineError: "
                + VirtualMachineError.class.isAssignableFrom(AssertionError.class));
    }
}
```

Compile and run with JDK 17+:

```bash
javac ErrorHierarchyDemo.java
java ErrorHierarchyDemo
```

Expected output:

```text
Error parent: Throwable
VirtualMachineError parent: Error
OutOfMemoryError is VirtualMachineError: true
StackOverflowError is Error: true
AssertionError is VirtualMachineError: false
```

`Class.isAssignableFrom(Other.class)` checks whether an instance of `Other` can be assigned to the type on the left. This example safely inspects class structure: **it does not trigger an actual resource error**.

## 6. How Does an Uncaught `Error` Affect a Thread?

The exception propagation mechanism still applies to `Error`:

1. When thrown, the JVM searches for a matching `catch` starting from the current call frame and unwinding up the call stack.
2. `catch (Exception e)` **does not catch** `Error` objects, because the two branches are separate.
3. `catch (Error e)`, `catch (VirtualMachineError e)` (if it is a subclass of this type), or `catch (Throwable t)` can match.
4. If an error escapes `Thread.run()`, the thread's uncaught exception handler (`UncaughtExceptionHandler`) can receive it. That thread terminates, but this **does not mean** all threads have terminated or that the JVM is forced to stop.
5. If the JVM terminates abruptly or has no remaining resources, normal steps such as logging, shutdown hooks, `finally`, or handlers **have no absolute guarantee** of running and completing.

### Runnable Example: Handler Receiving `AssertionError` on a Thread

This example intentionally uses `AssertionError` to **demonstrate `Error` propagation without exhausting JVM resources**. `AssertionError` is not a `VirtualMachineError`.

Create the file `UncaughtErrorDemo.java`:

```java
public class UncaughtErrorDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(
                () -> { throw new AssertionError("demo"); },
                "demo-worker"
        );

        worker.setUncaughtExceptionHandler((thread, failure) ->
                System.out.println(thread.getName() + ": "
                        + failure.getClass().getSimpleName())
        );

        worker.start();
        worker.join();
        System.out.println("main continues");
    }
}
```

```bash
javac UncaughtErrorDemo.java
java UncaughtErrorDemo
```

Output:

```text
demo-worker: AssertionError
main continues
```

`join()` makes the main thread wait for the worker to finish, so the order of the two printed lines is deterministic in this example. In a real system, if a `VirtualMachineError` occurs due to out-of-memory or a VM failure, **do not rely on the handler still being able to allocate memory, build strings, or write logs successfully**.

## 7. Practical Handling: Prevention, Diagnosis, and Recovery Decisions

### 7.1. When Designing Java Code

- **Catch intentionally.** An application typically catches `Exception` or specific exception types at boundaries where recovery is possible. Avoid a blanket `catch (Throwable)` that then returns "success" for a request.
- **Do not swallow `VirtualMachineError`.** If a special infrastructure layer must catch it to record state or perform minimal cleanup, it should rethrow it and follow the process's incident-handling policy. Catch-block code is not guaranteed to run safely if resources are already exhausted.
- **Do not retry indefinitely** after `OutOfMemoryError`/`StackOverflowError`. Retrying the same workload usually repeats the failure, clogs the system, and hides the root cause.
- **Do not use `System.gc()` as a guaranteed fix for `OutOfMemoryError`.** It is only a suggestion to run garbage collection, with no guarantee of reclaiming enough resources.
- **Use `finally` and try-with-resources for normal cleanup**, but do not treat them as a guaranteed recovery mechanism after a severe JVM failure.

An illustrative "catch-to-rethrow" pattern—**a method snippet that can be placed inside a Java class**, not a standalone `main` program:

```java
static void executeBoundary(Runnable task) {
    try {
        task.run();
    } catch (VirtualMachineError fatal) {
        // If a safe and verified recording mechanism exists, perform minimal recording here.
        // Do not turn the failure into a successful result.
        throw fatal;
    }
}
```

If the boundary does not need to perform any special action, **do not add this `catch`**: letting the error propagate naturally is usually simpler and safer. Do not treat the code snippet above as a guarantee that the JVM will be able to continue operating.

### 7.2. When Operating Applications

| Symptom | Evidence to Inspect | Sustainable Fix Direction |
| --- | --- | --- |
| `OutOfMemoryError: Java heap space` | Heap size, heap dump, allocation rate, objects retaining references | Fix leaks/overly long retention; bound caches/batches; tune memory based on measurements |
| `OutOfMemoryError` related to Metaspace/native thread | Full message, class/class loader count, thread count, OS/container limits | Find class loader leaks, thread leaks, or resource limits |
| `StackOverflowError` | Repeating frame sequence in stack trace, recursion path, offending input | Add proper termination condition, fix call cycle, reduce depth, or change algorithm |
| `InternalError`/`UnknownError` | Full message, stack trace, VM logs, JDK version/distribution, native dependencies | Isolate runtime/native code; upgrade or provide a minimal reproduction |

In HotSpot environments, `-XX:+HeapDumpOnOutOfMemoryError` can be configured to generate a heap dump upon `OutOfMemoryError`; consider disk space, sensitive data, and operational policies. This is a JVM-implementation-specific option, not something guaranteed across all VMs by the Java Language Specification.

An appropriate incident response workflow is to determine the scope of the failure, preserve sufficient evidence for diagnosis, stop or isolate the failing workload when necessary, and then fix the root cause. In systems monitored by an orchestrator or process supervisor, a restart policy can be helpful after a severe resource failure; **restarting is not a substitute for fixing leaks, infinite recursion, or misconfigured limits**.

## 8. Common Misconceptions

**"`catch (Exception)` will catch everything that can be thrown."** False. `Throwable` includes both `Exception` and `Error`; `catch (Exception)` does not catch `Error`.

**"Every `Error` is caused by a JVM bug."** False. `AssertionError` can be an application assumption failure; `NoClassDefFoundError` can stem from classpath/dependency issues or class initialization failure.

**"If `OutOfMemoryError` occurs, the heap is always full."** False. Allocation scenarios, Metaspace, thread limits, and native memory must be distinguished based on the message and environment.

**"`StackOverflowError` forces the entire JVM to exit."** False. The error may occur in a single thread; however, that unit of work fails and the recursive cause needs to be fixed.

**"Catching `VirtualMachineError` and retrying forever constitutes recovery."** False. Doing so does not guarantee that resources or application state have recovered and may worsen the outage.

**"`finally` always runs even if the JVM has died."** False. `finally` participates in normal block exit, but its execution cannot be guaranteed when the process/VM terminates abnormally.

## 9. Self-Check

1. **Is `OutOfMemoryError` a checked exception?** No. It inherits `VirtualMachineError → Error → Throwable`, which is unchecked.
2. **Does `catch (RuntimeException e)` catch `StackOverflowError`?** No. `StackOverflowError` belongs to the `Error` branch.
3. **Does `AssertionError` belong to `VirtualMachineError`?** No. Both belong to `Error`, but on different branches.
4. **If a worker thread throws an uncaught `Error`, is the JVM forced to terminate immediately?** No. Typically the failing thread terminates; whether the JVM continues or exits depends on the remaining threads and the runtime state.
5. **Is reading the error name or stack trace alone enough to diagnose `OutOfMemoryError`?** Not always. You need the full message along with resource metrics and operational context.

## 10. Authoritative References

- Java SE 17 API — [`Error`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Error.html).
- Java SE 17 API — [`VirtualMachineError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/VirtualMachineError.html).
- Java SE 17 API — [`OutOfMemoryError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/OutOfMemoryError.html), [`StackOverflowError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StackOverflowError.html).
- Java Language Specification 17 — [`11.2 Compile-Time Checking of Exceptions`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2).

Understanding the inheritance branch helps you choose the right `catch` type; understanding the root cause helps you choose the appropriate level of recovery. For `VirtualMachineError`, prioritize diagnosis, preserving evidence, and fixing the source of resource exhaustion or runtime failure.
