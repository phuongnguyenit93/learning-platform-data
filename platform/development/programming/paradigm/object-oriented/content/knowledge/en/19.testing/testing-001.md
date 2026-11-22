# Testing Public Behavior and Object Contracts in Java OOP

> **Topic:** OOP → Testing → Testing public behavior and object contracts.  
> **Objective:** Write tests against what clients can actually observe and legitimately request, rather than coupling tests to fields/private methods; specify contracts through preconditions, postconditions, invariants, and error handling; reuse a single test suite across multiple implementations of an interface; detect regressions when a replacement implementation still compiles.

## 1. What Does It Mean to Test an Object?

An object is more than a collection of fields. It exposes a **behavioral interface**: callable operations, return values, side effects, state after each operation, and conditions under which an operation is rejected.

Suppose a seat inventory has 10 available seats. A client requests:

~~~text
Kho vé sức chứa 10
    ├─ tryReserve(4)  → true   → đã đặt 4, còn 6
    ├─ tryReserve(7)  → false  → vẫn đã đặt 4, còn 6
    └─ cancel(2)      → thành công → đã đặt 2, còn 8
~~~

This is **observable behavior**. A good test need not know whether the inventory uses `int reserved`, `AtomicInteger`, `HashMap`, or a database; it should verify **the results and rules promised by the API**.

An **object contract** describes API semantics, not merely Java signatures. For instance, `boolean tryReserve(int count)` does not establish:

- Is `count = 0` valid?
- Does insufficient capacity return `false` or throw an exception?
- Does a failed operation change state?
- After success, by exactly how many seats does the reservation count increase?
- Are concurrent reservations by multiple threads permitted?
- What must remain unchanged when a new implementation replaces an existing one?

Contract tests turn these guarantees into **executable examples** and help detect changes that break *substitutability*.

## 2. Public Behavior Versus Implementation Details

| Test Through Public Behavior | Avoid Depending On Without a Specific Reason |
|---|---|
| `tryReserve(4)` returns `true`, and the snapshot correctly reports 4 reserved seats | Whether the internal field is named `reserved` or `taken` |
| `tryReserve(7)` returns `false` without changing state | Whether private method `hasEnoughSeats()` was invoked |
| `cancel(2)` reduces reserved seats from 4 to 2 | Whether source code uses one or two private helpers |
| Invalid input is rejected using the promised exception | Which source-code line throws it |
| Two implementations meet the same contract suite | Whether the internal mechanism specifically uses `synchronized`, CAS, or a lock |
| External events/collaborators are invoked as contracted, if that is observable behavior | How often a private helper runs when the count has no effect on outcomes |

Refactoring `int reserved` into `AtomicInteger reserved` without **changing behavior** should not cause most unit tests to fail. If tests constantly break whenever the internal structure changes, they are **too tightly coupled to the implementation**.

**This does not mean every test must be strictly black-box.** Unit tests for a pure algorithm or an internal adapter can be appropriate; integration tests may verify DB/HTTP interactions. But tests of an **object contract** should use the API real clients use and assert only the guarantees that must remain stable.

## 3. Four Parts of a Testable Contract

A contract is often described through:

| Part | Question | Seat Inventory |
|---|---|---|
| **Precondition** | What must the caller satisfy? | Reservation/cancellation quantities must be positive |
| **Successful postcondition** | What must hold after a successful call? | Reserving 3 seats increases the reserved count by exactly 3 |
| **Failure postcondition** | How does the object remain valid after a rejection/error? | Insufficient capacity returns `false` without changing state |
| **Invariant** | What condition must always hold at an observable boundary? | `0 ≤ reserved ≤ capacity` |

Real programs may also require **nonfunctional guarantees** that must be stated as needed: thread safety, latency, data-write consistency, idempotency, callback ordering, or access-control constraints. No interface automatically promises all these properties.

### Example Contract Specification

Define an interface for managing seat reservations with these rules:

- The implementation constructor requires `capacity > 0`.
- Initially, the reserved seat count is `0`.
- `tryReserve(n)`: if `n <= 0`, throw `IllegalArgumentException`; if capacity permits, increase the reserved count by `n` and return `true`; otherwise, return `false` without changing state.
- `cancel(n)`: requires `n > 0` and `n <= reserved`; otherwise, throw `IllegalArgumentException` **without modifying state**; if valid, subtract `n`.
- `snapshot()` returns an immutable, consistent snapshot of `capacity` and `reserved` at the moment the method executes.
- Every implementation supports calls from multiple threads in the same JVM; each reservation/cancellation call must act as one atomic change to **a single instance**.

