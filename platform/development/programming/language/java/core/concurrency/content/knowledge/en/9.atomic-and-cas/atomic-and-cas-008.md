# ABA Problem and AtomicStampedReference in Java Concurrency

> **Scope:** General Java concurrency under the **Atomic & CAS** topic. This article explains the ABA phenomenon, cases where ABA can break the correctness of a lock-free algorithm, the mechanism of pairing a reference with a stamp in `AtomicStampedReference`, how to write a CAS loop, and the design limitations that must be verified. It does not cover Spring-specific APIs.

## 1. Learning Objectives

After this lesson, you will be able to:

- Describe accurately what **compare-and-set (CAS)** checks and why standard CAS does not record the full history of a value.
- Analyze the **A → B → A** transition sequence and recognize when a thread using a stale snapshot can still succeed with CAS.
- Distinguish between **ABA occurring** and **ABA causing a bug**: not every case where a value returns to A makes the program incorrect.
- Explain that `AtomicStampedReference<V>` logically stores a **pair (reference, int stamp)** and checks both during CAS.
- Use `get(int[] stampHolder)` to read the reference and stamp as **one consistent snapshot**, instead of reading the two components separately while other threads are updating them.
- Correctly write `compareAndSet(expectedReference, newReference, expectedStamp, newStamp)` and set the new stamp according to an appropriate monotonic/unique convention.
- Understand why **a stamp does not automatically protect internal mutable objects**, does not replace memory reclamation, does not make multiple states outside the pair atomic, and still carries the risk of stamp reuse.
- Write a Java 17 test with a controlled execution schedule to observe ABA with `AtomicReference` and how `AtomicStampedReference` blocks an update based on a stale version.

**Key Takeaway:** Standard CAS answers "does the current value equal the value I read?". However, many algorithms actually need a stronger question: **"is this still the same generation/state that I read?"**. A stamp provides an additional version signal to detect intermediate changes that a simple final-value check misses.

## 2. Reviewing CAS Before Discussing ABA

CAS is an atomic read-check-write operation at the atomic variable level as specified by the API. The idea:

```text
compareAndSet(expected, update):

    if current still equals expected:
        current = update
        return true
    else:
        keep current unchanged
        return false
```

`AtomicReference<V>` is a Java SE class that uses CAS on **an object reference**. Example:

```java
AtomicReference<String> state = new AtomicReference<>("A");
boolean changed = state.compareAndSet("A", "B");
```

This is an **illustrative snippet**, requiring `import java.util.concurrent.atomic.AtomicReference;`. For reference CAS, the comparison is **reference identity (`==`)**, not `String.equals()`. The snippet uses string literals for clarity, but real applications must understand the identity of individual objects; in the full runnable example below, we intentionally create separate `A`, `B`, and `C` objects and keep the same reference throughout the test.

CAS solves the **atomicity of a single update**: between checking `expected` and writing `update`, no other thread can interleave an update on the same atomic variable. However, CAS **does not store previously occurring states**. If the current value equals `expected` again, standard CAS may treat the condition as satisfied, even if multiple updates happened in between.

### CAS Loop Example

```java
// Illustrative snippet inside a method:
// ref is an initialized AtomicReference<State>;
// transform(State) returns a new state without side effects.
for (;;) {
    State observed = ref.get();
    State next = transform(observed);
    if (ref.compareAndSet(observed, next)) {
        break;
    }
}
```

This is **illustrative code, not a standalone program**: `State`, `ref`, and `transform()` need to be defined. The loop retries because another thread might change the reference before our CAS executes.

**Important Note:** A CAS loop that fails and retries handles many common races, but it **does not automatically solve ABA**. When the value has gone A→B→A, the stale CAS **does not fail**; there is no opportunity to trigger a retry.

## 3. The ABA Problem: A → B → A

Suppose thread T1 reads the current reference as A and prepares to update it. Before T1 executes CAS, thread T2 changes A→B, then B→A.

```text
Time                  Thread T1                    Thread T2
-------------------   ---------------------------- --------------------------------
t0                    read current = A
t1                                                 CAS A -> B succeeds
t2                                                 CAS B -> A succeeds
t3                    CAS(expected=A, update=C)
t4                    -> succeeds because current=A
```

At t3, the reference identity check still passes: **the final value points back to the same object A**. CAS cannot distinguish the A state at t0 from the A state at t2. This is the **ABA** phenomenon.

If T1 only needs to set the value to C **as long as `current` is currently A**, the result may still be correct. However, if T1 made a decision based on the assumption **"nobody has changed the state since I observed it"**, then a successful CAS is **too weak** a signal.

### ABA Is Not Synonymous with an Unsynchronized Data Race

With `AtomicReference`, every read/CAS on the reference still has proper atomic memory semantics according to the API. ABA can occur **even when all accesses to the atomic variable are properly synchronized**.

Therefore:

- **Data race / missing happens-before** is a memory model issue.
- **ABA** is typically a **logic/versioning** issue in optimistic/lock-free algorithms: the current data may equal the read data, but the change history invalidates the old reasoning.
- Using `volatile` or ensuring visibility alone **cannot recover the change history** if only a single value is stored.
- A successful CAS guarantees the atomicity of the CAS operation itself; it **does not guarantee** that dependent data previously observed by T1 is still valid.

## 4. When Is ABA Actually Dangerous?

### Lock-Free Stack Scenario (Conceptual Model)

Suppose a stack uses an `AtomicReference<Node> head` and each node has a `next` field:

```text
Before:
head -> A -> B -> C

Thread T1:
  read oldHead = A
  read next = B
  prepare CAS(head, A, B)

Thread T2:
  pop A
  pop B
  push the same object A back (A's next is now C)
  head is A again

Thread T1:
  CAS(head, A, B) succeeds
```

T1 still holds reference A with matching identity, so CAS can succeed, but it uses **`next=B` read from an older structural generation**. Meanwhile, B may have already been removed from the stack, so setting `head=B` can corrupt the logical structure, lose nodes, or reintroduce an invalid node into the stack.

This is a **conceptual diagram**, not a complete lock-free stack implementation. Real implementations must consider node reuse, `next` mutation constraints, publication, progress guarantees, memory reclamation, and proving linearizability of the entire algorithm.

**The root cause of the bug is not merely that `head` returned to A.** The bug occurs because T1 is using **information dependent on a structural generation that has changed**, while CAS only verifies a single `head` reference.

### Another Scenario: Workflow State

Suppose a job's state is `READY`. T1 reads `READY` and decides to execute step X after a slow computation. Meanwhile, T2 transitions `READY→RUNNING→READY` for a new processing cycle. T1 performs CAS `READY→RUNNING` and thinks it has "acquired the lock" for the initial cycle. If processing must be tied to the exact **job run**, a version/generation is required; checking only the `READY` enum is insufficient.

In this scenario, sometimes a better approach is to model the state with an immutable **generation ID**, rather than necessarily using `AtomicStampedReference`. Choose based on the actual invariant.

## 5. How Does Java Solve This Type of ABA?

`AtomicStampedReference<V>` belongs to `java.util.concurrent.atomic`. It manages **a logical pair**:

```text
(reference, stamp)
```

Where:

- `reference` is the reference to object `V`.
- `stamp` is an `int` whose meaning is defined by **the programmer**, commonly used as a version/generation.
- The CAS operation checks **both `expectedReference` and `expectedStamp`**, and then updates **both `newReference` and `newStamp`** as an atomic operation on the pair.

Creating the variable:

```java
AtomicStampedReference<String> state =
        new AtomicStampedReference<>(initialReference, 0);
```

This is an **illustrative snippet inside a method or field initializer**, requiring `import java.util.concurrent.atomic.AtomicStampedReference;`; `initialReference` is an existing variable.

Transition sequence:

```text
Before: (A, 0)
T2:     (A, 0) -> (B, 1)
T2:     (B, 1) -> (A, 2)
T1:     wants to CAS from (A, 0) to (C, 1)

Result: FAIL, because current = (A, 2), no longer (A, 0).
```

Even though the final reference is still A, **the version is different**. If T1 truly wants to update the new generation, it must **re-read the pair `(A, 2)`, recompute the next step based on the new data**, and then attempt a new CAS.

### Meaning of the Name "StampedReference"

Do not assume the stamp is "auto-generated" or an OS timestamp. `AtomicStampedReference` **does not auto-increment the stamp**: every `compareAndSet` or `set` call requires the caller to provide the new stamp. If the caller reuses an old stamp or resets it to 0, ABA can return.

A common convention:

```text
current = (reference, version)
successful logical mutation:
    nextVersion = version + 1
    CAS(currentReference, nextReference, version, nextVersion)
```

This convention must be applied **across all relevant update paths**. Calls to `set()`, `attemptStamp()`, and retry logic must all follow the same versioning policy. Do not treat an `int` version as permanently unique: an `int` can overflow and wrap around to old values after enough increments, or be intentionally reused by the caller.

## 6. Core APIs of AtomicStampedReference

| API | Role | Key Notes |
|---|---|---|
| `new AtomicStampedReference<>(initialRef, initialStamp)` | Initialize the pair | `initialStamp` is completely chosen by the caller |
| `getReference()` | Get the current reference | Reads only one component at the time of the call |
| `getStamp()` | Get the current stamp | Reads only one component at the time of the call |
| `get(int[] stampHolder)` | Get the reference and write the stamp into `stampHolder[0]` | **Recommended way to obtain a consistent pair snapshot** |
| `compareAndSet(expectedRef, newRef, expectedStamp, newStamp)` | Atomic CAS for the pair | Compares reference by **identity** and stamp by integer value |
| `set(newRef, newStamp)` | Set a new pair | Does not check expected values; caller must enforce policy/version |
| `attemptStamp(expectedRef, newStamp)` | Attempt to update the stamp if current reference equals `expectedRef` | Useful when you genuinely want to change the version without changing the reference |
| `weakCompareAndSet(...)` | Weak CAS API | For the Java 17 API of this class, consult the specific specification; do not blindly substitute it for progress or performance guarantees |

