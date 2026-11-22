# Exposed state and broken invariants in OOP

> **Topic:** OOP → Design Pitfalls → Exposed state and broken invariants.  
> **Objective:** Recognize how external data paths can corrupt an object's state; understand how invariants differ from input validation; and use encapsulation, domain operations, defensive copies, and tests to protect Java objects.

## 1. The problem: objects can become "self-contradictory" even after valid construction

Suppose a ticketing system has a seat inventory with **capacity 10**, **4** reserved seats, and **6** available. These numbers must satisfy:

\[
0 \le \text{reserved} \le \text{capacity}
\]

and \(\text{available}=\text{capacity}-\text{reserved}\).

This is an **object invariant**: a condition that must hold whenever an object's state can be observed externally, especially **after successful construction** and **after each public operation completes**.

A design can initialize valid state yet allow external code to invalidate it:

~~~java
// Ví dụ CỐ Ý SAI để thấy lỗi thiết kế.
class BrokenSeatInventory {
    public int capacity;
    public int reserved;

    BrokenSeatInventory(int capacity) {
        this.capacity = capacity;
        this.reserved = 0;
    }

    int available() {
        return capacity - reserved;
    }
}

BrokenSeatInventory inventory = new BrokenSeatInventory(10);
inventory.reserved = 12; // Java cho phép: trường public.
System.out.println(inventory.available()); // -2
~~~

A single assignment valid for the **`int` type** has broken a business rule. The compiler cannot infer "`reserved` must not exceed `capacity`" from two `int` fields.

**The issue is more than "making a field `public`."** The deeper problem is that the object **cannot control every path through which its own state changes**. State can be modified directly through a field, through a getter returning a mutable collection, through an object passed to a constructor and later modified externally, or through setters that let related fields change independently.

## 2. What is an invariant, and how does it differ from validation?

Three concepts often appear together but answer different questions:

| Concept | Question | Seat-inventory example |
|---|---|---|
| **Precondition** | What must the caller supply for an operation to be valid? | `reserve(seats)` requires `seats > 0` |
| **Postcondition** | What must be true if the operation succeeds? | Successfully reserving 3 seats increases the reserved count by exactly 3 |
| **Invariant** | Which rule must hold at boundaries where state can be observed? | `0 ≤ reserved ≤ capacity` |

An invariant can involve **multiple fields**:

- Account: `balance >= 0` when overdrafts are prohibited by business policy.
- Inventory: `0 <= reserved <= stock`.
- Time interval: `start.isBefore(end)`.
- Order: `status == PAID` only after specific payment conditions are met.
- User group: ownership and membership must remain consistent with system rules.

Not every object needs complex invariants. For example, a DTO holding unverified input may deliberately contain invalid state so validation errors can be reported. In contrast, **domain objects** expected to represent valid state must preserve their rules across public operations.

### How far does "always true" extend?

A method may modify several fields in internal steps; an intermediate state **that is never exposed** may temporarily violate the invariant. Good designs still aim to make consistent updates and expose only valid state. In multithreaded programs, synchronization is also needed if threads read and write the same state.

Do not treat a promise to "call setters in the correct order" as invariant protection. API clients, subclasses, serializers, frameworks, or a future refactoring may invoke them in another order.

## 3. Why is `private` necessary but insufficient?

**Encapsulation** means more than changing `public` to `private`. It means an object **retains control over its state and enforces validity rules** when receiving requests for changes.

A sound design typically has three layers of protection:

1. **Hide state representation:** prevent clients from writing directly to important fields.
2. **Expose operations in domain language:** `reserve(3)` and `cancel(2)` rather than `setReserved(7)`.
3. **Protect all mutable reference paths:** constructors, getters, setters, collections, arrays, nested objects, and concurrent access.

The following table summarizes common mistakes:

| Approach | Risk | Remedy |
|---|---|---|
| `public int reserved` | Any client can assign an arbitrary value | Use `private` and guarded `reserve`/`cancel` methods |
| Separate `setReserved(x)` and `setCapacity(y)` | Can produce invalid combinations of state | Use a domain operation or update related data atomically |
| `getItems() { return items; }` | Exposes a reference to an internal mutable collection | Return a suitable snapshot/read-only view |
| `this.items = items` receiving an external `List` | Caller retains an alias and can later modify the data | Copy input data according to policy |
| `private final List<X> items` | `final` fixes the reference but does not prevent `add/remove` | Control mutations and prevent reference leaks |
| `record User(List<Role> roles)` | A record does not deep-copy its components automatically | Normalize/copy in the compact constructor |
| Validation on construction but not on updates | An initially valid object becomes invalid later | Enforce invariants in every mutator |

## 4. Complete Java 17 example: a seat inventory that preserves its invariant

Instead of exposing `capacity` and `reserved`, we create an object with encapsulated state:

- Capacity is set once in the constructor and never changes.
- Seats can only be reserved through `reserve(int seats)`.
- Reservations can only be canceled through `cancel(int seats)`.
- No API allows arbitrary assignments to the reserved-seat count.
- When too few seats remain, `reserve` returns `false` and **does not change state**.
- Operation seat counts must be positive; `cancel` cannot cancel more seats than have been reserved.

Create **`InvariantDemo.java`**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

// Một thiết kế lỗi để quan sát tác hại của public state.
final class BrokenSeatInventory {
    public int capacity;
    public int reserved;

    BrokenSeatInventory(int capacity) {
        this.capacity = capacity;
        this.reserved = 0;
    }

    int available() {
        return capacity - reserved;
    }
}

// Thiết kế có encapsulation và thao tác nghiệp vụ.
final class SeatInventory {
    private final int capacity;
    private int reserved;

    SeatInventory(int capacity) {
        if (capacity <= 0) {
            throw new IllegalArgumentException("capacity must be positive");
        }
        this.capacity = capacity;
        this.reserved = 0;
    }

    // synchronized làm cho toàn bộ kiểm tra + cập nhật là một critical section.
    synchronized boolean reserve(int seats) {
        requirePositive(seats);

        // Tránh reserved + seats gây overflow số nguyên.
        if (seats > capacity - reserved) {
            return false;
        }
        reserved += seats;
        return true;
    }

    synchronized void cancel(int seats) {
        requirePositive(seats);
        if (seats > reserved) {
            throw new IllegalArgumentException(
                    "cannot cancel more than reserved");
        }
        reserved -= seats;
    }

    synchronized int reserved() {
        return reserved;
    }

    synchronized int available() {
        return capacity - reserved;
    }

    int capacity() {
        return capacity;
    }

    private static void requirePositive(int seats) {
        if (seats <= 0) {
            throw new IllegalArgumentException("seats must be positive");
        }
    }
}

// Bảo vệ cả constructor và getter khỏi tham chiếu Set mutable bên ngoài.
final class PermissionSet {
    private final Set<String> permissions;

    PermissionSet(Set<String> input) {
        Objects.requireNonNull(input, "input");
        this.permissions = Set.copyOf(input);
    }

    Set<String> permissions() {
        return permissions; // Không sửa trực tiếp được.
    }

    boolean allows(String permission) {
        return permissions.contains(permission);
    }
}

public class InvariantDemo {
    public static void main(String[] args) {
        var broken = new BrokenSeatInventory(10);
        broken.reserved = 12;
        System.out.println("Broken available = " + broken.available());

        var seats = new SeatInventory(10);
        System.out.println("Reserve 4 = " + seats.reserve(4));
        System.out.println("Reserve 7 = " + seats.reserve(7));
        System.out.println("Available = " + seats.available());

        seats.cancel(2);
        System.out.println("Available after cancel = " + seats.available());

        Set<String> external = new HashSet<>(Set.of("READ"));
        PermissionSet policy = new PermissionSet(external);
        external.add("ADMIN"); // Thay đổi tập nguồn sau constructor.

        System.out.println("Policy has ADMIN = " + policy.allows("ADMIN"));

        try {
            policy.permissions().add("ADMIN");
        } catch (UnsupportedOperationException expected) {
            System.out.println("Permissions cannot be mutated externally");
        }
    }
}
~~~

Compile and run:

~~~bash
javac InvariantDemo.java
java InvariantDemo
~~~

Expected output:

~~~text
Broken available = -2
Reserve 4 = true
Reserve 7 = false
Available = 6
Available after cancel = 8
Policy has ADMIN = false
Permissions cannot be mutated externally
~~~

### Step-by-step state analysis

| Step | Operation | `reserved` | `available` | Invariant |
|---|---|---:|---:|---|
| Initialize | `new SeatInventory(10)` | 0 | 10 | Holds |
| Reserve 4 | `reserve(4)` returns `true` | 4 | 6 | Holds |
| Reserve 7 more | `reserve(7)` returns `false` | 4 | 6 | Holds; state unchanged |
| Cancel 2 | `cancel(2)` | 2 | 8 | Holds |
| Cancel 5 | `cancel(5)` throws an exception | 2 | 8 | Holds; state unchanged |

**Key point:** `SeatInventory` has no `setReserved` setter; it exposes only behaviors with **business meaning**. Its constructor establishes a valid initial state, and every valid public mutator preserves:

\[
0 \le \text{reserved} \le \text{capacity}
\]

This is an **inductive** argument:

1. **Base case:** after construction, `reserved = 0` and `capacity > 0`.
2. **Reservation step:** add only when `seats > 0` and `seats <= capacity - reserved`; capacity is therefore never exceeded.
3. **Cancellation step:** subtract only when `0 < seats <= reserved`; the result cannot become negative.
4. **Preservation:** if the state before an operation is valid, the state after a successful operation remains valid. Failure paths do not modify state.

This argument applies to the defined methods, assuming no code uses reflection/native access to alter fields illegally or bypasses the methods' synchronization. Under normal Java access rules, private access prevents direct assignment by clients.

### Why use `synchronized`?

If two threads both read `reserved = 4` and each tries to reserve 4 seats, the "check then add" action must be treated as **one unit**. Without synchronization, both might observe enough capacity and return `true`, while the stored result and actual bookings become inconsistent.

Using `synchronized` on `reserve`, `cancel`, and reads makes them use the same object monitor, establishing suitable happens-before relationships within the class. This demonstrates concurrency control **in the memory of one JVM**. If seats are stored in a database and multiple application instances run, transactions, optimistic locking, or conditional atomic updates are still needed at the storage layer. Adding `synchronized` to one service instance cannot eliminate races across nodes.

## 5. A subtle bug: a private field that returns the original collection

Consider a shopping cart:

~~~java
import java.util.ArrayList;
import java.util.List;

class LeakyCart {
    private final List<String> items = new ArrayList<>();

    LeakyCart() {
        items.add("SKU-1");
    }

    public List<String> getItems() {
        return items; // RÒ RỈ live mutable reference.
    }
}

LeakyCart cart = new LeakyCart();
cart.getItems().clear(); // Xóa trạng thái nội bộ từ ngoài class!
~~~

Making `items` a `private final` field **does not fix the issue**: `final` prevents the `List` reference from being reassigned, but does not stop its contents from changing.

One fix, when elements are immutable `String` values:

~~~java
final class SafeCart {
    private final List<String> items = new ArrayList<>();

    SafeCart() {
        items.add("SKU-1");
    }

    void addItem(String sku) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("Invalid SKU");
        }
        items.add(sku);
    }

    List<String> itemsSnapshot() {
        return List.copyOf(items);
    }
}
~~~

Now the following code cannot modify the cart through the snapshot:

~~~java
SafeCart cart = new SafeCart();
List<String> readOnly = cart.itemsSnapshot();

// readOnly.add("SKU-2"); // Biên dịch được, nhưng runtime
// ném UnsupportedOperationException vì snapshot không sửa được.

cart.addItem("SKU-2");
System.out.println(readOnly);          // Vẫn chỉ [SKU-1].
System.out.println(cart.itemsSnapshot()); // [SKU-1, SKU-2].
~~~

A snapshot also clearly distinguishes **a copy captured at call time** from **a view that changes along with its source**. If the API truly needs a live view, its timing and concurrency contract should be explicit, rather than exposing an arbitrary mutable reference.

## 6. Defensive copying in constructors: preventing mutations through aliases

A class can leak state through an externally supplied object even without exposing a getter:

~~~java
import java.util.List;