**Note:** This contract is chosen for the example, not prescribed for every ticket-reservation system. Another system might return a `Result` object instead of a boolean, or model excess cancellation as a different domain error. Tests must follow the real contract, not arbitrary preferences of the test author.

## 4. Complete Java 17 Example: One Interface, Two Implementations

To demonstrate the value of contract testing, we build two implementations with **different state-storage mechanisms** but **the same public API**:

- `MonitorSeatInventory` uses `synchronized`.
- `AtomicSeatInventory` uses `AtomicInteger` and a compare-and-set (CAS) loop.

Both must preserve the same business rules regardless of synchronization technique.

Create **`SeatInventoryDemo.java`** using only JDK 17+:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

// Dữ liệu quan sát được, immutable nhờ record với thành phần primitive.
record SeatSnapshot(int capacity, int reserved) {
    SeatSnapshot {
        if (capacity <= 0 || reserved < 0 || reserved > capacity) {
            throw new IllegalArgumentException("Invalid seat snapshot");
        }
    }

    int available() {
        return capacity - reserved;
    }
}

// Hợp đồng mà client phụ thuộc: không tiết lộ cách lưu state.
interface SeatInventory {
    boolean tryReserve(int count);
    void cancel(int count);
    SeatSnapshot snapshot();
}

// Cách A: khóa bảo vệ toàn bộ check + update trên một instance.
final class MonitorSeatInventory implements SeatInventory {
    private final int capacity;
    private int reserved;

    MonitorSeatInventory(int capacity) {
        if (capacity <= 0) {
            throw new IllegalArgumentException("capacity must be positive");
        }
        this.capacity = capacity;
    }

    @Override
    public synchronized boolean tryReserve(int count) {
        requirePositive(count);

        if (count > capacity - reserved) {
            return false;
        }

        reserved += count;
        return true;
    }

    @Override
    public synchronized void cancel(int count) {
        requirePositive(count);

        if (count > reserved) {
            throw new IllegalArgumentException(
                    "Cannot cancel more than reserved");
        }

        reserved -= count;
    }

    @Override
    public synchronized SeatSnapshot snapshot() {
        return new SeatSnapshot(capacity, reserved);
    }

    private static void requirePositive(int count) {
        if (count <= 0) {
            throw new IllegalArgumentException("count must be positive");
        }
    }
}

// Cách B: CAS đảm bảo không làm mất cập nhật trên một biến.
final class AtomicSeatInventory implements SeatInventory {
    private final int capacity;
    private final AtomicInteger reserved = new AtomicInteger();

    AtomicSeatInventory(int capacity) {
        if (capacity <= 0) {
            throw new IllegalArgumentException("capacity must be positive");
        }
        this.capacity = capacity;
    }

    @Override
    public boolean tryReserve(int count) {
        requirePositive(count);

        while (true) {
            int current = reserved.get();

            // Trừ trước để không làm tràn số nguyên do cộng.
            if (count > capacity - current) {
                return false;
            }

            if (reserved.compareAndSet(current, current + count)) {
                return true;
            }
            // Có cập nhật cạnh tranh: đọc lại và thử.
        }
    }

    @Override
    public void cancel(int count) {
        requirePositive(count);

        while (true) {
            int current = reserved.get();

            if (count > current) {
                throw new IllegalArgumentException(
                        "Cannot cancel more than reserved");
            }

            if (reserved.compareAndSet(current, current - count)) {
                return;
            }
        }
    }

    @Override
    public SeatSnapshot snapshot() {
        // capacity không đổi; reserved.get là một phép đọc atomic.
        return new SeatSnapshot(capacity, reserved.get());
    }

    private static void requirePositive(int count) {
        if (count <= 0) {
            throw new IllegalArgumentException("count must be positive");
        }
    }
}

public class SeatInventoryDemo {
    public static void main(String[] args) {
        SeatInventory inventory = new MonitorSeatInventory(10);

        System.out.println("Start: " + inventory.snapshot());
        System.out.println("Reserve 4: " + inventory.tryReserve(4));
        System.out.println("Reserve 7: " + inventory.tryReserve(7));
        System.out.println("After refusal: " + inventory.snapshot());

        inventory.cancel(2);
        System.out.println("After cancel: " + inventory.snapshot());

        // Không sửa nghiệp vụ client khi đổi implementation:
        SeatInventory another = new AtomicSeatInventory(10);
        System.out.println("Atomic reserve 4: " + another.tryReserve(4));
        System.out.println("Atomic snapshot: " + another.snapshot());
    }
}
~~~

Run:

~~~bash
javac SeatInventoryDemo.java
java SeatInventoryDemo
~~~

