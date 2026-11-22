# TOCTOU and Time-of-Check to Time-of-Use Concurrency Bugs in Java

## 1. What is TOCTOU?

**TOCTOU (Time Of Check To Time Of Use)** is a type of race condition that occurs when a program **checks a condition at time T1** and then **uses the check result to perform an action at time T2**, while the state may have changed between those two points in time.

For example: checking "the inventory has at least one item", then deducting one item. Both threads see the quantity as 1; before either thread deducts, both pass the check. If each thread proceeds to deduct based on the stale result, the quantity can drop to -1 and both requests are accepted even though only one unit of stock existed.

```text
Initial state: stock = 1

Thread A                   Thread B
---------                  ---------
check stock > 0 → true
                           check stock > 0 → true
                           ... state may change ...
stock = stock - 1
                           stock = stock - 1

Possible wrong result: both succeed, stock = -1
```

**The core bug does not lie in the check being wrong at T1.** The check may be completely valid at the moment it executes, yet **no longer be a valid basis for the operation at T2**. The length of the T1–T2 gap does not need to be large: another machine instruction, a context switch, an I/O operation, or a method call can all open a window for state changes.

TOCTOU can occur between threads within the same JVM, between processes, between an application and the file system, or between multiple applications accessing a shared resource. The topic of this article is **general concurrency mechanisms in Java** and how to handle them using Java/JDK APIs; it is framework-independent.

## 2. Distinguishing TOCTOU from Data Race and Stale Read

- **TOCTOU** describes a bug at the **check–use logic** level: a condition was once true but became stale before the action. It can occur even when each individual read or write is atomic.
- **A data race under the Java Memory Model** arises when two actions access the same variable, at least one action is a write, there is no proper happens-before relationship, and they are not both volatile operations. A data race can lead to observed behavior that is difficult to reason about under the memory model.
- **Stale read** is when a thread observes an old value or uses an outdated snapshot. A stale read can contribute to TOCTOU, but not all TOCTOU bugs are caused by visibility violations.
- **Atomicity** here refers to the requirement of treating the entire "if valid, then execute" decision as **a single logical operation that cannot be interleaved at a point where an invariant could be broken**.

For example, `AtomicInteger.get()` and `AtomicInteger.decrementAndGet()` are both individually atomic operations, but the combination "`get() > 0` then `decrementAndGet()`" **does not automatically become a single atomic operation**. Similarly, `volatile` can solve visibility for a signal variable, but it does not lock state during the gap between check and use.

A TOCTOU bug cannot be fixed simply by placing `Thread.sleep()`, `Thread.yield()`, or raising thread priority: those operations do not create atomicity for the entire decision block.

## 3. Java 17+ Example: Reproducing the Bug with a Controlled Schedule

The example below uses `CountDownLatch` to **deliberately ensure both threads perform the check before either thread performs the action**. That way, the buggy output is reproduced deterministically rather than "hoping" the scheduler happens to trigger the race.

Create the file `TocTouInventory.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class TocTouInventory {

    private static boolean reserveWithCas(AtomicInteger stock) {
        while (true) {
            int observed = stock.get();
            if (observed <= 0) {
                return false;
            }
            if (stock.compareAndSet(observed, observed - 1)) {
                return true;
            }
            // State changed: re-read and try again.
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicInteger unsafeStock = new AtomicInteger(1);
        AtomicInteger unsafeAccepted = new AtomicInteger();

        CountDownLatch bothChecked = new CountDownLatch(2);
        CountDownLatch continueAfterCheck = new CountDownLatch(1);

        Runnable unsafeReservation = () -> {
            boolean wasAvailable = unsafeStock.get() > 0;
            bothChecked.countDown();

            try {
                continueAfterCheck.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            if (wasAvailable) {
                unsafeStock.decrementAndGet();
                unsafeAccepted.incrementAndGet();
            }
        };

        Thread a = new Thread(unsafeReservation, "unsafe-A");
        Thread b = new Thread(unsafeReservation, "unsafe-B");
        a.start();
        b.start();

        bothChecked.await();
        continueAfterCheck.countDown();
        a.join();
        b.join();

        System.out.println("Unsafe accepted: " + unsafeAccepted.get());
        System.out.println("Unsafe stock: " + unsafeStock.get());

        AtomicInteger safeStock = new AtomicInteger(1);
        AtomicInteger safeAccepted = new AtomicInteger();

        Runnable safeReservation = () -> {
            if (reserveWithCas(safeStock)) {
                safeAccepted.incrementAndGet();
            }
        };

        Thread c = new Thread(safeReservation, "safe-C");
        Thread d = new Thread(safeReservation, "safe-D");
        c.start();
        d.start();
        c.join();
        d.join();

        System.out.println("CAS accepted: " + safeAccepted.get());
        System.out.println("CAS stock: " + safeStock.get());
    }
}
```

