# Identifying `WrongMethodTypeException`, `WrongThreadException`, and Closed Segment Access Errors

These three errors can appear together in an application using the **Foreign Function & Memory API (FFM)**, but they indicate **three different contract layers**: `MethodHandle` invocation signature, thread-based segment access permission, and memory lifetime tied to an `Arena`. Diagnosing the right error layer helps fix the root cause instead of just changing JVM flags or switching arena types by guesswork.

**Applicable version:** FFM examples use the official **Java 22+** API (JEP 454). On Java 17–21, FFM was still in incubator/preview stages, so package names, APIs, and compile/run flags may differ. The main example does not call native functions, so `--enable-native-access` is not required.

## 1. Quick Identification Map

| Symptom / exception | Violated contract | Common occurrence point | Check first |
| --- | --- | --- | --- |
| `java.lang.invoke.WrongMethodTypeException` | Parameter types or **return type at the call site** do not match `MethodHandle.type()`; can also be caused by incompatible adapter/composition creation | `invokeExact`, `invoke`, `asType`, combining method handles; downcall/upcall using handle | Print `handle.type()`; compare *static* types at the call site and `FunctionDescriptor` |
| `java.lang.WrongThreadException` | Using a segment/arena on an unauthorized thread | `segment.get/set` on a confined arena, `arena.allocate` or `arena.close` from another thread | Identify the thread that created `Arena.ofConfined()` and the executing thread |
| `java.lang.IllegalStateException` when accessing a segment | Scope is no longer `alive`, e.g., arena has been `close()`d | `segment.get/set` after `try-with-resources` or after closing the arena | Check `segment.scope().isAlive()` and the actual `close()` point |

**Note on the name “closed segment”:** A `MemorySegment` object is typically not closed via `segment.close()`. A **closeable arena** manages the lifetime of segments; closing the arena invalidates the scope of the associated segments. Therefore, the exception for a read/write operation on a segment after closing is usually `IllegalStateException`.

Do not infer solely from the exception message string: `IllegalStateException` has other causes as well, and when **both** thread and lifetime conditions are wrong, you should not rely on the JVM's internal check order to predict which message appears first. Reproduce each condition separately.

## 2. Visualizing the Three Contracts Before Debugging

### 2.1. Invocation Type — `MethodHandle`

In FFM, `Linker.downcallHandle(...)` returns a `MethodHandle` with a Java signature formed from `FunctionDescriptor` and how the handle was created. `MethodHandle.invokeExact` requires an **exact match** between the handle's type and the static type of the call in bytecode, **including the return type**. Even a mismatch of `int` versus `long`, a missing parameter, wrong parameter order, or using a wrapper instead of a primitive is enough to cause `WrongMethodTypeException`.

For example, a handle with `type()` of `(int)int`:

```java
MethodHandle identity = MethodHandles.identity(int.class);

int correct = (int) identity.invokeExact(7); // (int)int call
int wrong   = (int) identity.invokeExact(7L); // (long)int call: wrong
```

The snippet above is illustrative and assumes `java.lang.invoke.*` is imported, placed in a method declared `throws Throwable`. `7L` has static type `long`, while the handle requires `int`; the second line throws `WrongMethodTypeException` **before handling the return value becomes meaningful**.

An easily overlooked case is the return type. An `(int)int` handle is not equivalent to `(int)void` or `(int)long` when called with `invokeExact`. Use the correct return type cast (or call in the right type context) and check `handle.type()` instead of guessing based on actual values.

Distinguish:
- `invokeExact`: requires an exact match, **does not** automatically convert `int` to `long`, box/unbox, or adjust the signature.
- `invoke`: can apply conversions allowed by `asType`; not all conversions are valid, and it cannot fix an incorrectly declared native signature.
- `asType(MethodType)`: creates an adapter with the desired type if the conversion is valid; an impossible conversion can also lead to `WrongMethodTypeException`.
- `ClassCastException`, `IllegalArgumentException`, and `NullPointerException` may relate to data or arguments; they are **not automatically** considered `WrongMethodTypeException`.