Output:

~~~text
Start: SeatSnapshot[capacity=10, reserved=0]
Reserve 4: true
Reserve 7: false
After refusal: SeatSnapshot[capacity=10, reserved=4]
After cancel: SeatSnapshot[capacity=10, reserved=2]
Atomic reserve 4: true
Atomic snapshot: SeatSnapshot[capacity=10, reserved=4]
~~~

**The important question is not whether locking or CAS is better.** The example provides two technical approaches, while tests verify **one shared set of promised behaviors**.

### Class Diagram from the Client's Perspective

~~~mermaid
classDiagram
    class SeatInventory {
        <<interface>>
        +tryReserve(count) boolean
        +cancel(count) void
        +snapshot() SeatSnapshot
    }
    class MonitorSeatInventory {
        -int reserved
        +tryReserve(count) boolean
        +cancel(count) void
        +snapshot() SeatSnapshot
    }
    class AtomicSeatInventory {
        -AtomicInteger reserved
        +tryReserve(count) boolean
        +cancel(count) void
        +snapshot() SeatSnapshot
    }
    class SeatSnapshot {
        <<record>>
        +capacity() int
        +reserved() int
        +available() int
    }

    SeatInventory <|.. MonitorSeatInventory
    SeatInventory <|.. AtomicSeatInventory
    SeatInventory ..> SeatSnapshot : công bố
~~~

## 5. Write Tests from the Contract First, Then Apply Them to Both Classes

Writing completely separate test suites risks forgetting failure-path tests for one implementation. A useful approach is **one reusable suite of contract tests**: tests know only the `SeatInventory` interface, while test subclasses provide a way to create each implementation.

In JUnit Jupiter 5, subclasses can inherit `@Test` methods from a test superclass. We use this feature to run the same rules against both Monitor and Atomic.

Create **`SeatInventoryContractTest.java`** in the test source set, in the same package as `SeatInventoryDemo.java`:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

// Abstract contract test: không biết field/lock/CAS của implementation.
abstract class SeatInventoryContractTest {
    protected abstract SeatInventory create(int capacity);

    @Test
    void startsEmptyAndExposesConsistentSnapshot() {
        SeatInventory inventory = create(10);

        SeatSnapshot initial = inventory.snapshot();

        assertEquals(10, initial.capacity());
        assertEquals(0, initial.reserved());
        assertEquals(10, initial.available());
    }

    @Test
    void acceptsReservationAndChangesObservableState() {
        SeatInventory inventory = create(10);

        assertTrue(inventory.tryReserve(4));

        SeatSnapshot snapshot = inventory.snapshot();
        assertEquals(4, snapshot.reserved());
        assertEquals(6, snapshot.available());
    }

    @Test
    void insufficientCapacityReturnsFalseWithoutMutation() {
        SeatInventory inventory = create(10);
        assertTrue(inventory.tryReserve(4));

        SeatSnapshot before = inventory.snapshot();
        assertFalse(inventory.tryReserve(7));
        SeatSnapshot after = inventory.snapshot();

        assertEquals(before, after); // So sánh record theo giá trị.
    }

    @Test
    void cancellationDecreasesReservation() {
        SeatInventory inventory = create(10);
        assertTrue(inventory.tryReserve(4));

        inventory.cancel(2);

        SeatSnapshot after = inventory.snapshot();
        assertEquals(2, after.reserved());
        assertEquals(8, after.available());
    }

    @Test
    void invalidArgumentsThrowAndDoNotChangeState() {
        SeatInventory inventory = create(10);
        assertTrue(inventory.tryReserve(3));

        SeatSnapshot before = inventory.snapshot();

        assertThrows(IllegalArgumentException.class,
                () -> inventory.tryReserve(0));
        assertThrows(IllegalArgumentException.class,
                () -> inventory.tryReserve(-1));
        assertThrows(IllegalArgumentException.class,
                () -> inventory.cancel(0));
        assertThrows(IllegalArgumentException.class,
                () -> inventory.cancel(4));

        assertEquals(before, inventory.snapshot());
    }

    @Test
    void exactCapacityAndReleaseAllAreAllowed() {
        SeatInventory inventory = create(2);

        assertTrue(inventory.tryReserve(2));
        assertFalse(inventory.tryReserve(1));
        assertEquals(0, inventory.snapshot().available());

        inventory.cancel(2);

        assertEquals(0, inventory.snapshot().reserved());
        assertEquals(2, inventory.snapshot().available());
    }

    @Test
    void invalidCapacityIsRejected() {
        assertThrows(IllegalArgumentException.class, () -> create(0));
        assertThrows(IllegalArgumentException.class, () -> create(-1));
    }
}