class BrokenTeam {
    private final List<String> members;

    BrokenTeam(List<String> members) {
        this.members = members; // Giữ alias do client sở hữu.
    }

    int size() {
        return members.size();
    }
}
~~~

The client still holds a reference:

~~~java
List<String> external = new java.util.ArrayList<>(
        List.of("Lan", "Minh"));

BrokenTeam team = new BrokenTeam(external);
external.clear();

System.out.println(team.size()); // 0, dù Team không có mutator.
~~~

If the invariant is "a team must have at least one member," checking `!members.isEmpty()` in the constructor **does not guarantee it later**. We must copy the input structure and retain only a representation that cannot be modified:

~~~java
final class Team {
    private final List<String> members;

    Team(List<String> members) {
        java.util.Objects.requireNonNull(members);
        if (members.isEmpty()) {
            throw new IllegalArgumentException("Team must be nonempty");
        }

        // List.copyOf từ chối phần tử null và snapshot cấu trúc danh sách.
        this.members = List.copyOf(members);

        for (String name : this.members) {
            if (name.isBlank()) {
                throw new IllegalArgumentException("Blank member");
            }
        }
    }

    List<String> members() {
        return members; // Danh sách không thể sửa; String là immutable.
    }

    int size() {
        return members.size();
    }
}
~~~

In this `Team`, both the constructor and getter protect the invariant based on **list structure and immutable String values**. If elements are mutable objects, `List.copyOf` **is not a deep copy**: those objects may still be modified through other aliases.

### The `Collections.unmodifiableList` pitfall

~~~java
List<String> external = new java.util.ArrayList<>(List.of("A"));
List<String> view = java.util.Collections.unmodifiableList(external);

external.add("B");
System.out.println(view); // [A, B]
~~~

`unmodifiableList` prevents mutation **through the view** but does not prevent the original list's owner from changing it. In contrast, `List.copyOf(external)` creates a structural snapshot (for a suitable collection), so later `add/remove` operations on `external` do not modify the snapshot.

| Protection method | Prevent mutation through returned value? | Independent of source collection changes? | Prevent mutation of mutable element objects? |
|---|---|---|---|
| Return `items` directly | No | No | No |
| `Collections.unmodifiableList(items)` | Yes | No, this is a view | No |
| `List.copyOf(items)` | Yes | Yes, for structural changes in the source | No |
| Controlled deep copy | Depends on the API | Yes | Yes, if all relevant mutable elements are copied correctly |

**Therefore:** `private + final + getter` does not by itself prove an object is safely encapsulated. Draw the **reference graph** and check who can still mutate which objects.

## 7. How subclasses, records, and getters/setters can break invariants in other ways

### 7.1. Independent setters break rules involving multiple fields

Consider a booking window with `start < end`:

~~~java
import java.time.Instant;

class MutableWindow {
    private Instant start;
    private Instant end;

    MutableWindow(Instant start, Instant end) {
        setStart(start);
        setEnd(end);
    }

    void setStart(Instant start) {
        this.start = start;
    }

    void setEnd(Instant end) {
        this.end = end;
    }
}
~~~

The constructor calls setters without validating the relationship. Even with validation in each setter, changing a valid interval from `10:00–11:00` to `12:00–13:00` by calling `setStart(12:00)` first could create an invalid intermediate state. With strict checks and an exception, the client may **be unable to update in the desired order**, even though the intended final state is valid.

Instead of two setters, provide an operation that updates both fields together, validating before assignment:

~~~java
import java.time.Instant;
import java.util.Objects;

final class BookingWindow {
    private Instant start;
    private Instant end;

    BookingWindow(Instant start, Instant end) {
        replace(start, end);
    }

    synchronized void replace(Instant nextStart, Instant nextEnd) {
        Objects.requireNonNull(nextStart, "start");
        Objects.requireNonNull(nextEnd, "end");

        if (!nextStart.isBefore(nextEnd)) {
            throw new IllegalArgumentException("start must be before end");
        }

        // Chỉ sửa state sau khi đã kiểm tra cặp giá trị mới.
        this.start = nextStart;
        this.end = nextEnd;
    }