Compile and run with Java 17+:

```bash
javac TocTouInventory.java
java TocTouInventory
```

When the program completes normally, the deterministic output is:

```text
Unsafe accepted: 2
Unsafe stock: -1
CAS accepted: 1
CAS stock: 0
```

**Explanation of the buggy part:**

1. `unsafeStock` starts at 1. Both threads read `unsafeStock.get() > 0` before passing `continueAfterCheck.await()`.
2. `bothChecked.await()` in `main` ensures both have saved `wasAvailable = true`. Only then does `main` release the latch for both to continue.
3. Both calls to `decrementAndGet()` are atomic; therefore they sequentially bring the quantity from 1 down to 0 and then -1. The bug still occurs because **the decision of whether to deduct was based on two stale check results**.
4. `unsafeAccepted` becomes 2. Neither request was rejected even though only one unit of stock existed.

**Explanation of the fix:** `compareAndSet(observed, observed - 1)` writes only when the current value still equals the value that was read. If another thread has already modified `stock`, CAS returns `false`; the loop re-reads. Only one thread can successfully transition 1 → 0; the other thread observes 0 and returns `false`. The decrement operation and the condition "which value was observed" are bound together at the **linearization point** of the successful CAS.

Note: `safeAccepted.incrementAndGet()` is called after a successful CAS; it is a statistics counter for the example. In an application that needs to update **multiple data fields as a single transaction**, CAS on the quantity alone does not automatically guarantee that all fields are updated atomically together.

## 4. Why is `check-then-act` Dangerous?

Common pattern:

```java
if (conditionIsTrue()) {
    performAction();
}
```

This is an **illustrative snippet**, without definitions for the two methods. It is safe only when at least one of the following conditions is proven:

- The relevant state is **immutable** over the observation window.
- Only a single actor is permitted to modify the state within the scope under consideration.
- A **uniform lock** protects both the check and the action, and all actors with write access follow the same locking protocol.
- An **atomic check-and-act** API (such as CAS or `putIfAbsent`) performs the decision as a single guaranteed operation.
- The external resource system provides an equivalent guarantee protocol, such as a unique constraint or an appropriate transaction.

If only the `check` is protected and the lock is released before `act`, the vulnerability remains. Similarly, **two separate `synchronized` blocks** on the same monitor are not necessarily sufficient if there is a gap between them that yields the monitor to another thread. You must protect the **entire invariant**, not just individual API calls.

### Example with `synchronized`

```java
final class Stock {
    private int remaining = 1;

    public synchronized boolean reserveOne() {
        if (remaining == 0) {
            return false;
        }
        remaining--;
        return true;
    }

    public synchronized int remaining() {
        return remaining;
    }
}
```

This is a **standalone class that can be used in another program**, without `main`. When all accesses updating `remaining` go through the monitor of the **same `Stock` object**, the check and decrement form a single critical section; two threads competing for the same unit of stock cannot both succeed. For this example, the condition `remaining == 0` is sufficient because `remaining` starts non-negative and only decreases via `reserveOne()`; in general design, use `remaining <= 0` to guard against invalid initial state.

**Limitation:** JVM `synchronized` only coordinates threads using the same monitor within that JVM. It cannot lock another process, another JVM, or an external service that does not participate in the same protocol.

## 5. TOCTOU with Concurrent Data Structures

A `ConcurrentHashMap` guarantees safety for its documented operations; **it does not mean that combining multiple independent calls is atomic**.

### Error-prone approach: check then write