**Critical point to remember:** calling `getReference()` followed by `getStamp()` is **two separate operations**. If another thread updates the pair in between, you may construct an `expectedReference`/`stamp` pair that **never existed simultaneously**. Use `get(stampHolder)` to read both from the same snapshot.

Example:

```java
int[] holder = new int[1];
String expectedRef = stamped.get(holder);
int expectedStamp = holder[0];

// Compute the next state from the same snapshot:
String desiredRef = nextReference(expectedRef);
int desiredStamp = expectedStamp + 1;

boolean success = stamped.compareAndSet(
        expectedRef, desiredRef, expectedStamp, desiredStamp);
```

This is an **illustrative snippet inside a method**, assuming `stamped` and `nextReference()` are declared outside. `holder` must have at least one element; with `get`, Java writes the stamp into index 0.

A **failed** CAS is not a runtime error: another thread may have just updated the pair. Applications typically re-read the state, recompute `desired`, and retry if the contract allows, or return a "conflict" result to the caller.

## 7. Standalone Java 17 Example: ABA with AtomicReference and AtomicStampedReference

To avoid depending on whether "the scheduler happens to trigger ABA", the program below **explicitly orders execution using `Thread.join()`**:

1. The main thread holds a stale snapshot.
2. Another thread completes A→B→A and terminates.
3. The main thread then executes CAS with the stale snapshot.
4. Repeat the process with a stamped pair.

We use **three distinct `String` objects** and compare by reference identity to avoid confusion between `==` and `equals()`. Completing `join()` ensures the main thread observes the worker's updates after the worker finishes.

Create the file **`AbaStampedDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.atomic.AtomicStampedReference;

public class AbaStampedDemo {
    private static final String A = new String("A");
    private static final String B = new String("B");
    private static final String C = new String("C");

    public static void main(String[] args) throws InterruptedException {
        AtomicReference<String> plain = new AtomicReference<>(A);
        String oldReference = plain.get();
        Thread firstChanger = new Thread(() -> {
            if (!plain.compareAndSet(A, B) || !plain.compareAndSet(B, A)) {
                throw new AssertionError("unexpected plain CAS failure");
            }
        });
        firstChanger.start();
        firstChanger.join();

        System.out.println("plainBackToA=" + (plain.get() == A));
        System.out.println("plainStaleCas=" + plain.compareAndSet(oldReference, C));
        System.out.println("plainNowC=" + (plain.get() == C));

        AtomicStampedReference<String> stamped = new AtomicStampedReference<>(A, 0);
        int[] stampHolder = new int[1];
        String originalReference = stamped.get(stampHolder);
        int originalStamp = stampHolder[0];

        Thread secondChanger = new Thread(() -> {
            if (!stamped.compareAndSet(A, B, 0, 1)
                    || !stamped.compareAndSet(B, A, 1, 2)) {
                throw new AssertionError("unexpected stamped CAS failure");
            }
        });
        secondChanger.start();
        secondChanger.join();

        System.out.println("stampedBackToA=" + (stamped.getReference() == A));
        System.out.println("stampedVersion=" + stamped.getStamp());
        System.out.println("stampedStaleCas="
                + stamped.compareAndSet(originalReference, C, originalStamp, originalStamp + 1));

        int[] latestStampHolder = new int[1];
        String latestReference = stamped.get(latestStampHolder);
        boolean freshCas = stamped.compareAndSet(
                latestReference, C, latestStampHolder[0], latestStampHolder[0] + 1);

        System.out.println("stampedFreshCas=" + freshCas);
        System.out.println("stampedFinalVersion=" + stamped.getStamp());
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac --release 17 AbaStampedDemo.java
java AbaStampedDemo
```

**Verified compiled and executed stdout:**

```text
plainBackToA=true
plainStaleCas=true
plainNowC=true
stampedBackToA=true
stampedVersion=2
stampedStaleCas=false
stampedFreshCas=true
stampedFinalVersion=3
```

### Step-by-Step Explanation

**`AtomicReference` section:**

- T1/main reads `oldReference = A`.
- The worker uses CAS to transition **the exact object reference** A→B→A. Both CAS operations succeed; after `join()`, `current` is object A again.
- `plain.compareAndSet(oldReference, C)` returns `true` because CAS only sees reference A with matching identity at the time of update. **It has no knowledge that B ever existed.**
- `plainNowC=true` only shows that CAS succeeded; if the algorithm's contract requires detecting any change since the read, this condition is insufficient.

**`AtomicStampedReference` section:**