### 2.2. Allowed Thread — `Arena.ofConfined()`

`Arena.ofConfined()` has an **owner thread**, which is the thread that created the arena. Segments allocated from that arena can only be accessed from the owner while the scope is alive. Thread B reading or writing a segment owned by A will hit `WrongThreadException`, even if the segment is not closed, its size is sufficient, and the `ValueLayout` is correct.

`Arena.ofShared()` allows access from multiple threads, but **does not automatically synchronize read/write operations** and still has a finite lifetime. A data race or `close()` timing race can still exist even after `WrongThreadException` is gone.

### 2.3. Lifetime — `Arena.close()` and `MemorySegment.Scope`

Each `MemorySegment` is tied to a `scope()`. For a closeable confined or shared arena, `close()` ends the lifetime; accessing contents via `get`, `set`, copy, etc. after the scope is dead will fail. Calling `segment.scope().isAlive()` helps observe the state, but **checking “alive” before reading does not guarantee safety** if another thread can close the shared arena between the two operations.

A Java variable can still hold a reference to a `MemorySegment` after the arena has closed; GC/reference existence **does not mean the native memory region is still valid**.

## 3. Java 22+ Lab: Reproducing All Three Errors Accurately

Create a standalone file named **`NativeErrorLab.java`**:

```java
import java.lang.WrongThreadException;
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.WrongMethodTypeException;

public class NativeErrorLab {
    public static void main(String[] args) throws Throwable {
        demoWrongMethodType();
        demoWrongThread();
        demoClosedSegment();
    }

    private static void demoWrongMethodType() throws Throwable {
        System.out.println("[method handle]");
        MethodHandle identity = MethodHandles.identity(int.class);
        System.out.println("type=" + identity.type());

        int value = (int) identity.invokeExact(17);
        System.out.println("ok=" + value);

        try {
            int unexpected = (int) identity.invokeExact(17L);
            System.out.println("unexpected=" + unexpected);
        } catch (WrongMethodTypeException ex) {
            System.out.println("failure=" + ex.getClass().getSimpleName());
        }
    }

    private static void demoWrongThread() throws InterruptedException {
        System.out.println("[wrong thread]");
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(ValueLayout.JAVA_INT);
            segment.set(ValueLayout.JAVA_INT, 0, 42);

            Thread worker = new Thread(() -> {
                System.out.println("accessibleFromWorker="
                        + segment.isAccessibleBy(Thread.currentThread()));
                try {
                    int unexpected = segment.get(ValueLayout.JAVA_INT, 0);
                    System.out.println("unexpected=" + unexpected);
                } catch (WrongThreadException ex) {
                    System.out.println("failure=" + ex.getClass().getSimpleName());
                }
            });
            worker.start();
            worker.join(); // wait for worker to finish, keep arena open
            System.out.println("ownerValue="
                    + segment.get(ValueLayout.JAVA_INT, 0));
        }
    }

    private static void demoClosedSegment() {
        System.out.println("[closed segment]");
        MemorySegment segment;

        try (Arena arena = Arena.ofConfined()) {
            segment = arena.allocate(ValueLayout.JAVA_INT);
            segment.set(ValueLayout.JAVA_INT, 0, 99);
            System.out.println("beforeClose="
                    + segment.get(ValueLayout.JAVA_INT, 0));
        } // owner closes arena here

        System.out.println("aliveAfterClose=" + segment.scope().isAlive());
        try {
            int unexpected = segment.get(ValueLayout.JAVA_INT, 0);
            System.out.println("unexpected=" + unexpected);
        } catch (IllegalStateException ex) {
            System.out.println("failure=" + ex.getClass().getSimpleName());
        }
    }
}
```

Compile/run with JDK 22 or later:

```bash
javac NativeErrorLab.java
java NativeErrorLab
```

**Expected stdout:**

