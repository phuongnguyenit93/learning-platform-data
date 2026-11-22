# Immutable Strings Do Not Make Every Variable or Container Holding Them Thread-Safe

## 1. The Problem to Understand

In Java, `String` is **immutable**: once a `String` object is created, the content of that object itself cannot be changed through its public API. Multiple threads can concurrently read a properly shared `String` object without corrupting the string's content.

However, **an immutable `String` does not mean every variable referencing a `String`, every operation on that variable, or every structure storing `String`s is thread-safe**.

For example:

```java
String name = "Java";
name = name + " 17";
```

The expression above creates a new string value and **reassigns the variable `name`**; it does not edit the `"Java"` object. If multiple threads concurrently read and reassign **one shared variable**, race conditions, lost updates, and visibility issues still exist.

Lesson goals:
- Distinguish **an immutable object**, **a reassignable reference variable**, and **a mutable container holding strings**.
- Explain why `shared = shared + text` is not an atomic update.
- Understand the roles of `volatile`, `synchronized`, and `AtomicReference<String>` under the Java Memory Model.
- Choose the appropriate solution when sharing string state across threads.

## 2. A `String` Object and a Reference Variable Are Two Different Things

Consider:

```java
String a = "hello";
String b = a;
a = a.toUpperCase();

System.out.println(a); // HELLO
System.out.println(b); // hello
```

`a` and `b` initially point to the same `"hello"` content. `toUpperCase()` returns a new `String` value in this example, and then `a` is reassigned; `b` still points to the original string.

Separate three levels:

| Component | Immutable? | What can happen under multithreading? |
| --- | --- | --- |
| A **`String` object** | Yes; content does not change. | Threads reading concurrently do not contend over content-mutation operations. |
| A **shared `String` variable/field**, e.g. `current` | Not necessarily; the reference can be reassigned. | Concurrent reads/writes can lack visibility guarantees and suffer lost updates. |
| A **container** such as `ArrayList<String>`, `HashMap<String,String>`, or `StringBuilder` | Usually mutable. | Container mutations can race or violate thread-safety contracts. |

A variable `final String greeting = "hello";` prevents **reassigning that variable** after initialization, but `final` does not automatically turn a structure holding the variable into an immutable object, nor does it make all other fields of the containing object thread-safe.

## 3. Why Can Appending to a Shared Variable Lose Updates?

Consider shared state:

```java
class State {
    String text = "X";
}
```

If two threads execute concurrently:

```java
state.text = state.text + "A"; // Thread 1
state.text = state.text + "B"; // Thread 2
```

A `+=` or compound assignment like this has to perform multiple steps:

1. **Read** the current reference from `state.text`.
2. **Compute** a new `String` value by appending the suffix.
3. **Write** the new `String` reference back to `state.text`.

In one execution schedule, the following can occur:

| Step | Thread 1 | Thread 2 | Value in `state.text` |
| --- | --- | --- | --- |
| Initial | — | — | `"X"` |
| 1 | Reads `"X"` | — | `"X"` |
| 2 | — | Reads `"X"` | `"X"` |
| 3 | Creates and assigns `"XA"` | — | `"XA"` |
| 4 | — | Creates and assigns `"XB"` from stale read | `"XB"` |

The final result in the schedule above is `"XB"`: Thread 1's update **was overwritten**. If the write order reverses, the result can be `"XA"`. No `String` object was modified or corrupted; the bug lies in **the process of updating the shared reference**.

There is a **data race** here when threads access a field without synchronization and at least one access is a write. You must not rely on "running it a few times worked" to conclude a program is safe: the compiler, JVM, and processor are permitted to optimize within the Java Memory Model when required *happens-before* relationships are missing.

## 4. Java 17+: Standalone Runnable Example with Deterministic Results

The example intentionally forces both threads to read the old value before writing, so the lost-update bug reproduces clearly instead of depending on scheduling luck.

Save as `ImmutableStringConcurrencyDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class ImmutableStringConcurrencyDemo {
    static final class Holder {
        String value = "X";
    }

    static void appendUnsafely(
            Holder shared, CountDownLatch bothRead, String suffix) {
        // Both threads read "X" before any write.
        String snapshot = shared.value;
        bothRead.countDown();

        try {
            bothRead.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return;
        }

        // Overwrite with a value derived from each thread's own snapshot.
        shared.value = snapshot + suffix;
    }

    public static void main(String[] args) throws InterruptedException {
        String original = "Hi";
        String updated = original.concat("!");
        System.out.println("original = " + original);
        System.out.println("updated = " + updated);

        Holder unsafe = new Holder();
        CountDownLatch bothRead = new CountDownLatch(2);

        Thread first = new Thread(
                () -> appendUnsafely(unsafe, bothRead, "A"));
        Thread second = new Thread(
                () -> appendUnsafely(unsafe, bothRead, "B"));

        first.start();
        second.start();
        first.join();
        second.join();

        // Value is "XA" or "XB", not containing both updates.
        System.out.println("unsafe length = " + unsafe.value.length());

        AtomicReference<String> safe = new AtomicReference<>("X");
        Thread third = new Thread(
                () -> safe.updateAndGet(s -> s + "A"));
        Thread fourth = new Thread(
                () -> safe.updateAndGet(s -> s + "B"));

        third.start();
        fourth.start();
        third.join();
        fourth.join();

        String result = safe.get();
        // "XAB" or "XBA", always preserving both updates.
        System.out.println("atomic length = " + result.length());
        System.out.println("contains A = " + result.contains("A"));
        System.out.println("contains B = " + result.contains("B"));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 ImmutableStringConcurrencyDemo.java
java ImmutableStringConcurrencyDemo
```

Output (independent of update order between threads, unless abnormally interrupted):

```text
original = Hi
updated = Hi!
unsafe length = 2
atomic length = 3
contains A = true
contains B = true
```

**Explanation of output:**
- Calling `concat("!")` creates `"Hi!"`, while `original` continues to be `"Hi"`.
- `CountDownLatch(2)` ensures both threads have read `"X"` before either thread proceeds to assignment. Because each thread appends only one suffix to the same snapshot, the final value of `unsafe.value` has length **2**, despite two "appends."
- `AtomicReference.updateAndGet` performs an atomic update according to the transformation function. If two threads contend, one thread may have to retry against the value just updated by the other thread. Thus the final string has length **3** and contains both `A` and `B`, though the order `XAB` / `XBA` is non-deterministic.
- `Thread.join()` lets the `main` thread wait for the tasks to finish and see their results. `join()` does **not** make shared-variable updates inside the threads atomic on their own.
- The function passed to `updateAndGet` is `s -> s + suffix`, which has no side effects. The update function may be invoked multiple times under contention; never place operations like sending emails, writing files, or mutating other system state inside this lambda.

This is an example demonstrating **lost update**, not a recommendation to use unsynchronized shared variables in real applications.

## 5. `volatile` Solves Visibility, Not Lost Updates on Its Own

Declaration:

```java
class Status {
    volatile String message = "starting";
}
```

With `volatile`, writes to `message` and corresponding reads of `message` have visibility and ordering guarantees under the Java Memory Model. Threads reading the `volatile` field will not hold onto stale cached/hoisted values in ways that violate those rules. Reading/writing **a single reference** is an atomic operation even without `volatile`; what `volatile` adds is visibility and ordering guarantees.

If only one thread updates a status message while other threads read it, a `volatile String` pattern can be appropriate:

```java
final class Status {
    private volatile String message = "pending";

    void publish(String next) {
        message = next;
    }

    String current() {
        return message;
    }
}
```

However:

```java
volatile String text = "X"; // Example of a field in a class

void append(String suffix) {
    text = text + suffix;
}
```

**Updates can still be lost.** `volatile` gives individual reads/writes visibility, but does not combine **read → concatenate → write** into one atomic transaction. Two threads can still read the same old value and overwrite each other in turn.

Remember: **immutability** is about the state **of an object**; **`volatile`** is about visibility/ordering when accessing **a field**; **atomicity** is about the non-interleaving of **an entire update operation**. Those three properties are distinct.

## 6. Solutions When Shared Strings Must Be Updated

### 6.1. Synchronizing with `synchronized`

When an append operation must preserve every update, you can enclose the entire read–compute–write section under the same lock:

```java
final class SynchronizedText {
    private String value = "";

    public synchronized void append(String part) {
        value = value + part;
    }

    public synchronized String get() {
        return value;
    }
}
```

Two threads calling `append("A")` and `append("B")` on **the same instance** will not interleave their synchronized method bodies; the final string contains both parts. `synchronized` methods on the same object share the same monitor and provide a *happens-before* relationship for reads/writes protected by that monitor.

If multiple fields must change consistently within one operation, `synchronized` or an appropriate lock is usually easier to keep all invariants intact than updating each field independently.

