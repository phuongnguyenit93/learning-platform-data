# Arenas and Allocation: Closing an Arena with try-with-resources and Handling Double Close or Wrong-Thread Close

## 1. Why Must Arena Closing Be Managed?

In the Java **Foreign Function & Memory (FFM) API**, an `Arena` manages the lifecycle of memory regions and the `MemorySegment`s allocated from them. When allocating off-heap memory, knowing the address and size is not enough: the program must also know **when the memory region is valid** and **which thread is allowed to access it**.

For example:

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(ValueLayout.JAVA_INT);
    segment.set(ValueLayout.JAVA_INT, 0, 42);
    System.out.println(segment.get(ValueLayout.JAVA_INT, 0));
}
```

This is an abbreviated illustrative snippet; the standalone `ArenaCloseDemo.java` program is in section 5. When exiting `try`, Java **automatically calls `arena.close()`**. If the close succeeds, the arena's scope becomes invalid, the memory segments belonging to the scope can no longer be accessed, and the off-heap memory regions managed by the arena are reclaimed.

There are two particularly error-prone situations:

- **Double close:** `Arena.close()` is **not idempotent**. If the arena has already been closed, calling `close()` again throws `IllegalStateException`.
- **Wrong-thread close:** `Arena.ofConfined()` has an owning thread. Calling `close()` from a thread other than the owner throws `WrongThreadException`.

`try-with-resources` helps establish a clear closing point, but it **does not disable the two rules above**. The `try` syntax can still fail if you close it manually beforehand, close it from the wrong thread, or perform cleanup while another task is still using the memory.

This article uses the `Arena.ofConfined()`, `Arena.ofShared()`, `Arena.ofAuto()`, and `Arena.global()` APIs from `java.lang.foreign`. With **JDK 22+**, FFM is finalized (JEP 454); with **JDK 21**, FFM is in Third Preview (JEP 442) and requires enabling `--enable-preview` when compiling/running. The example will be tested directly on OpenJDK 24, while the JDK 21 commands are noted separately.

## 2. Arena, Scope, and MemorySegment Lifetime

An `Arena` is used to allocate memory and manage the scope of a group of resources. A `MemorySegment`, even if there is still a Java variable pointing to it, **cannot be used** after its arena closes successfully.

```text
Create Arena.ofConfined()
          │
          ▼
  allocate MemorySegment A, B, ...
          │
  get/set on owner thread
          │
          ▼
  exit try-with-resources
          │
          ▼
      arena.close()
          │
          ├─ scope().isAlive() == false
          ├─ native memory managed by the arena is freed
          └─ A, B, ... are all invalidated
                 │
                 ▼
         get/set after close
       IllegalStateException