- T1 reads `(originalReference=A, originalStamp=0)` simultaneously via `get(holder)`.
- The worker performs `(A,0) → (B,1) → (A,2)`.
- T1 attempts `compareAndSet(A, C, 0, 1)`. The current reference matches A, but the current stamp is 2, **which differs from the expected stamp 0**, so it returns `false`.
- T1 re-reads `(A,2)` and performs a new CAS with expected stamp 2 and desired stamp 3. This time it succeeds because **no other thread interleaved** between the new snapshot and the new CAS in this example.
- `stampedFinalVersion=3` is the result of the version-increment convention we chose, **not because the class automatically increments the stamp**.

**Why does the example use `join()`?** When illustrating two clear execution schedules, it allows the worker to complete ABA before main performs CAS. In real workloads, ABA happens due to thread interleaving; you cannot rely on natural scheduling to observe it consistently. Placing checkpoints like this is a testing technique, not a guideline for implementing lock-free algorithms.

**Note on exceptions inside a Thread:** if an `AssertionError` unexpectedly occurs inside the lambda, `join()` does not automatically rethrow it to main like `Future.get()` does; in this demo, we verified both worker CAS calls succeeded. Production tests need an explicit error-reporting channel, such as `Future` or capturing `Throwable`, so assertions can fail the test.

## 8. Writing a Logically Safe Stamped CAS Loop

When computing a new state from the read reference, the common pattern is:

```java
// Illustrative snippet inside a method: ref is AtomicStampedReference<State>.
// computeNext(State) only computes, with no side effects.
for (;;) {
    int[] stampBox = new int[1];
    State observed = ref.get(stampBox);
    int seenVersion = stampBox[0];

    State next = computeNext(observed);
    int nextVersion = seenVersion + 1;

    if (ref.compareAndSet(observed, next, seenVersion, nextVersion)) {
        break;
    }
    // Pair changed: re-read and compute next based on the new snapshot.
}
```

This is **illustrative code**, not a standalone program; `State`, `ref`, and `computeNext()` must exist in the class. For complex algorithms, you must separately analyze the correctness of `computeNext`, the relationship between state outside the reference and the reference CAS, the version reuse policy, and how contention is handled.

### Do Not Put Non-Idempotent Side Effects Inside a CAS Loop

An example that is unsafe in intent:

```java
// Incorrect illustration: side effect may run multiple times when CAS fails.
for (;;) {
    int[] stampBox = new int[1];
    State s = ref.get(stampBox);
    sendEmail(); // Could send duplicates if CAS fails multiple times!
    if (ref.compareAndSet(s, update(s), stampBox[0], stampBox[0] + 1)) {
        break;
    }
}
```

This is an **erroneous illustrative snippet**; `State`, `ref`, `sendEmail()`, and `update()` belong to an external context. A CAS loop may retry multiple times, so side effects like sending emails, calling paid APIs, debiting external accounts outside the JVM, or writing audit logs must be handled separately via transactions, idempotency, or a commit protocol.

A better pattern is to compute `next` purely, perform CAS, and then **after it succeeds**, trigger the side effect with a separate deduplication/error-handling mechanism. Even performing side effects after CAS does not make an external operation atomic with the CAS: the thread/process can crash between the two steps, so an outbox/idempotency or transaction pattern is needed when required by the problem.

### Do Not Infer Progress/Fairness Automatically

`AtomicStampedReference` helps avoid a class of false-success CAS operations, but it does not guarantee that a specific thread will eventually succeed. Under very high contention, a thread may retry for a long time. Being a **lock-free algorithm** is a property of the **entire algorithm**, not a property inferred from having an `AtomicStampedReference` in the code. An algorithm that uses atomics but performs blocking I/O, waits on a condition, or has cyclic dependencies may still not be lock-free.

## 9. Reading a Snapshot Correctly: `get(holder)` Instead of Two Separate Calls

A subtle bug:

```java
// Illustrating the risk of an inconsistent snapshot.
State refSnapshot = stamped.getReference();
int stampSnapshot = stamped.getStamp();
```

This is illustrative code where `stamped` is an `AtomicStampedReference<State>`. Between the two calls, another thread can change the pair:

```text
Before:         (A, 10)
T1 getReference -> A
T2 updates:     (B, 11)
T1 getStamp     -> 11

T1 obtains (A, 11), even though that pair never existed at any observed moment.
```

T1 can make wrong inferences even before CAS. If it executes CAS, the CAS will usually fail because the mismatched pair does not match the current state, but **you should not rely on a failed CAS to compensate for reading skewed state**.

Correct pattern:

```java
int[] stampBox = new int[1];
State refSnapshot = stamped.get(stampBox);
int stampSnapshot = stampBox[0];
```

Both values reflect **the same logical snapshot** according to the `get(int[])` contract. If T2 modifies the pair after T1 reads it, CAS with the old expected pair will fail unless that exact pair is recreated.