### 6.2. `AtomicReference<String>`

When you need to atomically update **one string reference** without an external lock around the whole operation:

```java
import java.util.concurrent.atomic.AtomicReference;

final class AtomicText {
    private final AtomicReference<String> value =
            new AtomicReference<>("");

    void append(String part) {
        value.updateAndGet(old -> old + part);
    }

    String get() {
        return value.get();
    }
}
```

`AtomicReference` uses atomic operations such as compare-and-set. Each successful `updateAndGet` is computed on a value consistent with the atomic update order; under contention, the lambda may re-run. Therefore **the lambda should be pure and side-effect-free**, and `part` should remain stable for the duration of the call.

If multiple references must be updated together under a shared invariant, one `AtomicReference` per field is **not enough** to make the group of updates atomic. You can use a lock or group the state into an immutable value object and swap the entire object through one `AtomicReference<State>`.

### 6.3. Avoid Sharing Writable State

In many applications, the simplest solution is for each thread to work on its own local variables:

```java
String makeMessage(String name) {
    String result = "Hello, ";
    result = result + name;
    return result;
}
```

`result` is a local variable per call; unless placed into shared state, threads do not contend when reassigning `result`. Using immutable `String`s prevents sneaky edits to the content of a string passed into another method.

Do not synchronize every string read just because a program is multithreaded. Synchronization belongs specifically where **shared mutable state** is read and written.

## 7. Containers Holding `String`s Do Not Automatically Become Thread-Safe

A collection of immutable elements can still be a **mutable collection object**:

```java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>();
names.add("An");
names.add("Bình");
```

Each `String` element is immutable, yet the internal structure of `ArrayList` (size, backing array, modification/iteration) is not designed for unsynchronized concurrent edits. If multiple threads mutate `names` concurrently, element immutability does not protect the list structure.

Similar situations:

| Structure | Property to remember | When shared across threads |
| --- | --- | --- |
| `ArrayList<String>` | Mutable list; mutating operations are not thread-safe by default. | Use locks for shared access/mutation, or choose a concurrent collection if suitable. |
| `HashMap<String, String>` | Immutable keys/values do not protect the mutable hash table. | Do not mutate concurrently without synchronization; use `ConcurrentHashMap` for concurrent access/updates. |
| `ConcurrentHashMap<String, String>` | Supports concurrent operations guaranteed by its API docs. | Use `compute` / `merge` when updating a key based on its old value. |
| `StringBuilder` | Mutable character buffer, **not** synchronized. | Keep per-thread or lock around all shared operations. |
| `StringBuffer` | Many methods have internal synchronization. | A sequence of multiple calls may still need extra synchronization if it must be business-atomic. |
| `List.of("A", "B")` / `List.copyOf(...)` | Collection that forbids structural edits through the collection API. | Can be shared for reading after proper publication; for mutable elements, this is not deep immutability. |

Wrong example, because `get` and `put` are two separate steps:

```java
// map is ConcurrentHashMap<String, String>, key "log" already exists.
String old = map.get("log");
map.put("log", old + "A"); // May overwrite another thread's update.
```

How to keep updating **one key** in an appropriate atomic operation:

```java
map.compute("log", (key, old) ->
        (old == null ? "" : old) + "A");
```

`ConcurrentHashMap.compute` synchronizes the key's update logic per the API contract; keep the remapping function short, free of side effects, and avoid recursive operations on the same map. Just like `AtomicReference`, the safety of collection operations is determined by **the collection's contract and usage**, not merely by `String` values being immutable.

### Wrappers and Surface Immutability

`Collections.unmodifiableList(mutableList)` is a **view that disallows modification through the wrapper**, while the underlying list can still be mutated elsewhere. The wrapper does not automatically provide synchronization or a snapshot. By contrast, `List.copyOf(source)` creates a list that cannot be structurally modified via its API and does not reflect additions/removals on the source list; it does not deep-copy mutable elements.

Therefore "a list of immutable `String`s" and "an immutable list" are two different claims.

## 8. Publishing References and the Java Memory Model

A reference to a `String` may be read across multiple threads. You cannot deduce from string immutability that **every reference publication or replacement** has a *happens-before* relationship.

For example:

```java
class MessageBox {
    String latest = "initial";

    void set(String text) {
        latest = text;
    }

    String get() {
        return latest;
    }
}
```