```java
// Illustration, assuming map has already been declared:
if (!map.containsKey("invoice-7")) {
    map.put("invoice-7", "processing");
}
```

Between `containsKey` and `put`, another thread may have already inserted the same key. Both threads believe they were first. Even when all operations on the map are thread-safe, **the rule "only one party may register"** can still be violated at the logic level.

### Correct approach when registering a unique key

Use `putIfAbsent` to combine "if not present, then insert" into a per-key atomic operation.

Create the file `PutIfAbsentExample.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class PutIfAbsentExample {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, String> registrations =
                new ConcurrentHashMap<>();
        AtomicInteger winners = new AtomicInteger();

        Runnable register = () -> {
            String previous = registrations.putIfAbsent(
                    "invoice-7", Thread.currentThread().getName());
            if (previous == null) {
                winners.incrementAndGet();
            }
        };

        Thread a = new Thread(register, "A");
        Thread b = new Thread(register, "B");
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("Successful registrations: " + winners.get());
        System.out.println("Key exists: "
                + registrations.containsKey("invoice-7"));
    }
}
```

Run:

```bash
javac PutIfAbsentExample.java
java PutIfAbsentExample
```

Output:

```text
Successful registrations: 1
Key exists: true
```

The actual owner may be `A` or `B`, depending on scheduling; the example intentionally **does not print the owner** because who wins cannot be predicted. `putIfAbsent` is correct for **the rule that one value is registered for the key** in the map. It does not create a transaction encompassing side effects outside the map.

**Caution with `computeIfAbsent`:** The API may be suitable for computing a value by key, but the mapping function should not perform hard-to-repeat side effects, make reentrant calls that update the map, or run long tasks; check the specific contract of `ConcurrentHashMap` and its error-handling behavior. Do not turn a rule requiring a multi-resource transaction into "a lambda inside a map" and assume the whole thing is atomic.

## 6. TOCTOU with the File System: `exists()` Then Act

This is one of the classic cases, because the file system can be modified by **another process**, not just threads within the JVM.

### Error-prone approach

```java
// Illustration: path has already been declared.
if (!java.nio.file.Files.exists(path)) {
    java.nio.file.Files.writeString(path, "new file");
}
```

Another process can create `path` **after** `exists(path)` but **before** `writeString(path, ...)`. If the write call uses default options matching file creation or truncation behavior, the operation may affect the file that the other process just created. Conversely, when `exists(path)` returns `true`, the file may have already been deleted or replaced right before use.

**Two important notes:**

- `Files.exists(path)` returning `false` does not definitively mean "the file does not exist": if existence cannot be determined due to access or I/O errors, the result can be `false`. `Files.notExists(path)` is not the strict logical negation of `exists(path)`; both can be `false` at the same time.
- Checking permissions, file type, attributes, target name, or symbolic links prior to a subsequent operation can also create TOCTOU when the object at the path is replaced.

### Using an atomic "create only if absent" operation

In Java NIO, `Files.createFile(path)` requires that checking for the file's non-existence and creating the file be an atomic operation with respect to file system activities that can affect the directory under the API contract. If the file already exists, `FileAlreadyExistsException` is the result to handle, rather than checking beforehand and then writing.

Create the file `CreateOnlyOnce.java`:

```java
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;

public class CreateOnlyOnce {
    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("toc-demo-");
        Path file = directory.resolve("receipt.txt");

        try {
            Files.createFile(file);
            System.out.println("First creation succeeded");

            try {
                Files.createFile(file);
                System.out.println("Unexpected duplicate");
            } catch (FileAlreadyExistsException e) {
                System.out.println("Duplicate rejected");
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }
}
```

Compile and run:

```bash
javac CreateOnlyOnce.java
java CreateOnlyOnce
```

Output if the file system permits the operations and no external actor interferes with the temporary directory:

```text
First creation succeeded
Duplicate rejected
```

The example creates a **new temporary directory** and does not operate on the learner's real files. Cleanup may throw `IOException` if the environment disallows deletion or the file was modified; that is an I/O error to handle according to application requirements.

If the goal is to open a file **only when the file does not exist yet**, `StandardOpenOption.CREATE_NEW` in the channel/file-writing open API has similar conditional creation semantics. If multi-step content updates are needed, "generating a unique name" **does not** automatically turn all subsequent writes into a transaction. You must design temporary writing, verification, commit, synchronization, and error handling according to the desired semantics.