```

This contract provides **temporal safety**: Java FFM operations that check the scope state will refuse to access memory that has already been freed. It does not mean you can ignore errors when making native downcalls or passing pointers out to a C library: the lifetime design must be consistent on both sides.

### Four Common Arena Types

| Type | Created with | Segment access permission | Explicit close? | Rule |
| --- | --- | --- | --- | --- |
| **Confined** | `Arena.ofConfined()` | Owner thread only | Yes | Only the owner thread may close |
| **Shared** | `Arena.ofShared()` | Multiple threads | Yes | Any thread may close, but must coordinate with ongoing access work |
| **Automatic** | `Arena.ofAuto()` | Multiple threads | **No** | Memory managed by runtime/GC; do not close manually |
| **Global** | `Arena.global()` | Multiple threads | **No** | JVM-wide lifecycle; do not close manually |

A confined arena is suitable for a short task on a single thread. A shared arena is appropriate when memory needs to be used by multiple threads, but it **does not automatically synchronize data** and does not automatically wait for workers to stop using it before closing. Auto/global are different lifetime types; do not use `try-with-resources` as a way to clean them up.

## 3. How Does `try-with-resources` Close an Arena?

`Arena` is `AutoCloseable`. Standard pattern:

```java
try (Arena arena = Arena.ofConfined()) {
    // Use all segments belonging to the arena within this scope.
} // Java automatically executes arena.close().
```

Execution flow:

1. Java creates the `arena` resource before running the body.
2. Inside the body, the `MemorySegment`s remain valid as long as the scope is alive and the thread is correct.
3. When exiting the body due to normal completion, `return`, or an exception, Java **attempts to call `close()`**.
4. If `close()` succeeds, the scope is no longer alive, the segments are invalidated, and the arena's memory is freed.
5. If `close()` **itself throws an exception**, the `try-with-resources` call can also fail. The `try` syntax does not guarantee that closing always succeeds when ownership/race rules are violated.

Conceptually equivalent, it can be managed manually:

```java
Arena arena = Arena.ofConfined();
try {
    // Work...
} finally {
    arena.close();
}
```

However, `try-with-resources` expresses ownership clearly and reduces the risk of forgetting `close` on return/exception paths. When two resources are declared together in a single `try (...)`, Java closes them in **reverse order** of declaration; if the body throws an exception and close also throws, the exception from close is attached as a **suppressed exception** to the primary error.

### Mistake: calling `close()` manually inside a managed block

```java
// INTENTIONALLY WRONG: Java will close the resource a second time at the end of the block.
try (Arena arena = Arena.ofConfined()) {
    arena.close(); // Successfully closed the first time.
} // Second close -> IllegalStateException.
```

**Correct approach:** let `try-with-resources` close it automatically. If early closing is needed by business semantics, adjust the scope of the `try` so that it ends earlier; do not intentionally double-close. For wrapper APIs that need an idempotent `close()`, the wrapper must have its own state/ownership mechanism; do not rely on `Arena.close()` being idempotent.

## 4. Exact Exceptions on Double Close, Wrong Thread, and In-Flight Access

According to the `Arena.close()` documentation for JDK 21/22/24, the key scenarios are:

| Situation | Result |
| --- | --- |
| Confined/shared arena already closed, calling `close()` again | `IllegalStateException` |
| Calling `close()` on `Arena.ofConfined()` from a non-owner thread | `WrongThreadException` |
| Accessing `get()/set()` on a segment after the arena has closed | `IllegalStateException` |
| Non-owner thread accessing a segment belonging to a confined arena | `WrongThreadException` |
| Closing an arena while a segment is still being accessed concurrently, such as a downcall holding the segment | May throw `IllegalStateException` |
| Calling `close()` on a global/automatic arena that does not support closing | `UnsupportedOperationException` |

**Do not confuse `WrongThreadException` with `IllegalThreadStateException`.** `WrongThreadException` (in `java.lang`) indicates an FFM operation that violates thread ownership. `IllegalStateException` on close is not necessarily a double-close; it can also relate to an unfinished memory operation.

### Distinguishing Failed Close from Successful Close

When a confined arena has `close()` called by a non-owner thread, that call **fails**. A failed call must not be treated as having freed native memory. In the verified example, the owner thread sees `scope().isAlive() == true` and still accesses the segment normally before closing it itself.

With a shared arena, if concurrent access causes `close()` to fail, the application needs to handle it according to an appropriate shutdown policy; it should not swallow the error or assume the resource is already closed. The right design is to **prevent new tasks, wait for ongoing work using the segment to finish, and then close**.

## 5. Complete Java 22+ Program: Closing Properly and Diagnosing Both Errors

The `ArenaCloseDemo.java` example below includes: in-scope/out-of-scope access, double close, closing a confined arena from another thread, and a shared arena accessed from a background thread. All threads have `join()` so that stdout follows a deterministic order and so the shared arena is not closed while a worker is still using it.

### 5.1. Create the file `ArenaCloseDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class ArenaCloseDemo {
    public static void main(String[] args) throws InterruptedException {
        MemorySegment escaped;
        try (Arena arena = Arena.ofConfined()) {
            escaped = arena.allocate(ValueLayout.JAVA_INT);
            escaped.set(ValueLayout.JAVA_INT, 0, 42);
            System.out.println("inside: " + escaped.get(ValueLayout.JAVA_INT, 0));
        }
        try {
            escaped.get(ValueLayout.JAVA_INT, 0);
        } catch (IllegalStateException expected) {
            System.out.println("after close: IllegalStateException");
        }

        Arena manual = Arena.ofConfined();
        manual.close();
        try {
            manual.close();
        } catch (IllegalStateException expected) {
            System.out.println("double close: IllegalStateException");
        }

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(ValueLayout.JAVA_INT);
            segment.set(ValueLayout.JAVA_INT, 0, 7);
            Thread other = new Thread(() -> {
                try {
                    arena.close();
                } catch (WrongThreadException expected) {
                    System.out.println("wrong-thread close: WrongThreadException");
                }
            });
            other.start();
            other.join();
            System.out.println("still alive: " + arena.scope().isAlive());
            System.out.println("owner reads: " + segment.get(ValueLayout.JAVA_INT, 0));
        }

        try (Arena shared = Arena.ofShared()) {
            MemorySegment segment = shared.allocate(ValueLayout.JAVA_INT);
            segment.set(ValueLayout.JAVA_INT, 0, 99);
            Thread reader = new Thread(() ->
                System.out.println("shared read: "
                        + segment.get(ValueLayout.JAVA_INT, 0)));
            reader.start();
            reader.join();
        }
    }
}
```

### 5.2. Compile and run on JDK 22+

In the directory containing the source:

```bash
java -version
javac -version
mkdir -p out
javac -encoding UTF-8 -d out ArenaCloseDemo.java
java -cp out ArenaCloseDemo
```

**Exact stdout, compiled and run on OpenJDK 24.0.2:**

```text
inside: 42
after close: IllegalStateException
double close: IllegalStateException
wrong-thread close: WrongThreadException
still alive: true
owner reads: 7
shared read: 99
```

### 5.3. Tracing the Output

1. `inside: 42` — the native segment is still valid inside the `try` block.
2. `after close: IllegalStateException` — Java automatically closed the arena upon exiting `try`; keeping the `escaped` reference in Java does not keep the memory belonging to the arena alive.
3. `double close: IllegalStateException` — calling `close()` a second time on the already-closed manual arena.
4. `wrong-thread close: WrongThreadException` — `other` is not the owner of `Arena.ofConfined()`.
5. `still alive: true` — failing to close from a non-owner thread does not cause the arena to be closed.
6. `owner reads: 7` — the owner can still read the valid memory region; upon exiting the block, the owner thread itself closes the arena.
7. `shared read: 99` — the background thread is allowed to read a segment from `Arena.ofShared()`; `reader.join()` ensures the thread finishes before `try` closes the shared arena.

The example avoids depending on `Exception.getMessage()`, because the message may change between JDK versions. The checks only compare the **exception type**, scope status, and written values.

## 6. Using the Same Idea on JDK 21 Preview

FFM in **JDK 21** is **Third Preview (JEP 442)**. The `Arena.ofConfined()`, `Arena.ofShared()`, and `scope().isAlive()` APIs already exist, but the JDK 21 compiler/JVM requires preview to be enabled. Use the following commands with **JDK 21**:

```bash
java -version
javac -version
mkdir -p out