    synchronized boolean contains(Instant point) {
        Objects.requireNonNull(point);
        return !point.isBefore(start) && point.isBefore(end);
    }
}
~~~

`BookingWindow` in the demo keeps two mutable fields to teach paired updates. For a value object that does not need to change after construction, an **immutable** design is simpler:

~~~java
import java.time.Instant;
import java.util.Objects;

record ImmutableWindow(Instant start, Instant end) {
    ImmutableWindow {
        Objects.requireNonNull(start);
        Objects.requireNonNull(end);
        if (!start.isBefore(end)) {
            throw new IllegalArgumentException("Invalid interval");
        }
    }
}

// Thay đổi => tạo một ImmutableWindow mới hợp lệ.
~~~

### 7.2. Records do not guarantee deep immutability

~~~java
record AccountRoles(java.util.List<String> roles) {}

var external = new java.util.ArrayList<>(java.util.List.of("READ"));
var roles = new AccountRoles(external);
external.add("ADMIN");

System.out.println(roles.roles()); // [READ, ADMIN]
~~~

A `record` generates a constructor, accessors, `equals`, and `toString` based on its components, but does not automatically copy a mutable `List`. To retain a snapshot:

~~~java
record SafeAccountRoles(java.util.List<String> roles) {
    SafeAccountRoles {
        roles = java.util.List.copyOf(
                java.util.Objects.requireNonNull(roles));
    }
}
~~~

In a compact constructor, assigning `roles = ...` replaces the parameter used to initialize the record field; with immutable `String` elements, this is a reasonable safeguard.

### 7.3. Inheritance opens additional mutation paths

If the superclass has a mutable `protected` field:

~~~java
class InventoryBase {
    protected int reserved; // Lớp con có thể sửa mà không qua validation.
}
~~~

A subclass can directly increment or decrement it and violate the superclass's invariant. If a class owns a strict invariant, use `private` state, controlled mutation methods, and consider a `final class` or an inheritance API with a clear contract. **`protected` does not mean "usable only inside this class."**

An overridden method called during construction can also observe a subclass whose state is not fully initialized. Avoid calling overridable methods from constructors before subclass invariants are established.

## 8. State-control flow diagram

~~~mermaid
flowchart TD
    Client["Client"] --> Request["reserve(3)"]
    Request --> Preconditions{"seats > 0?"}
    Preconditions -->|Không| Reject["Ném IllegalArgumentException<br/>Không đổi state"]
    Preconditions -->|Có| Capacity{"seats <= capacity - reserved?"}
    Capacity -->|Không| NoChange["Trả false<br/>Giữ nguyên state"]
    Capacity -->|Có| Mutate["reserved += seats"]
    Mutate --> Done["Trả true<br/>Invariant được bảo toàn"]
~~~

The diagram shows the correct boundary: **the client sends a request** rather than writing `reserved` directly. Only the object owning the state decides whether a change is allowed.

When an operation spans multiple aggregates or a database, invariants must be considered at two levels:

- **Invariant within one object/aggregate:** can be enforced using the API, private state, and suitable synchronization.
- **Invariant across multiple records or systems:** typically needs transactions, optimistic locking, unique constraints, an outbox, idempotency, or other consistency mechanisms.

Java encapsulation does not replace database constraints. For example, "never sell more tickets than exist" must still hold when two application nodes reserve seats in the same database.

## 9. Testing invariants: include failure paths and alternate mutation paths

A test that only checks `reserve(4)` returning `true` does not establish that an object is safe. Also check **unchanged state after rejected requests**, indirect mutation paths, and boundary conditions.

The following tests use JUnit Jupiter (JUnit 5) in the same package as **`InvariantDemo.java`**:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.HashSet;
import java.util.Set;
import org.junit.jupiter.api.Test;

class InvariantDemoTest {
    @Test
    void reservationCannotExceedCapacity() {
        SeatInventory inventory = new SeatInventory(10);

        assertTrue(inventory.reserve(4));
        assertFalse(inventory.reserve(7));

        assertEquals(4, inventory.reserved());
        assertEquals(6, inventory.available());
    }