**Note:** this is not an atomic snapshot of every field inside `State`. If `State` is a mutable object and another thread is modifying its fields, `get(holder)` only captures **the reference and the stamp**; it does not freeze the object graph.

## 10. Identity vs. Equality Comparison

`AtomicReference.compareAndSet()` and `AtomicStampedReference.compareAndSet()` check **reference identity**—meaning the exact same object—rather than calling `equals()`. Example:

```java
String a1 = new String("A");
String a2 = new String("A");

System.out.println(a1.equals(a2)); // true
System.out.println(a1 == a2);      // false
```

The snippet above can be placed in any `main` method without imports. If `AtomicStampedReference<String>` currently holds `a1`, then:

```java
// Illustration with stamped holding (a1, 5).
boolean ok = stamped.compareAndSet(a2, a1, 5, 6);
// ok == false: a2 does not have the same identity as a1.
```

This is an **illustrative snippet** with `stamped`, `a1`, and `a2` already declared. The stamp matches, but the reference **does not match**. In our main runnable example, we intentionally kept A/B/C as three distinct objects and reused the same instance A when returning, so that ABA occurs in the reference-identity CAS sense.

**Do not arbitrarily create new wrapper objects** and assume that "value A returning to A" is enough to trigger ABA on `AtomicReference`. For reference CAS, `current` must return to **the exact same object reference** that was observed, or another design with a shared token value must be involved. In real lock-free data structures, **node/reference reuse** is what makes ABA dangerous.

## 11. A Stamp Does Not Automatically Protect Internal Objects

Example:

```java
final class MutablePayload {
    int amount;
}

// Illustration: ref holds a MutablePayload with stamp=4.
// Thread T2 holds the same payload and sets payload.amount = 999
// WITHOUT updating the pair in AtomicStampedReference.
```

This is an illustrative class and description. T1 can read the reference/stamp `(payload, 4)`, T2 mutates `payload.amount` outside the atomic container, and then T1's CAS based on stamp 4 still succeeds. **The stamp did not change**, so it does not detect mutations of the referent. If concurrent writes to regular fields happen without synchronization, there is also a risk of a **data race** under the JMM.

A sound policy can be:

- Store only **immutable state objects** in `AtomicStampedReference`; every change creates a new state object and replaces the pair via CAS.
- Or protect mutations of a mutable referent with another explicit lock/ownership protocol, and ensure the stamp is updated when required.
- Do not publish mutable references for other threads to modify arbitrarily while the algorithm relies on snapshot immutability.

**Similarly for multi-level object graphs:** performing CAS on an atomic reference does not make a file write, a database update, or changes across three independent collections into a single unified transaction.

## 12. Stamp Overflow, Reuse, and Limits of ABA Prevention

`stamp` is a Java `int` (32-bit, signed). If every update uses `stamp + 1`, addition can **overflow** and wrap around through old values. After enough updates, a pair `(A, oldStamp)` can theoretically **reappear**.

Beyond overflow, ABA can still occur if the code:

- Uses `set(A, oldStamp)` after the state has changed.
- Resets the stamp to 0 on reload/reinitialize while old readers still exist.
- Has multiple writers choosing `newStamp` independently without following a monotonic version policy.
- Uses `attemptStamp` or other update paths without obeying the versioning rule.
- Applies modulo over a small set of stamps, causing pairs to be reused very quickly.

Therefore, `AtomicStampedReference` **significantly reduces the risk of generation-based stale CAS when versions are managed properly**, but it does not provide a guarantee of "never ABA under any circumstances".

### Choosing a Version Strategy

Depending on requirements:

1. **Short-lived programs with bounded mutations:** an `int` stamp incremented monotonically within a valid range may suffice; you must verify it cannot wrap/reuse while long-lived observers exist.
2. **Strict requirement that generations never collide:** design a larger version domain, immutable state carrying a generation/`UUID`, or an appropriate epoch-management mechanism. `AtomicStampedReference` **only provides an `int` stamp**; do not pretend it is a `long`/`UUID`.
3. **Structures with node reuse:** combine version tagging with the structure's ownership/reclamation mechanism; versioning alone does not solve all node lifecycle issues.
4. **No need to track generations:** do not add a stamp just because you heard CAS "has ABA"; adding complexity brings no correctness benefit if the invariant truly depends only on the current value.

In other words, before using a stamped reference, determine **how long an observer can hold a stale snapshot**, the update rate of the pair, and the possibility of lifecycle/version wrap-around.

## 13. Is AtomicMarkableReference Equivalent?

Java also has `AtomicMarkableReference<V>`, which manages a `(reference, boolean mark)` pair. A boolean mark is very useful in algorithms that use logical marking, such as "has this node been logically deleted?". However, for detecting **how many generations have passed**, a single mark bit can cycle 0→1→0 and is insufficient to distinguish all ABA cases.