// Hai implementation được kiểm tra bằng CÙNG bộ @Test.
class MonitorSeatInventoryTest extends SeatInventoryContractTest {
    @Override
    protected SeatInventory create(int capacity) {
        return new MonitorSeatInventory(capacity);
    }
}

class AtomicSeatInventoryTest extends SeatInventoryContractTest {
    @Override
    protected SeatInventory create(int capacity) {
        return new AtomicSeatInventory(capacity);
    }
}
~~~

**Expected result:** JUnit runs the same inherited tests for both concrete test subclasses. Every implementation must satisfy the full contract. The abstract superclass specifies observable requirements only; it never checks whether `reserved` is an `int` or an `AtomicInteger`.

To run these tests, add JUnit Jupiter to the test dependencies and use a Maven/Gradle/IDE test runner. Both concrete test classes are **package-private**, which JUnit Jupiter 5 permits; depending on the build tool's discovery configuration, ensure the source is in the test source set and the `*Test` class names are detected.

### Why Is the “Failure Leaves State Unchanged” Test Important?

An incorrect implementation might do this:

~~~java
// CỐ Ý SAI: tăng reserved trước rồi mới kiểm tra.
reserved += count;
if (reserved > capacity) {
    return false;
}
~~~

A test asserting only `tryReserve(7) == false` **would pass**, even though `reserved` has been corrupted. Comparing **snapshots before and after** detects the contract violation. Similarly, canceling more seats than reserved must throw an exception **without leaving a partially changed state**.

## 6. Structure Tests Using Given–When–Then

A behavioral test is easier to read when it has three clear parts:

- **Given:** the initial state and data needed to construct the object.
- **When:** a public operation is invoked.
- **Then:** the result, exception, observable state, or side effect matches the contract.

Example:

~~~java
@Test
void rejectedReservationKeepsPreviousState() {
    // Given
    SeatInventory inventory = new MonitorSeatInventory(5);
    inventory.tryReserve(4);
    SeatSnapshot before = inventory.snapshot();

    // When
    boolean accepted = inventory.tryReserve(2);

    // Then
    assertFalse(accepted);
    assertEquals(before, inventory.snapshot());
}
~~~

The name `rejectedReservationKeepsPreviousState` describes **the rule** under test better than `testReserve` or `test1`. The “Then” section should use a legitimate observable API. Do not add setters merely to make tests convenient; that may weaken encapsulation.

## 7. Test State Sequences, Not Just Individual Methods

A stateful object often has **multiple valid paths**. Testing each method independently can miss bugs that appear only after a sequence of operations.

~~~mermaid
stateDiagram-v2
    [*] --> Empty : new(10)
    Empty --> Partial : reserve(4) = true
    Partial --> Partial : reserve(7) = false
    Partial --> Partial : cancel(2)
    Partial --> Full : reserve(8) = true
    Full --> Full : reserve(1) = false
    Full --> Empty : cancel(all)
~~~

The diagram uses a capacity of 10: after reserving 4 and canceling 2, 2 reservations remain; reserving 8 fills the capacity. This is **multi-step behavior**, not an isolated method.

### State Table Testing

| State Before | Command | Result | State After |
|---|---|---|---|
| capacity=10, reserved=0 | `tryReserve(4)` | `true` | reserved=4 |
| capacity=10, reserved=4 | `tryReserve(7)` | `false` | reserved=4 |
| capacity=10, reserved=4 | `cancel(2)` | Success | reserved=2 |
| capacity=10, reserved=2 | `tryReserve(8)` | `true` | reserved=10 |
| capacity=10, reserved=10 | `tryReserve(1)` | `false` | reserved=10 |
| capacity=10, reserved=10 | `cancel(10)` | Success | reserved=0 |

Boundary inputs `0`, `1`, `capacity`, `capacity + 1`, and negative values also deserve tests. For objects with many states and paths, a table avoids covering only the happy path while forgetting rejection rules.

### Testing Against a Simple Reference Model

For a stateful API, a test can maintain a simple **reference model** of expected values and exercise many operation sequences. The reference model should be simpler than the real implementation and should avoid reusing its optimized algorithm, so both do not reproduce the same bug.

The following is an additional test using the earlier classes and JUnit imports; add `import java.util.Random;`:

~~~java
@Test
void sequenceOfOperationsAlwaysMatchesSimpleModel() {
    SeatInventory inventory = create(20);
    Random random = new Random(2026L);
    int expectedReserved = 0;

    for (int step = 0; step < 500; step++) {
        int quantity = 1 + random.nextInt(7);

        if (random.nextBoolean()) {
            boolean shouldAccept = quantity <= 20 - expectedReserved;
            assertEquals(shouldAccept,
                    inventory.tryReserve(quantity));

            if (shouldAccept) {
                expectedReserved += quantity;
            }
        } else if (quantity <= expectedReserved) {
            inventory.cancel(quantity);
            expectedReserved -= quantity;
        } else {
            // Với precondition sai, exception không đổi trạng thái.
            assertThrows(IllegalArgumentException.class,
                    () -> inventory.cancel(quantity));
        }

        SeatSnapshot snapshot = inventory.snapshot();
        assertEquals(20, snapshot.capacity());
        assertEquals(expectedReserved, snapshot.reserved());
        assertEquals(20 - expectedReserved, snapshot.available());
    }
}
~~~

**Benefit:** a fixed seed yields a reproducible sequence that explores varied states without hand-writing 500 test cases. **Limit:** one seed and 500 steps are not formal proof of all sequences; combine them with boundary cases, additional seeds, or property-based testing when risks are higher.

**Note:** If methods have other side effects (DB writes, event publication), the reference model must describe those observable effects as well; comparing only in-memory state is insufficient.

## 8. Testing Implementation Substitutability (LSP)

The **Liskov Substitution Principle (LSP)** requires an implementation to be usable where its abstraction is expected **without violating client assumptions**. Contract testing provides useful empirical evidence: run the same tests against every implementation.

Suppose a new implementation decides to do this:

~~~java
// Vi phạm hợp đồng ví dụ:
boolean tryReserve(int count) {
    if (count <= 0) {
        return false; // Sai: contract yêu cầu IllegalArgumentException.
    }
    // ...
}
~~~

The compiler **does not complain** because method signatures still match. But the contract test `invalidArgumentsThrowAndDoNotChangeState` fails. Likewise, throwing `IllegalStateException` on insufficient capacity rather than returning `false` changes behavior for clients that rely on the boolean result.

An interface **does not guarantee LSP by itself**. The signature is only part of the contract; input/output semantics, exceptions, consistency, and side-effect guarantees also matter.

Practical principles include:

- An implementation should not unexpectedly **strengthen preconditions** if the abstraction permits more inputs.
- An implementation should not **weaken promised postconditions**.
- All invariants must remain true when clients access an object through its abstraction.
- For exceptions, distinguish caller programming errors, expected business failures, and infrastructure failures; do not change failure modes without updating the contract.

**Contract tests cannot mathematically prove complete LSP compliance.** They exercise selected scenarios. Design reviews must also examine the subtype relationship and untested guarantees, especially performance, concurrency, transaction behavior, and security.

## 9. Testing Value Object Contracts: `equals`, `hashCode`, and `toString`

In Java, methods inherited from `Object` also have contracts worth considering. Not every class overrides them, however. Two types of tests are distinct:

1. **Business contract:** `SeatInventory` maintains `0 ≤ reserved ≤ capacity`.
2. **Value contract:** a value object implements `equals`/`hashCode` correctly and provides an appropriate diagnostic representation.

In this example, `SeatSnapshot` is a `record` containing primitives. Java supplies `equals` and `hashCode` based on its components. We can test them through the public API:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.HashSet;
import java.util.Set;
import org.junit.jupiter.api.Test;

class SeatSnapshotValueTest {
    @Test
    void equalSnapshotsAreEqualAndHaveEqualHashCodes() {
        SeatSnapshot a = new SeatSnapshot(10, 4);
        SeatSnapshot b = new SeatSnapshot(10, 4);
        SeatSnapshot different = new SeatSnapshot(10, 5);

        assertEquals(a, b);
        assertEquals(a.hashCode(), b.hashCode());
        assertNotEquals(a, different);

        Set<SeatSnapshot> set = new HashSet<>();
        set.add(a);
        assertTrue(set.contains(b));
    }

    @Test
    void rejectsBrokenInvariant() {
        assertThrows(IllegalArgumentException.class,
                () -> new SeatSnapshot(10, 11));
        assertThrows(IllegalArgumentException.class,
                () -> new SeatSnapshot(0, 0));
    }
}
~~~

This tests the **value** contract. For an entity with **identity**, two different objects containing the same display data may not be considered equal; define the intended `equals` semantics before writing tests.

### Common `equals` Rules