    @Test
    void invalidCancelDoesNotChangeState() {
        SeatInventory inventory = new SeatInventory(10);
        assertTrue(inventory.reserve(3));

        assertThrows(IllegalArgumentException.class,
                () -> inventory.cancel(4));

        assertEquals(3, inventory.reserved());
        assertEquals(7, inventory.available());
    }

    @Test
    void invalidInitialAndOperationArgumentsAreRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> new SeatInventory(0));

        SeatInventory inventory = new SeatInventory(2);
        assertThrows(IllegalArgumentException.class,
                () -> inventory.reserve(0));
        assertThrows(IllegalArgumentException.class,
                () -> inventory.cancel(-1));

        assertEquals(2, inventory.available());
    }

    @Test
    void originalCollectionCannotMutatePermissionSnapshot() {
        Set<String> source = new HashSet<>(Set.of("READ"));
        PermissionSet policy = new PermissionSet(source);

        source.add("ADMIN");
        assertFalse(policy.allows("ADMIN"));

        assertThrows(UnsupportedOperationException.class,
                () -> policy.permissions().add("ADMIN"));
        assertFalse(policy.allows("ADMIN"));
    }
}
~~~

For generic collections, add tests with **mutable object** elements, not only strings. For `BookingWindow`, test replacing the interval with another valid interval and an invalid one, confirming that the old fields remain unchanged after an exception.

**Test concurrency boundaries too, when required:** let multiple threads reserve seats, but do not rely on a few executions to "prove thread safety." Synchronize tests with latches, use stress tests or specialized race-detection tools, and verify transactions at the persistence layer.

### A dedicated test for atomic updates

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import org.junit.jupiter.api.Test;

class BookingWindowTest {
    @Test
    void invalidReplacementLeavesPreviousIntervalIntact() {
        Instant ten = Instant.parse("2026-10-15T10:00:00Z");
        Instant eleven = Instant.parse("2026-10-15T11:00:00Z");
        Instant twelve = Instant.parse("2026-10-15T12:00:00Z");

        BookingWindow window = new BookingWindow(ten, eleven);

        assertThrows(IllegalArgumentException.class,
                () -> window.replace(twelve, eleven));

        assertTrue(window.contains(ten));
        assertFalse(window.contains(twelve));
    }
}
~~~

This test also verifies the **postcondition on failure**: a rejected update must not leave state half-modified. Note that `Instant` contains no local time zone, while `Z` denotes UTC; the date-time values are sample data only.

## 10. Distinguishing invariants, immutability, and thread safety

These three properties reinforce each other but **are not equivalent**:

| Property | Meaning | Example |
|---|---|---|
| **Invariant** | State rule that must hold | `0 <= reserved <= capacity` |
| **Encapsulation** | Controls who can read/write and through which API | `reserved` is private and changes through `reserve` |
| **Immutability** | Observable state never changes after construction | `ImmutableWindow` with two `Instant` values |
| **Thread safety** | Correct behavior under concurrent use, according to the contract | `SeatInventory` protects both checks and updates with `synchronized` |

A mutable object can always preserve its invariant; `SeatInventory` is an example. An immutable object created with invalid data can **violate an invariant forever** if its constructor does not validate. And a class whose methods preserve invariants when called sequentially can still encounter race conditions when invoked concurrently without protection.

`private` is a mechanism for **hiding data from external code**, not for synchronizing memory. Applying `final` to a reference can support immutability, but does not make a mutable collection immutable.

## 11. When are getters/setters appropriate, and when should domain behavior be used?

Not every setter is bad. For DTOs, JavaBeans, form binding, or configuration, getters/setters may be practical. But when an object **owns invariants or business behavior**, a setter that accepts anything is often a signal to reconsider the API.

| Model | Typically appropriate API | Notes |
|---|---|---|
| Unvalidated input DTO | Fields/bean properties as required by the framework | Validate at the boundary before creating a domain object |
| Domain entity with state rules | `pay()`, `cancel()`, `reserve(n)` | Operations express business intent and preserve invariants |
| Value object | Constructor/factory validation, no mutator | A new value usually means a new object |
| Internal collection | `addItem`, `removeItem`, snapshot | Do not expose the original mutable collection |
| Field pair that must change together | `replaceWindow(start,end)` | Validate the combination before exposing state |