| Class/API | Atomic State Managed | Best Suited For |
|---|---|---|
| `AtomicReference<V>` | A single reference | State transitions that only need to check current identity |
| `AtomicStampedReference<V>` | Reference + `int stamp` | Checking a version/generation alongside the reference |
| `AtomicMarkableReference<V>` | Reference + boolean mark | Needing an extra mark state, e.g., logical deletion |
| `AtomicInteger` / `AtomicLong` | A single numeric value | Counters/flags/atomic integer operations |
| `synchronized` / `ReentrantLock` | Critical section protecting multiple fields | Needing logical atomic transactions across multiple values, not necessarily lock-free |

No single class is inherently "best". The decision depends on the **semantics of the invariant**: do you need to prevent other writers from updating concurrently, detect version history, or mark logical removal?

## 14. Stamps and Linearizability

**Linearizability** is the property that a concurrent operation can be viewed as taking effect at a single atomic point between its invocation and its response, while respecting the real-time order of non-overlapping operations.

With `AtomicStampedReference.compareAndSet`, checking and updating **the `(reference, stamp)` pair** is a single atomic action, helping programmers establish a linearization point for the pair-update operation.

However:

- An entire business method may perform many steps besides CAS: reading data, validating, writing side effects, publishing events.
- A single atomic CAS **does not automatically make the entire method linearizable**.
- If two fields outside the atomic pair must transition together, you need another protocol protecting the group or combine them into **one immutable state object** replaced atomically.
- If readers need to see the new generation and a consistent payload, the payload must be safely constructed/published and not mutated improperly afterward.
- If ownership/reclamation invalidates a node while a reader is using it, a stamp on `head` does not automatically protect the reader from all lifecycle bugs.

This is why an `AtomicStampedReference` example passing a few runs **is not proof** that a complete lock-free linked list or stack implementation is correct.

## 15. How Does the Java Memory Model Relate?

The atomic classes in `java.util.concurrent.atomic` define memory effects for their operations. On Java 17, normal reads via `AtomicReference.get()` and atomic CAS operations have API-specified memory effects compatible with the rules for `volatile` and atomic read-modify-write operations.

A `get(holder)` snapshot suffices to obtain a consistent reference/stamp pair and a CAS updates the pair atomically, but you must still consider:

- **Publication of the referenced object:** if an object is created and properly published through an atomic container, the writes preparing its data before publication are coordinated according to the appropriate memory semantics.
- **Mutability after publication:** if multiple threads concurrently modify regular fields inside the object, the atomic pair does not give those writes mutual exclusion or make them atomically visible.
- **Do not rely on `Thread.sleep` for ordering:** yielding the CPU or waiting for a duration is not a happens-before relationship that replaces atomics, locks, latches, or `join`.
- **CAS loops can fail due to contention:** handle retries/failures according to the contract; do not infer from a single failure that ABA definitely occurred—any concurrent update can invalidate the expected pair.

In the hands-on example, `Thread.join()` fixes the order of test steps and ensures the worker finishes before main continues. In real concurrent algorithms, correctness must hold **under any valid interleaving** permitted by the contract.

## 16. Do Not Confuse ABA with Other Issues

| Symptom | Possible Cause | Analysis Method |
|---|---|---|
| CAS fails repeatedly under contention | Concurrent updates / retry starvation | Measure retry counts, re-read expected and new state |
| CAS succeeds after A→B→A but based on a stale snapshot | ABA causing a stale decision | Add generation/stamp if the invariant requires it |
| CAS succeeds but readers see corrupted mutable fields | Data race on the referent | Check safe publication and payload ownership/locking |
| Two fields are inconsistent even though each uses an atomic | Split multi-field invariant | Combine state into an immutable snapshot or lock the whole transaction |
| A node in a stack is reused with a stale `next` | ABA and lifecycle/node reuse | Version tagging + algorithm/reclamation audit |
| Consumers receive duplicate events due to retries | Side effect placed inside the CAS loop | Separate side effects from retries; use idempotency/outbox |
| Version wraps back to the initial value | Stamp wrap-around/reuse | Review versioning policy and snapshot lifetime |
| Output order between two threads changes | Nondeterministic scheduling | Check business requirements; not ABA if there is no stale-snapshot false success |

Using the same blanket term "race condition" for every bug makes it easy to pick the wrong tool. Identify **what was read, when the value changed, and what the final operation actually verified**.

## 17. Designing Versions and Invariants: A Logical Resource Example

Suppose a system state contains `RecordState(id, status, generation)`. Thread T1 reads the state "READY generation 7" and prepares a processing step. Thread T2 might finish generation 7, initialize generation 8, and return `status` to `READY`.

If T1 only performs CAS on the enum `READY→RUNNING`, it cannot distinguish the two processing cycles. If processing must be bound to the exact generation, the check when claiming ownership must expect **generation 7**.

There are two common modeling approaches:

**Approach A — AtomicStampedReference:** the reference is a token/immutable state and the stamp is the generation, incrementing the stamp on each transition. Consumers use `get(holder)` and then CAS the expected pair.