javac --enable-preview --release 21 \
  -encoding UTF-8 -d out ArenaCloseDemo.java

java --enable-preview -cp out ArenaCloseDemo
```

Do not omit `--enable-preview` in the `java` step just because `javac` succeeded. Starting in **JDK 22**, FFM is finalized (JEP 454), so `--enable-preview` is not needed **just to use FFM**. The example above was **execution-tested with JDK 24**, while the JDK 21 commands are cross-checked against the preview API documentation, **with no claim that JDK 21 was actually run in this environment**.

Do not take JDK 17's `jdk.incubator.foreign` incubator API and substitute it verbatim with JDK 21/22's `java.lang.foreign` source. These are different API stages.

## 7. Handling Double-Close by Ownership

### 7.1. An Arena Should Have Only One Logical Closing Owner

A method that creates an arena and closes it before the caller uses the segment is a lifetime bug:

```java
// ILLUSTRATION OF BAD DESIGN: the returned segment is already invalidated.
static MemorySegment invalidReturn() {
    try (Arena arena = Arena.ofConfined()) {
        return arena.allocate(ValueLayout.JAVA_INT);
    }
}
```

This method can compile, but the returned `MemorySegment` can no longer be used after the arena has closed. **The continued existence of a Java object reference does not mean the native memory region is still valid.**

A proper contract is to finish processing within the scope and return a **Java value**:

```java
static int computeValue() {
    try (Arena arena = Arena.ofConfined()) {
        MemorySegment s = arena.allocate(ValueLayout.JAVA_INT);
        s.set(ValueLayout.JAVA_INT, 0, 123);
        return s.get(ValueLayout.JAVA_INT, 0);
    }
}
```

If a segment must be returned to the caller to be used longer than the creating method, you must design the caller to own the lifecycle of the **entire Arena**, or an `AutoCloseable` wrapper that closes it exactly once. Avoid having both sides assume responsibility for `close()`.

### 7.2. `scope().isAlive()` Does Not Make Close Idempotent

The following snippet can help with debugging, but it is **not a synchronization solution**:

```java
if (arena.scope().isAlive()) {
    arena.close();
}
```

On a shared arena, between those two lines another thread may have already closed it; `close` can still throw `IllegalStateException`. This is a **check-then-act race**. On a confined arena, even if the scope is alive, a non-owner still cannot close it. Therefore, a logical owner / locking mechanism is needed rather than merely checking `isAlive()`.

### 7.3. Why Should `IllegalStateException` Not Be Swallowed Unconditionally?

A `catch (IllegalStateException ignored)` around `close()` hides the real reason: double-close, in-flight memory access, or a lifecycle bug. In particular, if close fails because native work is still using the segment, continuing to run as if the memory had been freed can make the failure harder to diagnose. Only design an idempotent wrapper when your API **truly requires it**, and you must maintain the proper thread/callback constraints.

## 8. Wrong-Thread Close: Choosing Confined or Shared?

### 8.1. Confined: Same Thread Creates, Uses, and Closes

Pattern suitable for an independent worker thread:

```java
static void runOnOwnerThread() {
    try (Arena arena = Arena.ofConfined()) {
        MemorySegment s = arena.allocate(ValueLayout.JAVA_LONG);
        s.set(ValueLayout.JAVA_LONG, 0, 100L);
        // Work and cleanup on the same thread running the method.
    }
}
```

`Arena.ofConfined()` has an owner as soon as it is created. If you create an arena on the main thread and pass it to an executor, the executor **does not become the owner**. The usual fix is to **move the entire create–use–close sequence into the executor's task**, not just move the `close()` call.

If a non-owner thread has tried to close and received `WrongThreadException`, **do not retry on that same wrong thread**. Move cleanup back to the owner thread or redesign to use a shared arena if multiple threads are genuinely needed.

### 8.2. Shared: Any Thread Can Close, But Must Wait for Work to Finish

`Arena.ofShared()` does not have a single owner thread. Its segments can be accessed from multiple threads; any thread can call `close()`. However, that **does not mean closing while another thread is using the memory will always succeed**. With concurrent access or an in-flight downcall using the segment, `close()` can throw `IllegalStateException`.

A shutdown cycle should:

1. Stop dispatching new tasks that use the segment.
2. Wait for tasks currently using the memory to finish via `Future.get()`, `Thread.join()`, or an appropriate lifecycle barrier.
3. Have only one logical owner responsible for calling `close()` after there is no more in-flight access.
4. Never reuse the segment after a successful close.

**Be careful with interrupts:** if the thread waiting on `join()/get()` is interrupted, that **does not mean the worker has stopped**. When exiting `try` due to the exception, `close()` will still be attempted and may fail if the worker is using the segment. Production code needs a proper cancel/shutdown protocol and interrupt policy.

At the same time, having a shared arena **does not synchronize values**: two threads reading/writing the same `MemorySegment` still need to use locks or appropriate synchronized memory access modes to avoid data races.

## 9. Do Not Use try-with-resources to Close ofAuto/global

`Arena.ofAuto()` is managed by the runtime, while `Arena.global()` has a lifecycle tied to the JVM. These two types **do not support explicit closing**. If you put them into `try (...)` simply because the `Arena` type is `AutoCloseable`, Java will still call `close()` at the end of the block and receive `UnsupportedOperationException`.

```java
// INTENTIONALLY WRONG for block-scoped cleanup:
try (Arena arena = Arena.ofAuto()) {
    MemorySegment s = arena.allocate(ValueLayout.JAVA_BYTE);
} // close() is not supported: UnsupportedOperationException.
```

When you want to free native memory **at a clear point**, choose a confined/shared arena with a bounded lifetime that can be closed. When you genuinely want an auto/global lifetime, do not use `close()`; understand that the reclamation time or lifetime differs from a scoped `try`.

## 10. Exceptions in the Body and Exceptions from Cleanup

With `try-with-resources`:

- **Body finishes, close throws:** the close exception is propagated to the caller.
- **Body throws, close also throws:** the body exception is **primary**, and the close exception is placed in `getSuppressed()` of the primary.
- **Multiple resources:** closing occurs in reverse order of declaration; closing exceptions are also retained according to the suppressed exceptions rules.

Example intentionally creating a double-close **and** a primary exception:

```java
try (Arena arena = Arena.ofConfined()) {
    arena.close(); // Early close, not recommended.
    throw new IllegalArgumentException("work failed");
} catch (IllegalArgumentException primary) {
    System.out.println(primary.getMessage());           // work failed
    System.out.println(primary.getSuppressed().length); // 1
}
```

When the body throws, Java attempts to close automatically again, causing `IllegalStateException`. Java keeps `IllegalArgumentException` as primary and puts the close exception into suppressed. This is only an **error-illustration snippet**, not part of the `ArenaCloseDemo` program run in section 5.

Therefore, when debugging an error in the body accompanied by a cleanup anomaly, read **both the primary and suppressed exceptions**. Do not discard the close exception or obscure the root error with arbitrary logging.

## 11. Diagnosing Common Errors

| Symptom | Common cause | How to handle |
| --- | --- | --- |
| `IllegalStateException` on second `close()` | Already closed previously | One owner closes exactly once; avoid manual closing inside `try-with-resources` |
| `IllegalStateException` when accessing a segment returned from a method | The arena inside the method went out of scope | Return a Java value/copy the data or transfer ownership of the Arena to the caller |
| `WrongThreadException` when closing a confined arena | Not the owner thread | Move cleanup to the owner, or choose a synchronized shared design |
| `WrongThreadException` on `get()/set()` | Confined segment accessed on the wrong thread | Work on the owner thread or use a shared arena |
| `IllegalStateException` when closing a shared arena during a downcall | Segment is currently in use | Wait for work to finish before closing |
| `UnsupportedOperationException` when closing `ofAuto/global` | Explicit close is not supported | Do not use `try-with-resources` to close this type |
| `scope().isAlive()` is true but close still fails | Wrong thread, concurrent access, or check-then-act race | Design proper ownership and synchronization |
| `getSuppressed()` contains a close error | Body exception and close exception occurred together | Check both the primary error and the cleanup error |
| JDK 21 compile reports preview disabled | FFM is still preview in JDK 21 | `javac --enable-preview --release 21` and `java --enable-preview` |
| JDK 17 reports `java.lang.foreign` does not exist | FFM was in a different incubator API | Choose JDK 22+ or migrate source and build accordingly |

## 12. Checklist and Self-Practice Exercises

**Implementation checklist:**

- [ ] Choose the `Arena` type based on lifetime and multi-threading requirements, not just allocation syntax.
- [ ] Confined arena: the same thread creates, uses, and closes.
- [ ] Shared arena: stop dispatching and wait for all operations currently using the memory before closing.
- [ ] Use `try-with-resources` for closeable arenas with a clear lifetime.
- [ ] Do not call `close()` manually inside a `try (Arena ...)` managed automatically by Java.
- [ ] Do not close `ofAuto()/global()`.
- [ ] Do not access `MemorySegment` after the arena closes; if results are needed, copy them out to Java beforehand.
- [ ] Do not swallow `IllegalStateException`/`WrongThreadException` without understanding the lifecycle.
- [ ] When the body throws an exception, check `getSuppressed()` if cleanup can also fail.
- [ ] Check version: JDK 21 FFM preview requires flags; JDK 22+ FFM is finalized.

**Questions:**

1. Why is `try-with-resources` superior to closing an arena manually in many methods?
2. In `ArenaCloseDemo`, why is `escaped` still a Java reference, yet `get` after the block throws `IllegalStateException`?
3. What error does calling `close()` twice on the same confined arena cause? Why is `Arena.close()` not idempotent?
4. If thread A creates `Arena.ofConfined()` and thread B calls `close()`, which exception appears? Can the owner still close it?
5. Can a segment from a confined arena be used on another worker thread? What is a safe way to transfer ownership?
6. When is `Arena.ofShared()` more appropriate than confined? Why is `join()/Future.get()` still required before closing?
7. Is `scope().isAlive()` sufficient to avoid double-close when multiple threads can close a shared arena?
8. Are `Arena.ofAuto()` and `Arena.global()` suitable for `try-with-resources` to clean up memory at the exact block boundary?
9. When both the body and cleanup throw exceptions, where does Java place the second exception?
10. If using JDK 21 instead of JDK 24, which JVM/compiler flags must be changed?

**Key takeaway:** `Arena.close()` is **not idempotent** (double close → `IllegalStateException`); `Arena.ofConfined()` **may only be closed on the owner thread** (wrong thread → `WrongThreadException`). `try-with-resources` is the standard way to close confined/shared arenas when the lifetime fits cleanly within a block, but you still need to control ownership, concurrency, and cleanup exceptions.

### Official Documentation

- [Oracle JDK 22 — Arena API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html).
- [Oracle JDK 22 — Foreign Function & Memory package](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html).
- [Oracle JDK 21 — Arena Preview API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/foreign/Arena.html).
- [Oracle JDK 24 — Arena API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Arena.html).
- [Java Language Specification, `14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se22/html/jls-14.html#jls-14.20.3).
- [OpenJDK JEP 442 — FFM Third Preview](https://openjdk.org/jeps/442).
- [OpenJDK JEP 454 — FFM Final](https://openjdk.org/jeps/454).