Before adding `setStatus(String status)` to an entity, ask **which state transitions are actually valid?** For example, an order in `PAID` state cannot arbitrarily return to `CREATED` merely because a setter accepts that string.

## 12. Code-review checklist: identify every path that could break an invariant

When reviewing a class with state, check these points in order:

1. **Express the invariant as a concrete statement or formula.** Without defining "valid state," it is hard to protect it.
2. **Constructor/factory:** Does it reject invalid values? Does it copy mutable objects supplied by the caller?
3. **Fields:** Are mutable fields `public`/`protected`? Does `final` apply only to the reference or to the entire value?
4. **Getter:** Does it return an internal collection, array, `Date`, or other mutable object?
5. **Setter/mutator:** Can changing one field contradict another? Does it validate *before* assignment?
6. **Method override:** Can subclasses bypass validation or access state through another path?
7. **Serialization/ORM/framework:** Can a framework instantiate or restore objects via reflection or persistence mapping? If so, apply validation at appropriate boundaries/hooks without violating framework contracts.
8. **Concurrency:** Can multiple threads access one instance? If so, examine check-then-act, memory visibility, and atomicity.
9. **Across systems:** Does the invariant depend on a DB, cache, or another service? Put constraints and consistency mechanisms at the right layer.
10. **Tests:** Do they cover state preservation on failure, alias-based mutations, mutable elements, and boundary states?

### Do not "fix" it by making every field private and stripping away all behavior

Merely replacing public fields with getters and setters that wrap those fields:

~~~java
class WeakInventory {
    private int reserved;

    void setReserved(int value) {
        this.reserved = value; // Không có quy tắc nào được bảo vệ.
    }

    int getReserved() {
        return reserved;
    }
}
~~~

still allows values such as `-50` or `1_000_000`. Instead, define **valid state** and **allowed operations**. Encapsulation does not mean "every field has a getter/setter"; it means **keeping decisions about invariants inside the object itself**.

## 13. Practice exercise: stock quantities and reservations

Design a `StockItem` class with:

- `sku` as a nonblank ID string that never changes after construction.
- `onHand` as the nonnegative quantity of stock available.
- `reserved` as a nonnegative quantity held for orders, never exceeding `onHand`.
- No publicly exposed mutable fields.
- Methods `reserve(n)`, `release(n)`, `receive(n)`, and `shipReserved(n)`.

**State requirements:**

\[
0 \le \text{reserved} \le \text{onHand}
\]

`shipReserved(n)` must decrease **both** `reserved` and `onHand` after validating the request; it must not update one field and then fail on the other. `receive(n)` increases stock on hand and must handle integer overflow when using `int` (for example, with `Math.addExact` or prior validation). `reserve(n)` must not reserve more than the available quantity `onHand - reserved`.

Write unit tests for at least:

- Reject construction with `onHand < 0`.
- Reject reservations exceeding available stock without changing state.
- Shipping reserved stock updates both counts correctly.
- Shipping more than reserved changes no fields.
- Two concurrent reservations cannot both consume the final unit in a shared inventory.
- If inventory is stored in a DB, describe how to enforce the invariant across application nodes.

### Self-check questions

1. Why does compiling `inventory.reserved = 12` not prove that the resulting state is valid?
2. How does the precondition `seats > 0` differ from the invariant `reserved <= capacity`?
3. Why can `private final List<?>` still be modified externally?
4. How does `Collections.unmodifiableList(source)` differ from `List.copyOf(source)`?
5. If `List.copyOf` contains mutable object elements, is the object deeply immutable?
6. Why can the two setters `setStart` and `setEnd` create an invalid intermediate state?
7. When can a record still leak a mutable reference?
8. Does `synchronized` on one Java object protect ticket inventory across JVMs?
9. For a domain entity, when is `reserve(n)` better than `setReserved(n)`?

**Conclusion:** **An invariant is a promise that an object's published APIs cannot put it into a contradictory state.** Keeping this promise takes more than hiding fields: control **every mutation path and mutable reference**, including constructors, getters, mutators, subclasses, and concurrency. Design operations around business intent, validate before updating, protect aliases, and test that both successes and failures leave the object in a valid state.