| Rule | Meaning | Simple Test |
|---|---|---|
| Reflexive | `x.equals(x) == true` | `assertEquals(x, x)` |
| Symmetric | `x.equals(y) == y.equals(x)` | Compare in both directions |
| Transitive | If `x==y` and `y==z`, then `x==z` according to `equals` | Create three equivalent instances |
| Consistent | With no changes to comparison-relevant data, the outcome remains unchanged | Repeat the call on stable state |
| Not equal to null | `x.equals(null) == false` | `assertNotEquals(null, x)` |
| Compatible hash codes | If `x.equals(y)`, then `x.hashCode()==y.hashCode()` | Compare hashes and use a `HashSet` |

Do not infer the reverse: **equal hash codes do not imply equal objects**. Different objects may legitimately have the same hash.

`toString()` is generally for observation/debugging, not a stable API format unless the class explicitly promises one. Avoid tests that match every punctuation mark in `toString()` when its format is not part of the contract. For sensitive data, test what **must not be disclosed**, and consider other logging paths as well.

## 10. Do Not Expose Private Fields or Add Setters Just to Make Testing Easier

An example of a harmful test:

~~~java
// Ý tưởng KHÔNG NÊN làm mặc định:
Field field = MonitorSeatInventory.class
        .getDeclaredField("reserved");
field.setAccessible(true);
field.setInt(inventory, 4);
~~~

If a test knows a field's name and uses reflection to change it, the test bypasses the boundary that the class is supposed to protect. Renaming the field or switching to `AtomicInteger` then breaks the test even when clients are unaffected.

Similarly, adding `setReserved(int)` merely to construct test states quickly can weaken the production API by allowing clients to bypass reservation rules. Instead, create valid states through **public operations**:

~~~java
SeatInventory inventory = new MonitorSeatInventory(10);
assertTrue(inventory.tryReserve(4));
// Bây giờ có trạng thái reserved = 4, hợp lệ và tạo qua API thật.
~~~

If setup becomes excessive because every test must traverse several external systems, consider **test fixtures/builders** for constructing suitable dependencies or data. Fixtures should not create impossible states that legitimate operations cannot reach, unless explicitly testing recovery from corrupted legacy data.

### Avoid Over-Specifying Internal Call Counts

Mocks are valuable when interaction with a dependency **is part of the contract**, such as publishing exactly one event after a successful payment. But a test checking only `verify(calculator).calculate(...)` without asserting a result or observable consequence may pass even when the business outcome is wrong.

Distinguish among:

- **State-based test:** verifies publicly exposed state or results.
- **Interaction-based test:** verifies meaningful externally observable interactions with collaborators, such as sending exactly one notification.
- **Implementation-coupled test:** checks the order of private helpers or call counts of a pure algorithm that callers cannot observe.

Interaction tests are not inherently inferior. What matters is whether an interaction **is required by the contract or merely reflects the current implementation**.

## 11. Testing Errors and Exceptions: Failure Is Also Behavior

A well-defined public contract explains how invalid inputs are handled:

| Scenario | Example Behavior | What the Test Must Verify |
|---|---|---|
| Construct inventory with `capacity = 0` | Throws `IllegalArgumentException` | No falsely valid object is created |
| Reserve `0` or a negative number | Throws `IllegalArgumentException` | State remains unchanged |
| Request more seats than available | Returns `false` | State remains unchanged |
| Cancel more than the reserved count | Throws `IllegalArgumentException` | State remains unchanged |
| Cancel exactly the reserved count | Succeeds | State returns to reserved=0 |
| Replace the Monitor implementation with Atomic | Preserve all public semantics | The contract test suite still passes |

Use `assertThrows` to check the promised exception type. If the exception message is not a stable API guarantee, avoid hardcoding its exact text in tests. If an error code is part of an external contract, assert the structured code rather than the wording of a message.

### Atomicity of Failure Paths

In the example, invalid quantities cause an exception **before** state is updated. In more complex operations, if a database write succeeds and an email later fails, throwing an exception does not mean that every side effect has been rolled back. Tests must specify post-failure state according to actual consistency mechanisms: transactions, outbox, retries, or compensation.

## 12. Contract Tests and Concurrency Testing

If an abstraction promises that two threads may call `tryReserve(1)` on the same instance, atomicity is **part of the contract**, not merely an implementation detail.

A JUnit Jupiter 5 example tests **any implementation** through the interface. This can be placed in `SeatInventoryContractTest` with the necessary imports:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