### Security-sensitive TOCTOU

Suppose a program checks that a path resides inside an allowed directory before opening the file. If between the two operations someone alters a link or path component, the program may end up using **a different object** than the one it checked. This is the **check-path-then-open** problem, which can be severe when the code has greater file access privileges than the party controlling the path.

Mitigations depend on the operating system and file system provider: restrict directory permissions, do not trust paths controlled by untrusted parties, prefer operations bound to an **already-opened object** or directory handle rather than checking a name and reopening, use options that do not follow symbolic links when appropriate, and consider `SecureDirectoryStream` if the provider supports it. `NOFOLLOW_LINKS` on **a single** check or operation does not automatically make an entire multi-step sequence of operations safe; you must consider all path components, directory modification permissions, and the API's guarantee scope.

## 7. TOCTOU When Multiple Processes or Services Share a Resource

Locks on Java objects resolve contention among threads **that all adhere to that lock** within the same JVM. They do not automatically provide atomic conditions across JVMs or across services.

Common examples:

| Business rule | Error-prone check-then-act | Required point of guarantee |
| --- | --- | --- |
| An identifier may only be created once | `exists(id)` then `insert(id)` | Unique constraint, conditional write, or atomic protocol of the storage engine |
| Do not sell more than available stock | `read(stock) > 0` then `write(stock-1)` | Atomic conditional update, compare-and-swap, or appropriate transaction |
| Each job is claimed by only one worker | `isPending(job)` then `markRunning(job)` | Conditional atomic claim, lease, or guaranteed queue mechanism |
| File may only be created once | `Files.exists` then `writeString` | Atomic create-if-absent such as `createFile` or `CREATE_NEW` |
| Only an authorized user may access a resource | `checkPermission` then use handle/resource | Permission checked at the effective operation or on the resolved object |

A **transaction** only helps if the isolation level, locks, update conditions, and storage constraints actually protect the invariant. You cannot conclude "it is already inside a transaction" means TOCTOU is eliminated without examining the exact operation types and isolation level.

**Idempotency** and unique keys are also useful for retry handling; however, idempotency must be enforced at the point of write or at the place serving as the source of truth. A cache that checks and then sends a request does not guarantee preventing duplicate tasks when multiple actors run concurrently.

## 8. How to Choose a Mitigation Mechanism

### 8.1. Combine the check and the action into a single atomic operation

This is usually the cleanest approach if the API supports it:

- `AtomicInteger.compareAndSet(expected, update)` or `AtomicReference.compareAndSet(...)` when updating a single state representable by an atomic value/object.
- `ConcurrentHashMap.putIfAbsent`, `replace(key, expected, newValue)`, `compute`, or `merge` when updating by key in a map, following each API's specific contract.
- `Files.createFile` or opening with `CREATE_NEW` when creating a file if it does not yet exist.
- Conditional updates or unique constraints of the external resource itself when multiple JVMs/processes are involved.

An atomic operation solves **only the exact invariant it covers**. CAS on one field does not guarantee atomicity across a file, a network request, and another record simultaneously.

### 8.2. Hold a lock across the entire decision block

If a mutable object has multiple related fields, using the same `synchronized` monitor or `Lock` to protect both the check and the update can be simpler than trying to combine multiple atomic variables. All write paths must follow the same mechanism; if external actors modify the data, a local lock is insufficient.

Inside the critical section, avoid slow I/O or calling untrusted/uncontrolled code to prevent holding the lock too long, increasing contention, or causing deadlocks. Do not "split the lock" by unlocking between check and update unless there is a re-validation mechanism upon updating.

### 8.3. Use versioning or optimistic concurrency

When an object has multiple fields, you can read the state together with a **version**, prepare the changes, and write only if the version still matches. If it fails, re-read and retry within a bound. This is an optimistic mechanism based on a **conditional update point** at the source of truth; comparing the version only inside the JVM and then issuing an unconditional write to an external system still has TOCTOU.

### 8.4. Handle the case where the condition is no longer true

TOCTOU does not disappear if you merely detect the failure and proceed as if it succeeded. You must define:

1. When a claim fails: return an "already claimed" message, retry with fresh data, or skip?
2. On timeout or interrupt: can you determine whether the operation occurred; is reconciliation needed?
3. When partial side effects occur: is there rollback, compensation, or idempotency?
4. When multiple resources are involved: where does the invariant live, which actor has authority to modify it, and which operation determines success?

For a CAS loop, avoid unbounded retries if requests have deadlines and contention pressure is high; measure contention and apply appropriate backoff/limits when needed.

## 9. Testing and Detecting TOCTOU

Timing bugs often rarely appear on a developer machine but erupt under higher load. **You cannot prove a program is race-free merely by running it once or adding `sleep()`.**

Valuable testing approaches:

1. Identify the **invariants** to preserve: non-negative quantity, at most one owner per key, file not overwritten, only authorized users may use the resource.
2. List the **time windows**: after reading state, after checking a condition, before writing or before opening a file.
3. Use `CountDownLatch`/`CyclicBarrier` in tests to force threads to reach the same point before proceeding, as in the inventory example.
4. Run stress tests across many threads and input sizes; monitor invariant violations, exceptions, deadlocks, throughput, and retry rates.
5. For systems outside the JVM, test **multiple independent processes** accessing concurrently, including on the file system or corresponding storage. Local locks cannot simulate external actors.
6. Inspect each mitigation at the **actual atomic point**, rather than just trusting a "thread-safe" method name. You must examine the entire logic chain.
7. Use JFR, thread dumps, and logging with thread names and contention info to trace execution paths; however, do not rely on logs to enforce execution order, because observation can also alter timing.

The `CountDownLatch` example in this article creates **deliberate** interleaving, making TOCTOU tests repeatable. A test suite still only complements sound design; the strongest evidence comes from proving that the invariant is protected by a guaranteed operation/protocol.

## 10. Common Mistakes

- **"I already used `AtomicInteger`, so there is no TOCTOU."** False if check and act are two separate atomic operations: `get()` then `decrementAndGet()` still has a time window.
- **"I already used `ConcurrentHashMap`, so `containsKey` then `put` is atomic."** False: per-method thread safety does not automatically compose into atomicity for a pair of calls.
- **"Adding `volatile` is enough."** `volatile` handles certain visibility/ordering guarantees; it does not turn multi-step logic into an atomic operation.
- **"Inserting `sleep(100)` will avoid the race."** Sleep alters the schedule, which may mask the bug or make it more likely; it does not protect the invariant.
- **"Wrapping each step in its own `synchronized` block is enough."** False if the lock is released between check and act; another thread can modify state in the gap.
- **"Java locks handle actors outside the JVM."** False: other processes are not bound by a local JVM monitor.
- **"`Files.exists(path)` guarantees the next open uses that exact file."** False: the object at the path may change or may not be accurately checkable.
- **"Retrying immediately is harmless."** Retrying can cause duplicate side effects if you do not know whether the first attempt committed; you need idempotency and a clear confirmation protocol.
- **"No errors seen in 10,000 runs means it is safe."** Insufficient: different schedules and different workloads can still expose the race.

## 11. Checklist for Applying to Java Code

Before any **check → use** block, ask yourself:

1. **What state is being checked?** Is it a JVM variable, a map, a file, a record, or a service resource?
2. **Who can modify it?** Threads in the same JVM, another process, the file system, a remote service, or another user?
3. **Does the T1–T2 window allow changes?** If so, will a stale check result cause an invariant violation?
4. **Where is the atomic point?** CAS, `synchronized` across the entire block, `putIfAbsent`, create-if-absent, a unique constraint, or a conditional update?
5. **Do all participating components use that same protocol?** A local lock does not protect an externally managed resource.
6. **What happens on contention or failure?** Retry, reject, timeout, rollback, compensation, idempotency, and re-checking the result.
7. **Are there tests proving the invariant?** Deliberate interleaving, stress tests, and verification under multiple actors.

**Remember:** a condition that is **true at check time** is not guaranteed to remain true **at use time**. Fix TOCTOU by protecting the **entire decision** at the owner of the state and handling the case where the condition changes, rather than trying to guess or control scheduler speed.