**Approach B — AtomicReference to an immutable object with generation:** the reference points to a new record for each transition. Readers only CAS from **the exact old snapshot object** to the new state object. If old instances are never reused, reference identity differs for every generation, eliminating ABA caused by returning to **the same reference** in that model. However, you must control all update paths and never reuse object snapshots.

Approach B fits well when multiple fields form a single invariant that must be updated atomically. Approach A makes sense when the current reference can return to the same identity while versions still need to be distinguished. There is no mechanical one-to-one substitution without evaluating data types and design constraints.

## 18. Common Implementation Mistakes

1. **Calling `getReference()` and `getStamp()` separately and trusting it as a snapshot.** An update can happen in between. Use `get(holder)`.
2. **Only incrementing the stamp when the reference changes.** If a logical operation changes generations and returns to the same reference, you have recreated ABA; enforce a version convention for **every meaningful mutation**.
3. **Arbitrarily resetting the stamp with `set`.** This can reuse an old pair still held by an observer.
4. **Assuming the class auto-increments the stamp.** Every `newStamp` is supplied by the caller. `compareAndSet` does not increment it automatically.
5. **Using `equals()` to select the expected object.** Reference CAS compares using `==`; two objects with equal contents do not necessarily share the same reference.
6. **Holding a mutable payload and mutating its fields directly.** A stamp does not automatically detect mutations outside the container.
7. **Placing email/network writes inside a CAS retry loop.** Retries can repeat side effects. Separate idempotency/transaction handling is required.
8. **Assuming an `int` stamp is unique indefinitely.** Overflow or manual reuse can recreate an old pair.
9. **Overusing `AtomicStampedReference` for every counter.** If the invariant only requires atomic incrementing, `AtomicInteger.incrementAndGet` is simpler.
10. **Assuming ABA always produces wrong results.** If the decision depends only on the current state A, ABA may have no impact. You must identify the violated stale assumption.
11. **Assuming a CAS on `head` protects all node fields.** The algorithm must prove both the structure and node lifecycle, not just `head`.
12. **Not handling CAS failures.** Failures can be normal contention; code must retry, return a conflict, or apply another strategy.
13. **Computing `desired` state from an old snapshot and retrying CAS with the new expected values without recomputing.** The new result may be based on an outdated invariant.
14. **Thinking a stamp is a wall-clock timestamp.** It is a caller-managed `int`; it has no inherent relationship to real time.
15. **Assuming solving ABA implies lock-freedom, wait-freedom, and fairness.** Those are separate properties of the entire algorithm.
16. **Inferring from a single passing test that ABA can no longer happen.** You must analyze all stamp-modification paths and lifecycle/version bounds.

## 19. How to Test ABA Reproducibly

A more effective testing strategy than jumping straight to random stress testing:

1. **Define the invariant:** e.g., "if the state has gone through another generation since I read it, do not commit based on the stale snapshot."
2. **Capture the initial snapshot:** thread T1 reads A and (if applicable) version 0.
3. **Force the schedule:** use `CountDownLatch`, `CyclicBarrier`, or `Thread.join()` so T2 completes A→B→A while T1 still holds the old expected values.
4. **Attempt T1's CAS:** `AtomicReference` will accept it if the identity is A; stamped CAS with version 0 will fail if the current version is 2.
5. **Re-read and verify retry:** T1 reads the new pair and recomputes `desired`; if there is no further contention, CAS can succeed.
6. **Check payload/structure invariants:** do not assert only the `true`/`false` return of CAS; if the algorithm is a stack, verify no nodes are lost, no cycles are created, and no invalid nodes are accessed.
7. **Test failure paths:** intentionally reset the stamp, skip incrementing the version, or mutate the referent internally to see what `AtomicStampedReference` does not guarantee.
8. **Run stress/real contention tests:** multiple threads, many iterations, controlled random inputs, and assertions. A failure is proof of a bug; many passing runs are not proof of formal correctness.

In the runnable demo, `Thread.join()` is a simple way to force T2 to finish before T1's CAS. In a real lock-free algorithm test, one or more barriers/latches help control checkpoints **without needing `sleep`**.

### About Benchmarking

`AtomicStampedReference` may incur overhead for managing version pairs, contention, and allocation depending on the implementation. Do not claim it is faster or slower than standard CAS without measuring the actual workload and JDK. Benchmarks must compare versions that are **both logically correct**; an algorithm that omits stamps might be "faster" yet broken under critical ABA schedules.

If measuring contention and latency, consider JMH for Java microbenchmarks. Avoid single-run benchmarks using `System.nanoTime()` and treating small differences as definitive conclusions.

## 20. When Should You Use (and Not Use) AtomicStampedReference?

**Consider using it when:**

- The logic requires detecting **that a transition occurred since the snapshot**, even if the current reference returns to the original object.
- You have an optimistic CAS design with a reference that can be **reused**.
- There is a clear stamp policy with no reuse within the lifetime of relevant observers.
- You want to keep `reference + version` as an atomic pair without placing a lock around that update.
- You can verify that all read/write paths go through the atomic container without improper referent mutation.