@Test
void concurrentReservationsNeverOversellOneInstance()
        throws Exception {
    SeatInventory inventory = create(5);
    int attempts = 12;

    CountDownLatch ready = new CountDownLatch(attempts);
    CountDownLatch start = new CountDownLatch(1);
    ExecutorService pool = Executors.newFixedThreadPool(attempts);

    try {
        List<Future<Boolean>> results = new ArrayList<>();

        for (int i = 0; i < attempts; i++) {
            results.add(pool.submit(() -> {
                ready.countDown();
                start.await();
                return inventory.tryReserve(1);
            }));
        }

        assertTrue(ready.await(5, TimeUnit.SECONDS));
        start.countDown();

        int accepted = 0;
        for (Future<Boolean> future : results) {
            if (future.get(5, TimeUnit.SECONDS)) {
                accepted++;
            }
        }

        assertEquals(5, accepted);
        assertEquals(5, inventory.snapshot().reserved());
        assertEquals(0, inventory.snapshot().available());
    } finally {
        start.countDown(); // Không để task chờ vô hạn nếu assert fail.
        pool.shutdownNow();
    }
}
~~~

This verifies **the final result** after every call completes while two threads/groups of threads contend for seats. `CountDownLatch` helps them start at roughly the same time but **does not mathematically prove correctness for all possible thread schedules**. High-risk concurrency requires stress tests, memory-model review, specialized concurrency testing tools, and/or formal modeling.

Avoid `Thread.sleep` with arbitrary time delays to decide whether tests pass or fail. Do not check `reserved + available == capacity` using **two different snapshot calls at different moments** while threads are still updating; obtain **one consistent snapshot** and calculate using its fields.

### One-JVM Limitation

A thread-safety contract for one Java object does not automatically prevent overselling seats when two JVMs update **the same database record**. In a multi-node deployment, a service-level contract needs verification through transactions, conditional updates, or optimistic locking in persistence. Unit tests of `AtomicSeatInventory` cannot replace DB integration tests.

## 13. Test Layers: One Contract, Different Forms of Evidence

| Layer | Objective | Example |
|---|---|---|
| **Object unit test** | Public behavioral contract of one object | `tryReserve`, `cancel`, `snapshot` |
| **Interface contract test** | All implementations preserve shared semantics | Monitor and Atomic run the same suite |
| **Component/integration test** | Interaction among classes or real systems | Seat inventory persisted through repository/JDBC |
| **API test** | HTTP/JSON/status-code contract | Sold-out inventory returns an appropriate business error code |
| **Concurrency test** | Consistency under interleaved operations | Concurrent requests cannot reserve the same seat twice |
| **End-to-end test** | User workflow across components | Select a seat → reserve it → confirm the displayed result |

A fast unit test may establish correct in-memory `SeatInventory` logic, but it cannot establish correctness of DB locks, rollback, API serialization, or end-user experience. Choose **a test level appropriate to the contract boundary**.

## 14. Test Design Mistakes That Reduce Test Value

### Mistake A: Testing an Implementation Instead of Its Contract

~~~java
// Đáng ngờ:
assertEquals("java.util.concurrent.atomic.AtomicInteger",
        inventory.getClass()
                .getDeclaredFields()[0]
                .getType()
                .getName());
~~~

This test says nothing about whether the inventory behaves correctly; it merely locks in an implementation choice. Switching from atomic state to locks may be a valid refactor, but the test would fail unnecessarily.

### Mistake B: Asserting Only the Return Value and Ignoring State

~~~java
assertFalse(inventory.tryReserve(100));
~~~

If an implementation still increments `reserved` before returning `false`, this test misses the bug. Capture snapshots before and after and verify the invariant.

### Mistake C: Testing Failure by Corrupting Private State

If a test uses reflection to set `reserved = -5` and then expects `tryReserve` to repair it, the test imposes a state **not reachable through the valid API**. Unless the real requirement is recovery from corrupted legacy data, test instead that all **public mutation paths** never create such a state.

### Mistake D: Tests Depend on Execution Order or Shared State

Having every test mutate a `static SeatInventory shared` causes results to vary when JUnit runs tests in parallel or changes their order. Give each test an **independent fixture** with a fresh instance. Shared databases require an explicit isolation/cleanup strategy.

### Mistake E: Mocking the Very Object Under Test

If you mock all of `SeatInventory` and configure `when(tryReserve(4)).thenReturn(true)`, you test only behavior **programmed into the mock**, not the real implementation. Use mocks/fakes for collaborators outside the test scope; do not replace the system under test when verifying its contract.

### Mistake F: Overcoupling Tests to Logger Implementations, Time, or Randomness

If the contract does not require an exact log message, verify observable outcomes rather than matching log text verbatim. When the clock or randomness is a genuine business input, inject a `Clock` or controlled random generator/fake so the test is not flaky.

## 15. Writing Contract Tests for Real Adapters

The shared testing pattern applies beyond two in-memory state mechanisms. For example, `DocumentStore` may have file-based and database implementations:

~~~java
interface DocumentStore {
    void save(String id, byte[] bytes);
    java.util.Optional<byte[]> find(String id);
}
~~~

A contract might require:

- Reject null or empty IDs.
- Saving data and reading it back returns identical **byte content**.
- A missing ID returns `Optional.empty()`.
- Modifying the `byte[]` argument after `save` must not silently modify stored data.
- Modifying the `byte[]` returned by `find` must not silently change stored data when the API promises snapshots.
- Duplicate IDs must follow an explicit **overwrite** or **reject** policy, consistently implemented by both implementations.

Because `byte[]` arrays are mutable, **defensive copies** are necessary at input and output boundaries if promised by the API. An `InMemoryDocumentStore` that retains the original byte array's reference can violate the contract despite having the correct method signature.

This shows why **contract tests provide more value than counting methods**: they preserve behavior the Java type system cannot directly express, such as **ownership of a mutable buffer** and duplicate-save failure semantics.

## 16. Checklist for Designing Public Behavior Tests

Before writing tests, answer:

1. **What does the object promise?** Specify preconditions, postconditions, invariants, and failure modes.
2. **Which API is the public contract?** Do not expose private fields merely because setup is difficult.
3. **What is the initial state?** Every test should construct a consistent, independent fixture.
4. **Which observable results should be compared?** Return values, snapshots, exceptions, events, or persisted data.
5. **Are there rejection paths?** What should happen to state and side effects on failure?
6. **What are the boundary cases?** Zero, negative, maximum, empty, null, duplicates, overflow, and state transitions.
7. **Are multiple implementations present?** Use the same contract suite to verify substitutability.
8. **Are time/concurrency/I/O involved?** Use a clock, fakes, fixtures, integration tests, and properly scoped synchronization.
9. **Will tests become brittle after internal refactoring?** Remove assertions outside the contract and retain those clients need.
10. **Has the contract change been approved?** When business rules evolve, intentionally update the specification and tests; do not change tests merely to make them green.

A useful technique is naming tests as sentences of the form **“When X, the system must Y”** so even a reviewer unfamiliar with the implementation understands them. A name like `testPrivateHelperA` likely misses the behavior clients care about.

## 17. Practical Exercise: Digital Wallet Contract

Design an interface:

~~~java
interface Wallet {
    long balanceCents();
    void deposit(long amountCents);
    boolean tryWithdraw(long amountCents);
}
~~~

Assumed rules:

- A wallet starts with a nonnegative balance.
- `deposit(n)` requires `n > 0`; on success it increases the balance by exactly `n`.
- `tryWithdraw(n)` requires `n > 0`; with sufficient funds, it subtracts exactly `n` and returns `true`; otherwise it returns `false` without changing the balance.
- The balance never becomes negative; handle deposit overflow (`Math.addExact` or pre-checks).
- Operations on **one instance** support multiple threads; two withdrawals cannot both succeed using the same stale balance.
- Tests should use integers representing **the smallest monetary unit** to avoid binary floating-point errors in this example.

Requirements:

1. Implement `SynchronizedWallet` and `AtomicWallet`.
2. Write one abstract contract test that runs the same `@Test` methods for both implementations.
3. Test `deposit(0)`, negative withdrawals, withdrawals exceeding the balance, overflowing a `long` deposit, and unchanged state after errors.
4. Test the sequence `deposit(100) → withdraw(30) → withdraw(80 bị từ chối)`.
5. Test two threads each withdrawing 80 from a wallet with 100; **only one succeeds**.
6. Explain why these unit tests do not establish correctness of real-money transactions in a database or payment service.

### Self-Check Questions

1. How does “testing public behavior” differ from inspecting private fields?
2. Why does matching a method signature not guarantee that two implementations are interchangeable?
3. How do preconditions, postconditions, and invariants differ?
4. Why is asserting only `tryReserve(7) == false` insufficient?
5. Why run the same contract suite for every implementation of an interface?
6. When should you test `equals/hashCode`, and why do equal `hashCode` values not imply equal objects?
7. Should reflection be used to change private state merely to shorten test setup?
8. Why do exact log-message assertions make tests brittle when logs are not contractual?
9. Is a one-JVM concurrency test enough to prove that tickets cannot be oversold across multiple nodes?
10. What observable effects matter when a method both updates a DB and publishes an event?

**Remember:** Good OOP tests answer **“Does the object fulfill its promises to clients?”** Specify contracts in observable terms, test success and failure, use state snapshots and operation sequences, and apply one suite to substitutable implementations. Decoupling tests from internals makes refactoring easier **without lowering the correctness bar for behavior**.