If one thread calls `set` while another calls `get` without further synchronization, there is no strong enough guarantee that the reading thread will observe **the latest value** at the expected time. The content of the `String` object itself remains immutable, yet the protocol for exchanging updates through the `latest` field is missing.

Common ways to establish synchronization/happens-before relationships:
- Use `volatile` when publishing/replacing **a single reference** without read–modify–write composition.
- Use `synchronized`/`Lock` when reading and writing a group of states under a shared invariant.
- Use `AtomicReference` for atomic reference swaps or read–modify–write updates.
- Use properly contracted concurrent collections/queues or message passing when threads must exchange data.

A `final` field properly initialized in a constructor provides special initialization guarantees under the Java Memory Model (assuming `this` does not escape during construction). Still, an object with a `final String` field can contain other mutable fields and is **not inherently thread-safe**.

## 9. Choosing a Design by Requirement

| Requirement | Implementation direction |
| --- | --- |
| Multiple threads only read one properly published `String` | Share the string directly; no lock needed to protect immutable content. |
| One thread replaces a message, many threads read the latest message | `volatile String` or `AtomicReference<String>`, depending on API needs. |
| Multiple threads concurrently "append" to one string variable | `synchronized` or `AtomicReference.updateAndGet`; avoid unsynchronized `+=`. |
| Updating multiple fields that must stay consistent with each other | A shared lock or an immutable state object swapped atomically. |
| Multiple threads operating on a map containing `String`s | `ConcurrentHashMap` with appropriate update APIs; `get` then `put` may not suffice. |
| Long string concatenation, each thread with its own buffer | Local `StringBuilder`; produce a `String` when ready to share results. |
| Need a read-only list | Use an appropriate immutable copy and publish it properly; distinguish snapshots from unmodifiable views. |

**Performance note:** repeatedly updating a string via `old + suffix` can create many intermediate strings due to `String` immutability. For heavy concatenation, if threads build data independently, it is usually better to use a local `StringBuilder` and combine results via an appropriate synchronization mechanism. Do not share one mutable `StringBuilder` without synchronization just to avoid allocating objects.

## 10. Easily Confused Claims

1. **"`String` is immutable, so `shared += "x"` is thread-safe."** False: the statement updates a shared variable across multiple steps.
2. **"Adding `volatile` makes every update safe."** False: visibility alone does not guarantee atomic read–modify–write.
3. **"`List<String>` is always thread-safe because its elements are strings."** False: a mutable container has its own state and synchronization rules.
4. **"`ConcurrentHashMap` makes any sequence of `get` then `put` atomic."** False: use `compute`/`merge` when you want an atomic per-key update.
5. **"Using `synchronized` when reading a string is mandatory."** False: reading a properly published immutable string object needs no separate lock to protect its content; however, the surrounding state-exchange protocol may require locking.
6. **"Having a `final String` makes the whole object thread-safe."** False: other fields can still be mutable, and consistency across fields needs separate design.

## 11. Applied Exercises

**Exercise 1.** Given a shared field:

```java
volatile String log = "";

void add(String item) {
    log = log + item;
}
```

Two threads call `add("A")` and `add("B")`. Is `log` guaranteed to contain both parts?

**Answer:** No. Each thread can read the same old snapshot before assigning; `volatile` does not provide atomicity for the entire concatenation. You can replace it with `AtomicReference<String>.updateAndGet` or synchronize the entire operation.

**Exercise 2.** A service publishes a new status string without needing to append to the old status; one thread writes, many threads read. Is `AtomicReference.updateAndGet` required?

**Answer:** Not necessarily. A `volatile String status` field with simple reads/writes fits many independent status-publication cases. If conditional transitions based on the old value must be guaranteed, consider atomic/locking mechanisms.

**Exercise 3.** A `HashMap<String,String>` has `String` keys and values. Can multiple threads mutate the map while iterating directly without synchronization?

**Answer:** No. Immutable strings do not protect the `HashMap` structure during concurrent modification. Choose `ConcurrentHashMap` or external synchronization depending on the operation's consistency needs.

**Exercise 4.** When needing to read a created string shared through a thread-safe queue, do you have to lock separately around `charAt` and `length` on that string?

**Answer:** No separate lock is needed to protect the immutable content of `String`. Passing the string through a queue with an appropriate concurrent contract provides the publication/handoff mechanism; any other mutable state must be evaluated separately.

## References

- [Java SE 17: `String`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Java SE 17: `AtomicReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html)
- [Java SE 17: `ConcurrentHashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
- [Java Language Specification §17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html)
