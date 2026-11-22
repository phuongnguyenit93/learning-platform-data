# Hard-to-control shared state: recognizing, isolating, and protecting it in Java OOP

> **Topic:** OOP → Design Pitfalls → Hard-to-control shared state.  
> **Objective:** Understand *shared mutable state* and why it makes objects unpredictable; distinguish sharing data from sharing mutation rights; identify reference leaks, mutable `static` fields, stateful singletons, and race conditions; and choose appropriately scoped encapsulation, immutable snapshots, stateless services, synchronization, or transactions.

## 1. The real issue: one state with multiple writers

Suppose a ticketing system has **1 seat remaining**. Two booking requests arrive nearly simultaneously:

1. Request A reads: 1 seat remains.
2. Request B also reads: 1 seat remains.
3. A decides the booking succeeds.
4. B also decides the booking succeeds.

The system may report **two successful bookings for the same seat**, even if `reserved` eventually holds only `1`. This is more than a bad increment: business decisions relied on **shared state without controlling read–modify–write operations**.

Another example needs no threads: a `Team` stores the `List<Member>` provided by its caller. The caller later invokes `members.clear()`, changing the `Team` membership **without any domain method on `Team`**. This is also shared mutable state, caused by **aliasing** (multiple references to the same mutable object).

**Shared mutable state** is state that can change and is accessible to multiple parties: objects, modules, requests, threads, or processes reading/writing shared storage. Sharing itself **is not always bad**. The design smell appears when **ownership, mutation authority, atomic operations, and required invariants are unclear**.

### Four situations to distinguish

| Data | Shared? | Mutable? | Main risk |
|---|---|---|---|
| Constant `static final String APP_NAME` | Yes | No, when the value is immutable | Low |
| `List.copyOf(...)` containing `String` | Possibly | Not via the list API; `String` elements are immutable | Low if sharing is authorized |
| One `ArrayList` referenced by many classes | Yes | Yes | Unexpected edits and violated invariants |
| `int remaining` shared among threads | Yes | Yes | Lost updates, stale reads, check-then-act |
| Database inventory shared by applications | Yes | Yes | Conflicting writes, overselling, inconsistent transactions |

**Two key questions:** *Through which paths can the state change?* And *does every change follow the same contract?*

## 2. Why is this dangerous in OOP?

OOP lets several objects reference the same object:

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> shared = new ArrayList<>(List.of("READ"));

List<String> referenceA = shared;
List<String> referenceB = shared;

referenceA.add("WRITE");
System.out.println(referenceB); // [READ, WRITE]
~~~

`referenceA` and `referenceB` are **two variables pointing to one instance**, not separate lists. This remote effect needs neither `static` nor multithreading.

When a class publishes an internal mutable reference, clients gain the ability to change state:

~~~java
final class UnsafeGroup {
    private final List<String> members;

    UnsafeGroup(List<String> members) {
        this.members = members; // Giữ alias từ bên ngoài.
    }

    List<String> members() {
        return members; // Lại đưa alias ra ngoài.
    }
}
~~~

These statements mutate the object outside its control:

~~~java
List<String> external = new ArrayList<>(List.of("Lan"));
UnsafeGroup group = new UnsafeGroup(external);

external.clear();           // Thay đổi từ đầu vào đã truyền.
group.members().add("Nam"); // Thay đổi qua getter.
~~~

Even if `members` is `private final`, **the List contents remain mutable**. `final` prevents reassignment of the field reference, not mutation of the referenced object.

### Common consequences

- **Broken invariants:** `reserved > capacity`, negative balances, or collections missing required data.
- **Call-order-dependent behavior:** results change when a method happens to run earlier.
- **Hard-to-reproduce bugs:** races occur only under certain schedules or load levels.
- **Interfering tests:** singleton/static state persists across test cases.
- **Leaks between requests or users:** a service field stores request A's data, then request B overwrites it.
- **Difficult root-cause analysis:** too many writers can produce invalid state.
- **Difficult scaling across nodes:** a JVM-local lock cannot protect shared database records.

Increasing unit-test counts alone does not solve a design that still permits arbitrary state mutations.