```text
[method handle]
type=(int)int
ok=17
failure=WrongMethodTypeException
[wrong thread]
accessibleFromWorker=false
failure=WrongThreadException
ownerValue=42
[closed segment]
beforeClose=99
aliveAfterClose=false
failure=IllegalStateException
```

**Why are the three branches stable?**

1. The `MethodHandle` branch uses `identity(int.class)` with type `(int)int`, then intentionally calls it with `long`. It illustrates the exact type mechanism that FFM downcall handles must also follow; no C library is needed.
2. The `WrongThreadException` branch uses another Java thread to touch a **confined** arena's segment while the arena is **still open**; `join()` keeps the output order stable and the owner reads the value `42`.
3. The `IllegalStateException` branch accesses the segment only on the **same owner thread** after `try-with-resources` has closed the arena; it does not mix in a wrong-thread error. `scope().isAlive()` returns `false`.

In real applications, do not just catch these errors and continue using the same pointer/segment. The `catch` blocks in the lab are for **identification**; in production you must fix the type, thread, or lifetime contract.

## 4. Reading the Stack Trace and Identifying the Cause

### 4.1. If it is `WrongMethodTypeException`

For example, the message *may* state the expected type and the called type; the exact syntax varies by JVM version:

```text
java.lang.invoke.WrongMethodTypeException:
  expected (int)int but found (long)int
```

This is an **illustrative example of the message format**, not guaranteed exact stderr for every version. You should:

1. Print `handle.type()` right before the call. If using FFM, compare `FunctionDescriptor` and the final handle type **after adapter operations**.
2. Check the **number, order, static types of parameters, and return type at the call site**. In particular: `int` ≠ `long`, `int` ≠ `Integer` when using `invokeExact`.
3. Check how you created the downcall handle:
   - `linker.downcallHandle(address, functionDescriptor)` has a **fixed function address**, so it does not need a leading function address parameter at invocation.
   - `linker.downcallHandle(functionDescriptor)` **does not fix the address**; calling the handle requires an additional **first `MemorySegment` parameter** representing the function address (some native struct return cases also have an additional allocator argument).
4. Check the return type in `FunctionDescriptor.of(...)` or `FunctionDescriptor.ofVoid(...)`. Confusing `JAVA_LONG` with `JAVA_INT`, or omitting the cast at `invokeExact`, must be examined.
5. Fix the declaration/call site to match the ABI and `MethodType`. Only use `invoke`/`asType` when conversion is intentional and valid; do not rely on auto conversion to hide a wrong native declaration.

**FFM contract illustration (short snippet, not a complete program):**

```java
// Assume "symbol" is a valid C function address:
// int add_ints(int a, int b);
MethodHandle add = Linker.nativeLinker().downcallHandle(
        symbol,
        FunctionDescriptor.of(
                ValueLayout.JAVA_INT,
                ValueLayout.JAVA_INT,
                ValueLayout.JAVA_INT));

System.out.println(add.type());           // (int,int)int
int sum = (int) add.invokeExact(2, 3);     // correct Java types
```

The snippet above **lacks symbol loading and library definition code**, so it is only for understanding the signature. Creating a downcall handle is a **restricted** operation: the application needs appropriate native access, e.g., `java --enable-native-access=ALL-UNNAMED ...` when the caller is on the classpath. Do not call an unverified native address; declaring a `FunctionDescriptor` that mismatches the actual ABI is even more dangerous than a Java method type error and can crash the JVM.

### 4.2. If it is `WrongThreadException`

Find where `Arena.ofConfined()` is created. Common architectural mistake example:

```java
// Illustrative example: method creates confined segment on thread A.
MemorySegment segment = confinedArena.allocate(ValueLayout.JAVA_INT);

// Then submits segment to executor running on thread B:
executor.submit(() -> segment.get(ValueLayout.JAVA_INT, 0));
// Thread B is not owner -> WrongThreadException on get operation.
```

This is a snippet depending on `confinedArena`/`executor` variables in a real program, **not a standalone runnable file**.

Fixes according to the requirement:

- **No need to share the segment:** Keep allocation, read/write, and close on one owner thread; return a **copied Java value**, do not leak `MemorySegment`.
- **Must read/write from multiple threads:** Use `Arena.ofShared()` and organize synchronization, task ordering, close timing, and clear ownership. A shared arena solves *thread confinement*, not races or use-after-close.
- **Only need to transfer data to another thread:** Copy to a `byte[]` or appropriate Java structure before leaving the short-lived scope, or create a new memory region under a properly managed scope.
- **Error occurs on `arena.close()`:** A confined arena can also only be **closed by its owner thread**; do not delegate closing to another executor thread.

Debugging hints:

```java
System.out.println("currentThread=" + Thread.currentThread().getName());
System.out.println("canAccessHere="
        + segment.isAccessibleBy(Thread.currentThread()));
System.out.println("scopeAlive=" + segment.scope().isAlive());
```

The snippet above requires `segment` to exist in the usage scope; observing `false` or `true` is only a signal at a point in time. Avoid treating `Thread.getName()` as sole proof of ownership: two threads can have the same name; if needed, log `Thread.currentThread().threadId()` (Java 19+) or the `Thread` object reference.

### 4.3. If the segment is “closed” / `IllegalStateException`

Typical error example when returning a segment outside its scope:

```java
// Illustrative example: this method returns an invalidated segment.
static MemorySegment brokenSegmentFactory() {
    try (Arena arena = Arena.ofConfined()) {
        return arena.allocate(ValueLayout.JAVA_INT);
    } // close() before caller can read
}
```

The returned `MemorySegment` is still a Java reference, but its scope is dead. If the caller invokes `get(ValueLayout.JAVA_INT, 0)`, expect `IllegalStateException`.

Fixes:
1. Have the **segment usage** happen **within the arena's lifetime**, then return an independent Java data type. If an API must return a segment, clearly design **who owns the arena, who closes it, and when it is closed**, instead of creating and closing it immediately.
2. Do not call `close()` in `finally` before asynchronous tasks, callbacks, or downcalls finish using the segment. With a shared arena, coordinate task completion before closing.
3. After close, **there is no operation to “reopen” the old scope**. Create a new arena/segment or obtain the original data from a still-valid source; do not try to `reinterpret` a freed address to bypass checks.
4. Do not fix by using `Arena.global()` for all memory: a global scope has no manual close mechanism, easily leading to excessively long lifetimes. `Arena.ofAuto()` also has no manual close and has a different lifetime mechanism; only choose it when you understand the requirements.

**Distinguish two forms of `IllegalStateException`:**

- `segment.get/set(...)` after close: the segment scope is **not alive**.
- `arena.close()` called a second time, or conflicting with concurrent access: error related to **arena closing behavior**, not necessarily from a `get` on a dead segment.

Read the stack trace to see which operation threw the error. You can log `segment.scope().isAlive()`, but this is an observation, not something that extends the lifetime.

## 5. Distinguishing Errors in a Real FFM Call Chain

Consider the path:

```text
Java call site
  -> MethodHandle.invokeExact(...)
     -> Linker/downcall (FunctionDescriptor, ABI)
        -> MemorySegment arguments
           -> check if scope is alive
           -> check if thread has access
           -> native function (if valid)
```

The labels above represent **conceptual check layers**; they do not guarantee the internal order of every JVM or guarantee that a specific native function will run after all checks.

- **Wrong handle type first:** `WrongMethodTypeException` can occur right at the `invokeExact` signature; it is not sufficient evidence that the native function was called.
- **Right type, but segment cannot be used from current thread:** `WrongThreadException` can appear in `get/set` or when the linker checks `MemorySegment` arguments passed through the ABI.
- **Right type, right thread, but arena is closed:** `IllegalStateException` can occur when accessing the segment or during a downcall using a segment that is no longer alive.
- **All three conditions met, but wrong offset:** `IndexOutOfBoundsException` is a spatial bounds error, not one of the three main errors.
- **All three conditions met, but wrong alignment:** `IllegalArgumentException` may relate to layout/alignment. For native code, a wrong ABI signature can cause severe behavior that the JVM cannot fully check.
- **Restricted native call permission not granted:** `IllegalCallerException`/warning per JDK policy; resolve with appropriate native access configuration, **not** as a substitute for fixing `WrongMethodTypeException`, thread, or lifetime.