**Do not use it by default when:**

- You only need `counter++` or a single independent value update: `AtomicInteger`/`AtomicLong` is more suitable.
- You need to protect invariants across multiple mutable fields that cannot be packed into an immutable snapshot: `synchronized`/`ReentrantLock` is usually clearer.
- Data is already designed as immutable and each transition creates **a new unique state instance**; `AtomicReference<ImmutableState>` may be enough.
- Proven collection primitives exist such as `ConcurrentLinkedQueue`, `ConcurrentHashMap`, or `BlockingQueue`: prefer battle-tested primitives over implementing custom lock-free structures.
- You need "never-colliding versions" over an extremely long lifetime where `int` is insufficient; choose a different version domain/architecture.
- You want to solve serialization across databases/processes: Java atomics only protect state within the appropriate JVM and do not become distributed transactions.

## 21. Self-Check Questions and Answers

**Q1.** T1 reads reference A. T2 performs CAS A→B→A and T1 proceeds with CAS A→C. Why can standard CAS return `true`?  
**Answer:** Standard CAS only compares the current reference with expected A. Once `current` has returned to the exact same object A, it has no information that B existed in between.

**Q2.** Is merely detecting A→B→A enough to conclude there is a bug?  
**Answer:** No. ABA only causes a bug if T1 relies on the assumption that the state/structure has not changed since the snapshot and that assumption is a correctness requirement.

**Q3.** Why does `AtomicStampedReference` prevent the example with `(A,0)→(B,1)→(A,2)`?  
**Answer:** T1 expects both reference A **and** stamp 0; the current stamp is 2, so the stale CAS fails.

**Q4.** Does `AtomicStampedReference` automatically increment the stamp when calling `compareAndSet`?  
**Answer:** No. The caller passes `newStamp`. You must enforce that every meaningful mutation path updates the version.

**Q5.** Does calling `getReference()` followed by `getStamp()` guarantee the same snapshot?  
**Answer:** No; another thread can update between the two calls. Use `get(int[] stampHolder)`.

**Q6.** Two instances `new String("A")` are `equals` to each other; does reference CAS treat them as the same expected value?  
**Answer:** No. Reference CAS uses identity `==`, not `equals()`.

**Q7.** A referent `Payload` has `payload.value` modified, but the reference and stamp do not change. Does stamped CAS automatically detect this?  
**Answer:** No. It only checks the reference/stamp pair. Mutable fields must be protected by state design, ownership, or another lock.

**Q8.** Why might an `int stamp` be insufficient in a long-running system?  
**Answer:** It has a finite number of values and can overflow/wrap, or be intentionally reset by code, allowing an old pair to reappear.

**Q9.** Is the stale `next` bug in a lock-free stack completely solved just by using `AtomicStampedReference`?  
**Answer:** You cannot claim that. A stamp helps prevent CAS based on an old `head` version, but you still need to verify the entire algorithm, node reuse, and memory reclamation/lifecycle.

**Q10.** Can you invoke side effects inside a CAS retry loop?  
**Answer:** You should not for non-idempotent side effects. CAS can fail multiple times so the effect may execute repeatedly, and CAS does not form a transaction with external systems.

**Q11.** If a CAS with a stale stamp fails, is it correct to fix it by fetching the latest stamp and immediately doing CAS with `desired` computed from the old snapshot?  
**Answer:** Not necessarily. You must re-read **both reference and stamp**, check the invariant, and **recompute `desired`** from the new snapshot before retrying.

**Q12.** Do `AtomicMarkableReference` and `AtomicStampedReference` serve the same purpose?  
**Answer:** No. Markable uses a boolean mark, suitable for logical marking; stamped uses an `int` version, useful for distinguishing generations of changes.

## 22. References

- [Java SE 17 — AtomicStampedReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicStampedReference.html): constructor, `get(int[])`, `compareAndSet`, `set`, `attemptStamp`.
- [Java SE 17 — AtomicReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): `get`, `set`, `compareAndSet`.
- [Java SE 17 — AtomicMarkableReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicMarkableReference.html): reference combined with a boolean mark.
- [Java SE 17 — java.util.concurrent.atomic](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/package-summary.html): introduction to atomic classes and memory effects.
- [Java Language Specification Java SE 17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): data race, happens-before, and memory ordering.
- [Java SE 17 — Thread](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `start`, `join`, and completion relationships.

**Final Summary:** **ABA = current returns to A after changing in between**. Standard CAS checks current identity, so it can allow a stale update to succeed. `AtomicStampedReference` adds a **generation/stamp** so CAS checks a **(reference, version) pair**. It is effective when **every significant mutation increments the version, versions are not reused while observers exist, the referent is managed safely, and the algorithm is proven end-to-end**.