## 3. State ownership and mutation boundaries

An object or module should have **a clear state owner**. Callers request domain operations; the owner decides whether changes are valid:

~~~mermaid
flowchart LR
    C1["Client A"] -->|"reserve(1)"| Owner["SeatInventory: chủ sở hữu"]
    C2["Client B"] -->|"reserve(1)"| Owner
    Owner --> Rule{"capacity còn đủ?"}
    Rule -->|Có| Commit["Cập nhật có kiểm soát"]
    Rule -->|Không| Reject["Từ chối, không đổi state"]
    Owner --> Snapshot["Snapshot chỉ đọc"]
    Snapshot --> C1
    Snapshot --> C2
~~~

Do not interpret "one place controls mutation" as forbidding other classes from **using** state. Clients may still need read access, but through **immutable snapshots**, well-defined getters, or appropriate query methods.

A good design for important state usually has:

1. **Private representation:** clients cannot directly assign internal fields.
2. **Domain operations:** `reserve(1)` instead of `setReserved(7)`.
3. **Clear contracts and invariants:** for example, `0 ≤ reserved ≤ capacity`.
4. **Atomicity at the correct scope:** checks and updates must be coordinated under concurrency.
5. **No mutable alias leaks:** guard constructor input, getters, and nested elements.
6. **Failure-path tests:** invalid operations must not leave partially updated state.

## 4. Reproducible standalone Java 17 race-condition example

Instead of relying on scheduler timing, the example uses `CountDownLatch` to **deliberately make two threads read the same state before either writes**. This reveals the *lost update* bug consistently.

### 4.1. An intentionally incorrect implementation

One seat remains and two customers try to book it. In the flawed design, both threads read `reserved = 0` and then write `observed + 1`:

~~~java
import java.util.concurrent.CountDownLatch;

final class UnsafeSeatGate {
    private final int capacity = 1;
    private int reserved;

    private final CountDownLatch bothRead = new CountDownLatch(2);
    private final CountDownLatch mayWrite = new CountDownLatch(1);

    boolean reserveOne() throws InterruptedException {
        int observed = reserved;

        if (observed >= capacity) {
            return false;
        }

        // Cố ý buộc cả hai request qua bước kiểm tra trước khi ghi.
        bothRead.countDown();
        mayWrite.await();

        reserved = observed + 1; // Ghi từ snapshot cũ.
        return true;
    }

    void letBothWrite() throws InterruptedException {
        bothRead.await();
        mayWrite.countDown();
    }

    int reserved() {
        return reserved;
    }
}
~~~

This class **demonstrates a bug** and must not be used in production. `CountDownLatch` does not create the bug; it reproduces a dangerous execution schedule.

### 4.2. A class that preserves its invariant

A correct solution makes "check then update" **one operation that another thread cannot interleave**:

~~~java
record SeatSnapshot(int capacity, int reserved) {
    SeatSnapshot {
        if (capacity <= 0 || reserved < 0 || reserved > capacity) {
            throw new IllegalArgumentException("Invalid snapshot");
        }
    }

    int available() {
        return capacity - reserved;
    }
}

final class SeatInventory {
    private final int capacity;
    private int reserved;

    SeatInventory(int capacity) {
        if (capacity <= 0) {
            throw new IllegalArgumentException("capacity must be > 0");
        }
        this.capacity = capacity;
    }

    // Cả phần kiểm tra và cập nhật đều nằm trong cùng monitor.
    synchronized boolean reserveOne() {
        if (reserved >= capacity) {
            return false;
        }
        reserved++;
        return true;
    }

    synchronized SeatSnapshot snapshot() {
        return new SeatSnapshot(capacity, reserved);
    }
}
~~~

Here `SeatInventory` keeps `reserved` `private`, exposes no setter, and returns an **immutable `SeatSnapshot`**. Using `synchronized` on both `reserveOne()` and `snapshot()` makes reads/writes consistent through that instance's monitor.

### 4.3. Complete runnable program