### Same `MemorySegment`, but Who “Owns” the Lifetime?

| Creation source | Thread access | Typical lifetime | Diagnostic direction |
| --- | --- | --- | --- |
| `Arena.ofConfined()` | Owner thread | Until owner calls `close()` / exits `try` | Wrong thread → `WrongThreadException`; already closed → `IllegalStateException` |
| `Arena.ofShared()` | Multiple threads | Until close; requires concurrency coordination | No confinement, but can be closed too early |
| `Arena.ofAuto()` | Multiple threads | According to scope reachability/GC | Does not use `close()`; check if data was dereferenced/dropped |
| `Arena.global()` | Multiple threads | Global scope stays alive for the JVM lifetime | Not manually closed; must consider resource management |
| `MemorySegment.ofArray(...)` | Multiple threads | Tied to Java heap/GC, not a confined arena | Typically does not hit “closed arena” like confined native examples |

## 6. Immediately Applicable Diagnostic Workflow

When logs contain one of the three errors, follow this order:

1. **Identify the operation throwing the error from the stack trace.** Is it `invokeExact`, `get/set`, or `close`? Record the actual `java -version` and the code at the reported line.
2. **If there is a `MethodHandle`**, print `handle.type()`; compare it with the parameter/return types at the call site. If using FFM, check `FunctionDescriptor`, whether the function address is already bound, and see what adapters were applied.
3. **If there is a `MemorySegment`**, record `segment.scope().isAlive()`, the calling thread, and the arena type that created the segment. Do not start debugging offset/byte order if the error indicates lifetime/thread is already wrong.
4. **Minimally reproduce each error separately** like in the lab: same thread + closed arena to test lifetime; wrong thread + open arena to test confinement; no native call to test `MethodHandle`.
5. **Fix ownership/lifetime where the data is created:** change scope design, order asynchronous work, or fix the signature. Re-run tests and integration paths; do not just catch and ignore the error.

### Self-Check Questions

**Scenario A:** `handle.type()` is `(long)int`, but `(int) handle.invokeExact(5)` is called. Expected error? **`WrongMethodTypeException`**, because `5` is `int`, requiring a `long` argument such as `5L` (assuming the handle declaration is correct).

**Scenario B:** Thread A creates `Arena.ofConfined()`, passes the segment to thread B before the arena closes. Thread B calls `get`. Expected error? **`WrongThreadException`**, because of the wrong owner thread.

**Scenario C:** Thread A creates a segment, exits `try (Arena arena = ...)`, then **the same thread A** reads the segment. Expected error? **`IllegalStateException`**, because the scope is dead.

**Scenario D:** Replace confined with a shared arena, but close the shared arena while the worker is not done. Is it guaranteed to be error-free? **No.** A shared arena allows multiple threads to access it, but does not extend the lifetime; you must wait for the worker to finish before closing.

## 7. Official References

- [Java SE 25: `MethodHandle.invokeExact`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandle.html) and [`WrongMethodTypeException`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/WrongMethodTypeException.html): static signature/return type and method handle conversions.
- [Java SE 25: `WrongThreadException`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/WrongThreadException.html): wrong-thread invocation error.
- [Java SE 25: `Arena`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Arena.html): confined/shared/global/auto, lifetime, and `close()`.
- [Java SE 25: `MemorySegment`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/MemorySegment.html) and [`MemorySegment.Scope`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/MemorySegment.Scope.html): thread/lifetime checks, `get/set`, and `scope().isAlive()`.
- [Java SE 25: `Linker`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Linker.html): downcall method handle, native signatures, and checks on segments.
- [OpenJDK JEP 454](https://openjdk.org/jeps/454): standardizing the Foreign Function & Memory API from JDK 22.