Combine **all three snippets below** in **one `SharedStateDemo.java` file** in order: imports; the two classes `UnsafeSeatGate`/`SeatInventory` with `SeatSnapshot` shown above; then the `SharedStateDemo` class below. Each Java file has only one `public` class matching its filename:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SharedStateDemo {
    public static void main(String[] args) throws Exception {
        var unsafe = new UnsafeSeatGate();
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Future<Boolean> a = pool.submit(unsafe::reserveOne);
            Future<Boolean> b = pool.submit(unsafe::reserveOne);

            // Chỉ nhả barrier sau khi cả hai đã đọc reserved = 0.
            unsafe.letBothWrite();

            int accepted = (a.get() ? 1 : 0) + (b.get() ? 1 : 0);

            System.out.println("Unsafe accepted = " + accepted);
            System.out.println("Unsafe reserved = " + unsafe.reserved());

            var safe = new SeatInventory(1);
            Future<Boolean> c = pool.submit(safe::reserveOne);
            Future<Boolean> d = pool.submit(safe::reserveOne);

            int safeAccepted = (c.get() ? 1 : 0) + (d.get() ? 1 : 0);
            System.out.println("Safe accepted = " + safeAccepted);
            System.out.println("Safe reserved = " + safe.snapshot().reserved());
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

**When creating the actual file**, put all `import` statements **at the top** (not between classes). Because the snippets are separated conceptually, gather `import java.util.concurrent.CountDownLatch;` and the three imports in `SharedStateDemo` at the beginning:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
~~~

Then declare `UnsafeSeatGate`, `SeatSnapshot`, `SeatInventory`, and `public class SharedStateDemo`, **without repeating imports between classes**.

Compile and run:

~~~bash
javac SharedStateDemo.java
java SharedStateDemo
~~~

Intentional output:

~~~text
Unsafe accepted = 2
Unsafe reserved = 1
Safe accepted = 1
Safe reserved = 1
~~~

**Key observation:** the incorrect result **does not have to be `reserved > capacity`**. Here `reserved` is still `1`, but both requests report **success**. Recorded state no longer agrees with the announced business decisions: a *lost update*.

In the correct version, only one thread at a time can execute `reserveOne()` on **the same `SeatInventory` instance**, so the second sees `reserved = 1` and is rejected. `SeatSnapshot` captures the `capacity/reserved` pair from one instant under the lock.

## 5. How do `volatile`, `synchronized`, and atomics differ?

A dangerous misconception is that "adding `volatile` to an `int` makes `count++` safe."

~~~java
class WrongCounter {
    private volatile int count;

    void increment() {
        count++; // Đọc -> cộng -> ghi: KHÔNG nguyên tử.
    }

    int get() {
        return count;
    }
}
~~~

In Java, `volatile` provides **visibility and ordering guarantees** for designated variables under the Java Memory Model. It does not make a **read–modify–write** sequence atomic. Two threads can still read one old value and overwrite each other's results.

Comparison:

| Tool | Main guarantee | Suitable for | Insufficient for |
|---|---|---|---|
| `private` | Restricts state access at language level | Encapsulation | Automatic thread safety |
| `final` | Prevents field reassignment; special JMM final-field publication semantics | Stable state design | Making mutable objects immutable |
| `volatile` | Visibility/ordering for one variable; volatile accesses follow JMM rules | Stop flags, simple state | `count++` and multi-step check-then-act |
| `synchronized` | Mutual exclusion and happens-before through one monitor | Related state and invariants | Multiple JVMs/DBs/distributed systems |
| `AtomicInteger` | Atomic operations such as `incrementAndGet` and `compareAndSet` on **one** value | Counters, single-value state, CAS | Enforcing cross-object/record invariants automatically |
| `ReentrantLock` | Explicit locking, `tryLock`, wait conditions | Workflows needing advanced lock capabilities | Any invariant whose access paths bypass the same lock |
| DB transaction/constraint | Controls stored-data consistency per DB/isolation | Concurrent updates across requests/nodes | Guaranteeing all side effects in external systems |

### AtomicInteger: good for counters, insufficient for every constraint

~~~java
import java.util.concurrent.atomic.AtomicInteger;

final class RequestCounter {
    private final AtomicInteger count = new AtomicInteger();

    int markRequest() {
        return count.incrementAndGet();
    }

    int current() {
        return count.get();
    }
}
~~~

This simple counter supports atomic increments without a separate lock. But if the rule is "reserved seats must not exceed capacity," the following approach:

~~~java
// KHÔNG AN TOÀN: check và increment là hai thao tác tách rời.
if (reserved.get() < capacity) {
    reserved.incrementAndGet();
}
~~~

still contains a race. A **CAS loop** can combine checking and updating through compare-and-set:

~~~java
final class AtomicSeatInventory {
    private final int capacity;
    private final java.util.concurrent.atomic.AtomicInteger reserved =
            new java.util.concurrent.atomic.AtomicInteger();

    AtomicSeatInventory(int capacity) {
        if (capacity <= 0) {
            throw new IllegalArgumentException("capacity must be > 0");
        }
        this.capacity = capacity;
    }

    boolean reserveOne() {
        while (true) {
            int current = reserved.get();
            if (current >= capacity) {
                return false;
            }
            if (reserved.compareAndSet(current, current + 1)) {
                return true;
            }
            // Thread khác vừa ghi; đọc lại trạng thái mới và thử lại.
        }
    }

    int reserved() {
        return reserved.get();
    }
}
~~~

The code protects a simple constraint on **one `reserved` value** with immutable `capacity`. If `reserved`, `revenue`, and booking history must be updated together, three AtomicInteger instances do not magically form one atomic transaction. Identify the real **unit of consistency**, which may span several fields/objects.

## 6. Aliasing is shared mutable state even with only one thread

Two variables may reference **the same collection**, allowing one party to modify data without invoking the other object's domain methods. This lesson focuses on *shared-state ownership*; detailed constructor/getter leaks and defensive copying are covered under *Exposed state and broken invariants*.

Consider a group permission set supplied by a caller:

~~~java
// Sai: nhóm giữ cùng List mà caller còn được sửa.
List<String> external = new ArrayList<>(List.of("READ"));

final class PermissionGroup {
    private final List<String> permissions;

    PermissionGroup(List<String> input) {
        this.permissions = input;
    }

    boolean has(String permission) {
        return permissions.contains(permission);
    }
}

PermissionGroup unsafe = new PermissionGroup(external);
external.add("ADMIN");
System.out.println(unsafe.has("ADMIN")); // true ngoài ý muốn
~~~

No race condition is needed here: **an alias exposes a mutation path beyond the owner**. Fix the design by taking an unmodifiable snapshot at input:

~~~java
final class SafePermissionGroup {
    private final java.util.List<String> permissions;

    SafePermissionGroup(java.util.List<String> input) {
        java.util.Objects.requireNonNull(input, "input");
        this.permissions = java.util.List.copyOf(input);
    }

    boolean has(String permission) {
        return permissions.contains(permission);
    }

    java.util.List<String> snapshot() {
        return permissions;
    }
}
~~~

`List.copyOf` protects **List structure** from callers and stops mutations through `snapshot()`; because its elements are immutable `String` values, this is enough for the demo. With mutable elements, this remains a shallow snapshot and element ownership must be examined. Sharing immutable objects or safe snapshots is not itself a flaw: control **who can mutate the shared data**.

## 7. `static` and Singleton: wider sharing than intended

In Java, a `static` field belongs to **its class in a class-loader scope**, rather than to any instance. If mutable, it can be seen and modified by many objects using that class:

~~~java
final class GlobalFlags {
    static boolean maintenanceMode = false;
}

// Một phần chương trình:
GlobalFlags.maintenanceMode = true;
// Phần khác đọc cùng biến trong cùng class-loader context.
~~~

In multithreaded applications, the example's field also lacks visibility guarantees for unsynchronized reads/writes. If it is simply a flag needing cross-thread visibility, consider `volatile` or `AtomicBoolean`, while also defining mutation rights and lifetime. For immutable shared configuration, `static final` is often simpler.

**`static` does not mean "one copy throughout the cluster."** Separate JVMs, class loaders, and processes have distinct state.

### A singleton is not automatically thread-safe

A singleton defines instance management within a scope; it **does not synchronize internal fields**.

~~~java
final class SessionTracker {
    // Một singleton toàn chương trình (minh họa ý tưởng).
    static final SessionTracker INSTANCE = new SessionTracker();

    private String lastUserId;

    private SessionTracker() {}

    void record(String userId) {
        lastUserId = userId;
    }

    String lastUserId() {
        return lastUserId;
    }
}
~~~

If concurrent requests call `record`, `lastUserId` is overwritten repeatedly and belongs to no particular request. `volatile` can improve visibility but cannot make the data belong to "the right user"; **the fundamental flaw is state ownership**.

Instead of keeping request information in a mutable singleton, pass `userId` as an argument or use properly scoped **request state**.

## 8. Spring singleton services and cross-request state leakage

In Spring, `@Service` beans generally have **singleton scope by default within one application context**. Different HTTP requests may execute on **the same instance** from separate threads.

Problematic example:

~~~java
// Ví dụ minh họa cho ứng dụng Spring, không thuộc JDK trần.
@org.springframework.stereotype.Service
class UnsafeCheckoutService {
    private String currentOrderId; // Request state nằm trên singleton!

    String prepare(String orderId) {
        currentOrderId = orderId;

        // Giữa các bước này request khác có thể ghi field.
        return "Processing " + currentOrderId;
    }
}
~~~

Requests A/B may interleave, causing A to read B's `orderId`. The bug persists even when `currentOrderId` is `volatile` or getters/setters are synchronized separately: **multiple requests share one state slot**.

A stateless design is simpler:

~~~java
@org.springframework.stereotype.Service
class CheckoutService {
    String prepare(String orderId) {
        // Dữ liệu riêng của lời gọi nằm trong biến local.
        String validated = java.util.Objects.requireNonNull(orderId);
        if (validated.isBlank()) {
            throw new IllegalArgumentException("orderId is blank");
        }
        return "Processing " + validated;
    }
}
~~~

A local variable belongs to a method invocation, not a service-wide mutable field. A Spring singleton **can be safe with thread-safe or immutable dependencies**; being a singleton is not inherently wrong. Shared caches, repositories, or schedulers still need correct concurrency contracts.

**`ThreadLocal` note:** It can store context per thread, but should not be the default for request state. Thread pools reuse threads; failing to call `remove()` at the correct lifecycle boundary can leak context across tasks. Asynchronous, reactive, and virtual-thread systems require framework-appropriate context propagation. Explicitly passing context is easier to control when possible.

## 9. `ConcurrentHashMap` does not make every business operation atomic

A concurrent collection protects some operations, but does not make a caller's sequence of operations atomic.

~~~java
import java.util.concurrent.ConcurrentHashMap;

var counts = new ConcurrentHashMap<String, Integer>();

// Không an toàn để tăng đồng thời:
int oldValue = counts.getOrDefault("ORD-1", 0);
counts.put("ORD-1", oldValue + 1);
~~~

Two threads may read the same `oldValue` and lose an update. If the required operation modifies **one key** based on its current value:

~~~java
counts.merge("ORD-1", 1, Integer::sum);
~~~

`ConcurrentHashMap.merge` performs an atomic update to that key's mapping according to the collection contract. It does not make updates across **multiple keys**, a database, and email into one transaction.

Likewise, if map values are mutable `ArrayList` instances, a thread-safe map **does not make the ArrayList contents thread-safe**. Aliasing risk remains:

~~~java
// Một ConcurrentHashMap<String, List<String>> có thể
// được truy cập concurrent, nhưng các List bên trong vẫn
// cần hợp đồng cập nhật riêng hoặc thay bằng giá trị bất biến.
~~~

Ask more than "are we using a concurrent collection?": **what is the invariant-preserving unit of change** — one key, multiple keys, or multiple resources?

## 10. A single JVM and a database/cluster have different scopes

Suppose each application instance has:

~~~java
private final SeatInventory inventory = new SeatInventory(100);
~~~

With two separately deployed application nodes, each has **its own SeatInventory**. Node A's locks do not block node B. If capacity is actually stored in a shared database, a local counter is only a cache/estimate unless synchronized with the source of truth.

A database-side solution is a conditional update followed by checking the affected-row count:

~~~sql
-- Pseudocode SQL, cú pháp điều chỉnh theo cơ sở dữ liệu.
UPDATE inventory
SET reserved = reserved + :quantity
WHERE id = :inventory_id
  AND :quantity > 0
  AND reserved <= capacity - :quantity;
~~~

If the update affects **one** row, the reservation succeeds; if it affects **no** rows, the record may be absent, capacity insufficient, or conditions unmet. The caller must distinguish these outcomes under its contract. Add a constraint for `0 <= reserved <= capacity` and consider numeric overflow/types, isolation levels, retries, and idempotency.

When multiple rows must change together (reserve tickets, create bookings, debit wallets, etc.), use an appropriate **transaction** isolation level or another coordination mechanism. Database transactions usually cannot encompass successful email delivery; transactional outbox, idempotent consumers, or compensation policies may be needed.

**Scope matters.** `synchronized` protects **one Java object in one JVM**, not the whole cluster against overselling.

## 11. Root-cause analysis using "who holds the reference?"

Review ownership and mutation paths with a diagram:

~~~mermaid
flowchart TD
    Input["Caller List mutable"] -->|"truyền reference"| C["Order / Group"]
    Input -.->|"vẫn có thể sửa"| Data["Cùng List object"]
    C -->|"giữ alias"| Data
    Getter["Getter trả List"] -->|"trao alias cho"| Other["Client khác"]
    Other -.->|"add/remove"| Data
    Fix["Defensive copy + controlled methods"] --> Safe["Snapshot bất biến"]
~~~

In the flawed design, a caller modifies state through constructor/getter references without invoking the owning class's mutator. A sound design **transfers ownership by copying** or safely shares immutable values according to a contract.

Specific review questions:

- Where was the object created? Who else keeps mutable references?
- Do methods return collections, arrays, or mutable nested objects?
- Does `final` fix only the field reference or the contents too?
- Does a singleton retain request/user/tenant-specific data?
- Which steps must execute as one atomic change?
- Which threads or nodes can read/write the same data?
- Does failure leave a partially modified state?
- Can shared mutable state be avoided while satisfying the requirements?

## 12. Testing concurrency without relying on luck

A test that sleeps with `Thread.sleep(100)` hoping to trigger a race is **unreliable**. Instead, use `CountDownLatch` or synchronization primitives to control start/stop points and `Future.get()` or `Thread.join()` to collect results.

This JUnit Jupiter 5 example tests the **correct** `SeatInventory` implementation. Put `SeatInventoryTest.java` in the same package as the Java classes in section 4:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class SeatInventoryTest {
    @Test
    void twoConcurrentRequestsCannotBothReserveTheLastSeat()
            throws Exception {
        SeatInventory inventory = new SeatInventory(1);

        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Future<Boolean> a = pool.submit(() -> {
                start.await();
                return inventory.reserveOne();
            });
            Future<Boolean> b = pool.submit(() -> {
                start.await();
                return inventory.reserveOne();
            });

            start.countDown();

            boolean first = a.get(3, TimeUnit.SECONDS);
            boolean second = b.get(3, TimeUnit.SECONDS);

            assertEquals(1,
                    (first ? 1 : 0) + (second ? 1 : 0));

            SeatSnapshot snapshot = inventory.snapshot();
            assertEquals(1, snapshot.reserved());
            assertEquals(0, snapshot.available());
        } finally {
            pool.shutdownNow();
        }
    }

    @Test
    void capacityCannotBeZero() {
        assertThrows(IllegalArgumentException.class,
                () -> new SeatInventory(0));
    }

    @Test
    void rejectedBookingDoesNotMutateState() {
        SeatInventory inventory = new SeatInventory(1);

        assertTrue(inventory.reserveOne());
        assertFalse(inventory.reserveOne());

        assertEquals(1, inventory.snapshot().reserved());
    }
}
~~~

The tests need JUnit Jupiter and a compatible runner. `start` lets tasks begin at roughly the same time, but **does not guarantee identical scheduling**. Reliability comes from checking invariants after the tasks finish; serious races may need systematic stress tests or concurrency models. Timeouts reveal hangs rather than letting the suite wait indefinitely.

### Testing aliasing

A quick test can prove snapshots cannot be modified externally:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class PermissionGroupTest {
    @Test
    void clientCannotEditPermissionsThroughAliasedList() {
        List<String> external = new ArrayList<>(List.of("READ"));
        SafePermissionGroup group = new SafePermissionGroup(external);

        external.add("ADMIN");

        assertFalse(group.has("ADMIN"));
        assertThrows(UnsupportedOperationException.class,
                () -> group.snapshot().add("ADMIN"));
        assertFalse(group.has("ADMIN"));
    }
}
~~~

The test checks **input paths** and **output paths**. For lists of mutable objects, add tests ensuring that elements do not leak internal state or unintended mutation authority.

## 13. Choosing remedies according to shared-state behavior

| Scenario | Approach | What to check |
|---|---|---|
| Shared configuration, unchanged after startup | Immutable config/`static final` | No leaked nested mutable objects |
| Per-request data | Method parameters, locals, correctly scoped request context | Never stored in fields of shared singletons |
| Caller-supplied list | Defensive copy + immutable elements | Shallow versus deep copying |
| Shared counter | `AtomicInteger` or `LongAdder` according to requirements | Approximate count versus snapshot/atomic read; resetting/aggregation |
| Check-then-act on one object | `synchronized`/lock/CAS | Check and update under the same protection |
| Several fields that must remain consistent | One lock or a wholesale immutable-aggregate replacement | Do not expose intermediate states |
| Mutable concurrent collection | `ConcurrentHashMap`/concurrent collection with an appropriate operation contract | Compound actions and mutable values |
| Multi-node shared record | DB transaction/conditional update/optimistic lock | Isolation, retries, idempotency |
| Shared cache | Proven caching library with immutable values | TTL, eviction, stale reads, stampedes |
| Eventual consistency is acceptable | Events, outbox, workers, reconciliation | Define temporary and final states |

No single keyword "cures" all shared state. `volatile`, `synchronized`, atomics, and transactions solve **different constraints at different scopes**. Often the best option is **not sharing mutable state**.

## 14. Exercise: managing a coupon usage limit

A coupon allows **at most 100 uses**. Its API handles concurrent requests.

### Requirements

Design `CouponQuota` with:

- Immutable `maxUses` greater than 0.
- Nonnegative `used` that never exceeds `maxUses`.
- A `boolean tryUse()` method returning `true` only when **exactly one** use is recorded.
- A `snapshot()` method returning an immutable `used`/`remaining` pair.
- No public setters and no direct increment of `used` by callers.
- Tests issuing at least 500 concurrent `tryUse()` requests and ending with **exactly 100 successes** and usage of 100.
- A multi-node extension describing conditional updates or DB versions/constraints instead of relying on one Java instance's lock.

Implement an initial version with `synchronized`, then another with `AtomicInteger.compareAndSet`. Compare clarity, amount of code, and the scope of invariants each protects.

### Self-check

1. Why is a `private final List<String>` field insufficient by itself?
2. If two variables reference one `ArrayList`, how do changes through one affect the other?
3. Why can `volatile int count; count++` still lose updates?
4. In the ticket example, why can `reserved == 1` be a **wrong business outcome** even though both requests are accepted?
5. What risks arise from a `currentOrderId` field in a Spring singleton under concurrent load?
6. How does `Collections.unmodifiableList(source)` differ from the `List.copyOf(source)` snapshot?
7. When is `AtomicInteger` sufficient versus a lock guarding several fields?
8. Does `ConcurrentHashMap` make its `ArrayList` values thread-safe?
9. Why can node A's `synchronized` not protect ticket sales on node B?
10. Where can local variables, immutable snapshots, or explicit parameters eliminate mutable shared state?

**Conclusion:** "Hard-to-control shared state" means more than global variables or multiple threads. The underlying problem is **unclear ownership, mutation rights, observation timing, and consistency boundaries**. Robust OOP designs **encapsulate state, expose domain operations, restrict mutable aliases, and prefer immutable data**, then choose synchronization/transactions according to the actual scope of sharing.
