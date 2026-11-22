# Designing Business Operations to Preserve Validity Rules in Java

> **Module:** Java Core – class/object  
> **Group:** Design and Practice  
> **Topic:** Designing Business Operations to Preserve Validity Rules  
> **Platform:** Java 17+, examples do not use preview features or special frameworks.

## 1. The Design Problem: Objects Must Always Be in a Valid State

In object-oriented programming, a class needs to do more than just store data fields. A good class must protect **state rules (invariants)** throughout the object's lifecycle.

For example, an account must not have a negative balance. If the class allows external code to call `setBalance(-100)`, the rule exists only in documentation and is not protected by code. If a shipped order still allows modifying the product list, the order state can become inconsistent with the invoice and receipt.

The goals of designing business operations are:

1. Represent **the exact actions that are meaningful in the business domain**: `deposit`, `withdraw`, `pay`, `ship`, `reserveStock`, `enroll` instead of a set of unconditional `setX` methods.
2. Place **condition checks** where the state is owned, not only in the form/controller.
3. Ensure the object starts in a valid state and **each successful operation moves the object to the next valid state**.
4. When an operation fails, avoid leaving behind a **partially modified state**.
5. Do not expose collections or mutable references for other code to modify while bypassing checks.
6. Clearly define the **scope of atomicity**: a single object, multiple objects, multiple threads, a database, or a distributed system.
7. Design the API so that invalid states are **hard to represent and hard to create accidentally**.

Key takeaway: **encapsulation is not just about making fields `private`; encapsulation is also about placing validity rules and state-changing operations within the same trusted boundary**.

## 2. Concepts to Distinguish

| Concept | Question It Answers | Example |
| --- | --- | --- |
| Invariant (business invariant) | What must always be true across observable states? | `balance >= 0` |
| Precondition | What must be true before the operation is allowed? | Withdrawal requires `amount > 0` and sufficient balance |
| Postcondition | After the operation succeeds, what is true? | The balance decreases by the exact withdrawal amount |
| State transition | From which state to which state can the object transition? | `PAID → SHIPPED` |
| Encapsulation boundary | Who is allowed to modify the data? | Only `Order.ship()` changes the shipping state |
| Aggregate boundary | Which group of objects must remain consistent together? | An order and its line items managed by Order |
| Failure atomicity | On failure, are partial updates left behind? | Keep inventory unchanged if one SKU is short |
| Defensive copy | Can the caller modify internal data through an alias? | Return `List.copyOf(items)` |
| Concurrency invariant | Can multiple threads break a rule even if each method is correct single-threaded? | Two withdrawals against the same balance |
| Persistence transaction | Which database changes must commit or roll back together? | Deducting inventory and creating the order |

An **invariant** must be stated in a way that can be verified. “A reasonable account” is too vague; “a non-negative balance and a withdrawal amount greater than 0” is a condition that can be coded and tested.

### 2.1. An Invariant Does Not Mean Data Never Changes

A balance can increase/decrease, available seats can change, and an order status can transition forward. “Invariant” means **a condition that holds true across all valid states**, not an immutable object.

### 2.2. Distinguishing Invariants from Context-Dependent Rules

That an invoice must have a non-negative total is a relatively stable internal invariant. A promotion like “10% off on Fridays” is a time-dependent policy; it can come from a service/policy object. Do not cram every fluctuating rule into an entity's setter.

### 2.3. Validation in the Constructor Is Not Enough

A constructor can validate the initial balance, yet `setBalance(-5)` still allows corrupting the state afterward. You must consider **every mutation path**: methods, exposed mutable lists, reflection/frameworks, deserialization, concurrency, and collaborators.

## 3. Weak Design: Allowing Arbitrary Setters

~~~java
class Account {
    private long balanceCents;

    Account(long balanceCents) {
        this.balanceCents = balanceCents;
    }

    long getBalanceCents() {
        return balanceCents;
    }

    void setBalanceCents(long balanceCents) {
        this.balanceCents = balanceCents;
    }
}
~~~

This is a **fragment illustrating a flawed design**. A caller can do:

~~~java
Account account = new Account(1000);
account.setBalanceCents(-500);
~~~

There is no domain operation explaining why the balance became negative, or whether the business allows an overdraft. If every call site checks before calling the setter, each place may forget or use different conditions.

### 3.1. “Letting the Controller Validate Is Enough” Does Not Work

A REST controller, scheduled job, import script, test fixture, or a future API might all call the entity. If the invariant lives only in a controller, another code path can break it.

The controller should still validate input errors to provide user-friendly messages. However, **core domain rules must still be enforced in the object/service that owns the state**.

### 3.2. The Problem with CRUD-Centric APIs

An API with `getStatus/setStatus` allows transitioning directly from `DRAFT → SHIPPED` while skipping payment, logging no domain events, and without checking the line items. To fix this, replace them with methods expressing behavior: `pay()`, `ship()`, `cancel()` with validation guards.

### 3.3. Not Every Setter Is Bad

A pure configuration object or DTO can use setters according to its contract. For state carrying business rules, what matters is **not letting a setter open a path to creating invalid states**. A setter with strict validation can still be valid when it is itself a meaningful business operation, though the method name usually needs to express the business intent more clearly.

## 4. Writing Invariants as Formulas and Test Cases

For an account that does not allow overdrawing into negative balance:

- `balanceCents >= 0` is always true after creation and after every public operation.
- `deposit(amount)` requires `amount > 0` and no overflow.
- `withdraw(amount)` requires `amount > 0`, `amount <= balanceCents`.
- Successful deposit: `newBalance = oldBalance + amount`.
- Successful withdrawal: `newBalance = oldBalance - amount`.
- If the argument is invalid or the balance is insufficient, **the balance remains unchanged**.

One way to present this using Hoare-style reasoning:

~~~text
Before withdraw:
  balance >= 0
  amount > 0
  amount <= balance

Operation:
  balance = balance - amount

After withdraw:
  balance >= 0
  balance_new = balance_old - amount
~~~

### 4.1. Start with Small, Strong Invariants

For a small class, a few clear conditions may be enough. Do not write “the object is always consistent” without defining what consistent includes.

### 4.2. Mark All State-Mutation Points

Find every assignment to state fields, mutations of collections, and calls to mutable collaborators. Every mutation point must go through a valid check/commit flow.

### 4.3. Categorize Input Errors

Some errors are **precondition violations**: negative amount, empty ID, end time before start time. Others are **business rejections**: insufficient balance, out of stock, an order cannot be shipped in the DRAFT state. The API can use distinct exceptions or a result type, but it must help the caller distinguish the cause well enough to handle it.

## 5. Complete Program 1 — Preserving Reservation Limits with Conditional Operations

To focus on **designing invariant-protecting operations** rather than rewriting the BankAccount exercise, consider a pool of seats with a fixed total capacity. The business rules are:

- `capacity > 0` right from creation.
- `0 <= reserved <= capacity` in every observable state.
- `reserve(n)` accepts only `n > 0` when enough seats remain.
- `release(n)` accepts only `n > 0` and `n <= reserved`.
- A rejected command must **not change** the number of reserved seats.

Create the file **`SeatReservationDemo.java`**:

~~~java
public class SeatReservationDemo {
    static final class SeatPool {
        private final int capacity;
        private int reserved;

        SeatPool(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException(
                        "capacity must be positive");
            }
            this.capacity = capacity;
        }

        void reserve(int count) {
            requirePositive(count);
            if (count > capacity - reserved) {
                throw new IllegalStateException(
                        "insufficient seats");
            }
            reserved += count;
        }

        void release(int count) {
            requirePositive(count);
            if (count > reserved) {
                throw new IllegalStateException(
                        "not reserved");
            }
            reserved -= count;
        }

        int reserved() {
            return reserved;
        }

        int available() {
            return capacity - reserved;
        }

        private static void requirePositive(int count) {
            if (count <= 0) {
                throw new IllegalArgumentException(
                        "count must be positive");
            }
        }
    }

    public static void main(String[] args) {
        SeatPool seats = new SeatPool(4);
        seats.reserve(2);
        seats.reserve(1);
        System.out.println("reserved=" + seats.reserved());

        try {
            seats.reserve(2);
        } catch (IllegalStateException ex) {
            System.out.println("reserve rejected="
                    + ex.getMessage());
        }

        try {
            seats.release(4);
        } catch (IllegalStateException ex) {
            System.out.println("release rejected="
                    + ex.getMessage());
        }

        seats.release(1);
        System.out.println("after release=" + seats.reserved());
        System.out.println("available=" + seats.available());
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 SeatReservationDemo.java
java SeatReservationDemo
~~~

Expected stdout:

~~~text
reserved=3
reserve rejected=insufficient seats
release rejected=not reserved
after release=2
available=2
~~~

### 5.1. Why Is This a Business API Instead of a Setter?

If `setReserved(int)` were provided, a caller could set `reserved = -1` or greater than capacity. `reserve` and `release` represent **actions**, not just field assignments, and validate both the new request and the current state.

### 5.2. Check First — Commit Afterward

The condition `count > capacity - reserved` uses a non-negative difference to check whether enough seats remain; only after passing the guard does it add `reserved += count`. Similarly, `release` checks first and subtracts afterward. Because the result after each operation is bounded within `[0, capacity]`, addition overflow cannot occur within the scope of this invariant.

### 5.3. Safety Scope of This Example

The operations above are **not thread-safe** if multiple threads call the same `SeatPool` concurrently. A real-world reservation application must protect the read–check–write sequence with synchronization, DB constraints/transactions, or an appropriate mechanism. `capacity` is a `final` field, whereas `reserved` is mutable; `final` does not solve concurrency on its own.

The lesson **“Building an Account Class with Creation, Deposit, and Withdrawal”** applies this exact mindset of *valid commands and unchanged state on failure* to an account exercise with money representation, overflow handling, and dedicated tests.

## 6. Constructors/Factories Are the “Gateway” to a Valid State

A class with invariants must not allow creating an invalid object right from the start.

~~~java
record Quantity(int units) {
    Quantity {
        if (units <= 0) {
            throw new IllegalArgumentException("units must be positive");
        }
    }
}
~~~

This is a **record fragment**. Every way of creating `new Quantity(n)` via the canonical constructor must go through this validation.

### 6.1. A Constructor Should Not Merely Assign Fields

A constructor is responsible for establishing invariants such as non-null fields, valid ranges, and sensible relationships across multiple fields. If a new object is already invalid, no method can be certain that the baseline state is correct.

### 6.2. Static Factories Help Express Business Names

~~~java
static Order draftFor(CustomerId customerId) { ... }
static Money zero(String currency) { ... }
~~~

These are **conceptual signatures**. Factory names help explain the initial state; however, validation must still live in the trusted constructor/factory path, avoiding parallel APIs that bypass validation.

### 6.3. Do Not Expose a “Half-Initialized” Object

Avoid publishing `this` from a constructor via a listener/registry/thread before fields and invariants are established. Even if the fields end up correct, an object observed too early can encounter an intermediate state.

### 6.4. Do Not Use a Constructor Just to Execute a Long Workflow

Creating a domain object is different from calling a payment gateway, making a network request, or running a database transaction. An application service may be needed to orchestrate external I/O, after which the domain object records the result through a guarded method.

## 7. State Machine: States Must Transition Along Valid Edges

An order can be modeled as:

~~~text
DRAFT --pay--> PAID --ship--> SHIPPED
  |
  +--cancel--> CANCELLED

PAID --cancel--> CANCELLED
~~~

The transitions above are only **one example policy**. Another domain might require a refund before cancellation or disallow cancellation after payment.

Invariants of the example:

- Only an order in `DRAFT` may have products added.
- Only a DRAFT order **with at least one line item** may be paid.
- Only a PAID order may be shipped.
- `SHIPPED` and `CANCELLED` cannot modify items and cannot automatically “revert” to DRAFT.
- Payment/shipping/cancellation in an invalid state must be rejected **without changing state**.
- The total amount is derived from the lines; there is no independent public setter for the total.

### 7.1. Why Is an Enum a Good Fit for State?

An enum has a finite set of constants; switches/guards represent the edges. However, an enum by itself only defines state names and **does not automatically prevent invalid assignments** if the entity still allows an arbitrary `setStatus`.

### 7.2. Place Transitions in the Object That Owns the State

`Order.pay()` understands the items and current status; `Order.ship()` understands the current state. The controller only requests the action and does not directly modify the status field.

## 8. Complete Program 2 — An Order That Allows Only Valid Transitions

File **`OrderWorkflowDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class OrderWorkflowDemo {
    enum Status {
        DRAFT, PAID, SHIPPED, CANCELLED
    }

    record Line(String sku, int quantity, long unitPriceCents) {
        Line {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("empty SKU");
            }
            if (quantity <= 0 || unitPriceCents < 0) {
                throw new IllegalArgumentException("invalid line");
            }
        }

        long amountCents() {
            return Math.multiplyExact(quantity, unitPriceCents);
        }
    }

    static final class Order {
        private Status status = Status.DRAFT;
        private final List<Line> lines = new ArrayList<>();

        Status status() {
            return status;
        }

        List<Line> lines() {
            return List.copyOf(lines);
        }

        void addLine(Line line) {
            requireStatus(Status.DRAFT);
            if (line == null) {
                throw new IllegalArgumentException("null line");
            }
            lines.add(line);
        }

        long totalCents() {
            long sum = 0;
            for (Line line : lines) {
                sum = Math.addExact(sum, line.amountCents());
            }
            return sum;
        }

        void pay() {
            requireStatus(Status.DRAFT);
            if (lines.isEmpty()) {
                throw new IllegalStateException("empty order");
            }
            totalCents(); // Check arithmetic before changing state.
            status = Status.PAID;
        }

        void ship() {
            requireStatus(Status.PAID);
            status = Status.SHIPPED;
        }

        void cancel() {
            if (status != Status.DRAFT && status != Status.PAID) {
                throw new IllegalStateException("cannot cancel");
            }
            status = Status.CANCELLED;
        }

        private void requireStatus(Status expected) {
            if (status != expected) {
                throw new IllegalStateException(
                        "expected " + expected + ", was " + status);
            }
        }
    }

    public static void main(String[] args) {
        Order order = new Order();

        try {
            order.ship();
        } catch (IllegalStateException ex) {
            System.out.println("Early ship = " + ex.getMessage());
        }

        order.addLine(new Line("BOOK", 2, 500));
        System.out.println("Total = " + order.totalCents());

        order.pay();
        System.out.println("After payment = " + order.status());

        order.ship();
        System.out.println("After shipping = " + order.status());

        try {
            order.addLine(new Line("PEN", 1, 100));
        } catch (IllegalStateException ex) {
            System.out.println("Late edit = " + ex.getMessage());
        }

        System.out.println("Lines = " + order.lines().size());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 OrderWorkflowDemo.java
java OrderWorkflowDemo
~~~

**Exact stdout:**

~~~text
Early ship = expected PAID, was DRAFT
Total = 1000
After payment = PAID
After shipping = SHIPPED
Late edit = expected DRAFT, was SHIPPED
Lines = 1
~~~

### 8.1. No Public `setStatus`

The transitions are encapsulated inside `pay`/`ship`/`cancel` with appropriate guards. A screen cannot transition directly from DRAFT to SHIPPED just by using a setter.

### 8.2. `lines()` Returns an Immutable Snapshot

`List.copyOf(lines)` returns an unmodifiable List. The caller cannot directly add items to the internal ArrayList and bypass `addLine`. The Line entries are immutable records with primitive/String components, so no mutable element leak occurs in the demo.

### 8.3. Do Not Separate Total into an Independently Set Field

If you have both lines and `setTotal`, it is very easy for the two values to contradict each other. `totalCents()` computes the sum from the lines. If total must be cached for performance, every mutation must update both fields as an invariant and have tests ensuring consistency.

### 8.4. Payment Simplification

In the demo, `pay()` only changes internal state after the guards and **does not call a bank or payment gateway**. In a real system, payment success must be confirmed by an external system, managing idempotency and transaction/outbox patterns. Do not equate “changing status=PAID” with having collected the money.

## 9. Do Not Expose Mutable Collections: A Common Encapsulation Leak

A getter can be a backdoor that breaks an invariant:

~~~java
class Team {
    private final List<Member> members = new ArrayList<>();

    public List<Member> getMembers() {
        return members; // Leaks a mutable reference.
    }
}
~~~

If the rule is that a team has at most 5 members, a caller can call `team.getMembers().add(member)` dozens of times without going through the limit check.

### 9.1. Safe Options

- Return a snapshot `List.copyOf(members)` if elements are immutable/handled with proper ownership.
- Return an unmodifiable **view** when a live view is genuinely desired and concurrent modifications can be controlled; understand that the view changes with the source list and does not protect mutable elements.
- Return a DTO/summary instead of exposing the internal aggregate.
- Provide only business methods such as `addMember`/`removeMember` with guards.

### 9.2. An Unmodifiable Wrapper Is Not Synonymous with a Snapshot

`Collections.unmodifiableList(internal)` prevents the caller from modifying the list through the wrapper, but when the owner modifies `internal`, the view reflects the change. `List.copyOf(internal)` creates an unmodifiable list from the current elements (which may reuse a suitable immutable source) and preserves snapshot structure by contract.

### 9.3. Mutable Elements Are Still Dangerous

`List.copyOf` only handles the List structure. If the List contains `MutableMember` with a public `setRole`, a caller can still mutate the elements. You need immutable element types, appropriate deep defensive copies, or to expose only read-only projections.

## 10. Designing “All-or-Nothing” Operations Across Multiple Fields

For example, an inventory needs to preserve these rules:

- Stock for each SKU is always `>= 0`.
- Reservation must require a positive quantity.
- If any SKU is short, **deduct no SKUs**.
- No public setters for quantity so a caller cannot silently set -99.

A flawed implementation:

~~~java
for (RequestLine request : requestLines) {
    stock.put(request.sku(), stock.get(request.sku()) - request.qty());
    if (stock.get(request.sku()) < 0) {
        throw new IllegalStateException("not enough");
    }
}
~~~

This is an **anti-pattern fragment**. It mutates before validating. If the second SKU is short, the first SKU has already been deducted; the object falls into a partially updated state.

### 10.1. Prepare First, Commit Later

A safer design in a single-threaded context:

1. Validate the entire request input: SKU, qty, duplicates.
2. Build a `proposed` map or copy of the state.
3. Verify sufficient stock for all entries.
4. Only when all guards pass, commit the changes to state.
5. Report a sufficiently meaningful error to the caller.

### 10.2. Validate All Input Before Mutation

If an operation processes 10 products, an error on the 10th product must not cause the previous 9 products to be deducted if the contract declares atomicity.

### 10.3. “Prepare-Then-Commit” Does Not Automatically Solve Threads/Database

If another thread can modify stock after the validation step but before commit, the operation still has a race. It must be combined with a lock, immutable state replacement/atomic CAS, or a database transaction depending on the boundary. The initial demo is intentionally single-threaded; a later section includes a lock example.

## 11. Complete Program 3 — Preserving Valid Inventory When Reserving Multiple SKUs

File **`InventoryReservationDemo.java`**:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeMap;

public class InventoryReservationDemo {
    static final class Inventory {
        private final Map<String, Integer> onHand = new TreeMap<>();

        void addStock(String sku, int qty) {
            requireSku(sku);
            requirePositive(qty);
            int next = Math.addExact(onHand.getOrDefault(sku, 0), qty);
            onHand.put(sku, next);
        }

        Map<String, Integer> snapshot() {
            return Map.copyOf(onHand);
        }

        void reserve(Map<String, Integer> request) {
            if (request == null || request.isEmpty()) {
                throw new IllegalArgumentException("empty request");
            }

            Map<String, Integer> proposed = new LinkedHashMap<>();
            for (Map.Entry<String, Integer> entry : request.entrySet()) {
                String sku = entry.getKey();
                Integer qty = entry.getValue();

                requireSku(sku);
                if (qty == null) {
                    throw new IllegalArgumentException("null quantity");
                }
                requirePositive(qty);

                int current = onHand.getOrDefault(sku, 0);
                if (qty > current) {
                    throw new IllegalStateException("insufficient " + sku);
                }
                proposed.put(sku, current - qty);
            }

            // Do not mutate onHand until the entire request is valid.
            onHand.putAll(proposed);
        }

        int quantity(String sku) {
            return onHand.getOrDefault(sku, 0);
        }

        private static void requireSku(String sku) {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("empty SKU");
            }
        }

        private static void requirePositive(int qty) {
            if (qty <= 0) {
                throw new IllegalArgumentException("qty must be positive");
            }
        }
    }

    public static void main(String[] args) {
        Inventory inventory = new Inventory();
        inventory.addStock("BOOK", 4);
        inventory.addStock("PEN", 2);

        try {
            inventory.reserve(Map.of("BOOK", 2, "PEN", 3));
        } catch (IllegalStateException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }

        System.out.println("After failure BOOK = "
                + inventory.quantity("BOOK"));
        System.out.println("After failure PEN = "
                + inventory.quantity("PEN"));

        inventory.reserve(Map.of("BOOK", 2, "PEN", 1));
        System.out.println("After success BOOK = "
                + inventory.quantity("BOOK"));
        System.out.println("After success PEN = "
                + inventory.quantity("PEN"));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 InventoryReservationDemo.java
java InventoryReservationDemo
~~~

**Exact stdout:**

~~~text
Rejected = insufficient PEN
After failure BOOK = 4
After failure PEN = 2
After success BOOK = 2
After success PEN = 1
~~~

### 11.1. Why Is the Error Guaranteed to Be PEN?

BOOK has 4 and 2 are requested — valid. PEN has 2 and 3 are requested — invalid. Even though `Map.of` does not guarantee iteration order, the only invalid entry in the request is PEN; the method still throws before `putAll`, so the output is stable.

### 11.2. Why Does Inventory Remain Unchanged on Failure?

The method builds a separate proposed map without modifying `onHand` inside the validation loop. If any entry is short, the exception occurs **before** commit.

### 11.3. An Assumption of the Demo

`reserve` does not modify `request`; the caller must not mutate a concurrent map between validation and processing without synchronization. The demo uses immutable Map.of. A production implementation needs an input snapshot or lock if the caller might provide mutable concurrent state.

### 11.4. Can the Commit Step Fail?

With an in-memory `TreeMap`/`Integer` under normal conditions and already-validated input, `putAll` uses valid keys/values; however, **there is no general Java guarantee that any arbitrary mutation batch into mutable structures has transactional rollback** if the runtime encounters an unchecked failure (for example, resource exhaustion). If you truly need an atomic state swap in memory with other readers, building an immutable snapshot and swapping a reference under synchronization can be clearer; for a database, use a transaction.

## 12. Error Categories: Invalid Input, Disallowed State, and Infrastructure

Operation design should distinguish errors so the caller handles them consistently.

| Category | Example | Common Representation |
| --- | --- | --- |
| Invalid argument | Quantity 0, empty SKU, end time <= start | `IllegalArgumentException` or validation error |
| Illegal business state | Shipping before payment | `IllegalStateException` or domain-specific exception |
| Business rejection | Insufficient balance, out of seats | Specific domain result/exception |
| Infrastructure failure | Database/network unavailable | Exception in adapter/application service |
| Concurrency conflict | Version changed by another request | Conflict result, retry/cancellation strategy |
| Programming bug | Unexpected null dereference | Fail fast, log, fix code |

### 12.1. Exception or Result Type?

There is no single universally right choice. Use exceptions when an operation is valid in kind but cannot be performed under its contract; use a `Result`/sealed outcome when business rejection is frequently an expected handling branch.

### 12.2. Do Not Catch Exception and Return false for Every Error

If every error from DB to bug becomes false, the caller does not know why it could not execute and may retry incorrectly. Preserve failure classification across the API, logs, and monitoring.

### 12.3. Validation Errors Should Come Before Mutation

Many domain methods can fail fast. However, if an action requires checking all fields to return a list of UX errors, you can collect errors before committing. What is important is **not mutating partial state while still collecting errors**.

## 13. Complete Program 4 — Course Enrollment and Business Outcomes

File **`CourseEnrollmentDemo.java`**:

~~~java
import java.util.LinkedHashSet;
import java.util.Set;

public class CourseEnrollmentDemo {
    enum EnrollmentResult {
        ENROLLED, ALREADY_ENROLLED, FULL
    }

    static final class Course {
        private final int capacity;
        private final Set<String> studentIds = new LinkedHashSet<>();

        Course(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity must be positive");
            }
            this.capacity = capacity;
        }

        EnrollmentResult enroll(String studentId) {
            if (studentId == null || studentId.isBlank()) {
                throw new IllegalArgumentException("invalid student ID");
            }

            if (studentIds.contains(studentId)) {
                return EnrollmentResult.ALREADY_ENROLLED;
            }
            if (studentIds.size() >= capacity) {
                return EnrollmentResult.FULL;
            }

            studentIds.add(studentId);
            return EnrollmentResult.ENROLLED;
        }

        int enrolledCount() {
            return studentIds.size();
        }

        Set<String> roster() {
            return Set.copyOf(studentIds);
        }
    }

    public static void main(String[] args) {
        Course course = new Course(2);

        System.out.println(course.enroll("s1"));
        System.out.println(course.enroll("s1"));
        System.out.println(course.enroll("s2"));
        System.out.println(course.enroll("s3"));
        System.out.println("Enrolled = " + course.enrolledCount());
        System.out.println("Has s3 = " + course.roster().contains("s3"));
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 CourseEnrollmentDemo.java
java CourseEnrollmentDemo
~~~

**Exact stdout:**

~~~text
ENROLLED
ALREADY_ENROLLED
ENROLLED
FULL
Enrolled = 2
Has s3 = false
~~~

### 13.1. Why Return an Enum Instead of Throwing on Every Rejected Signup?

`ALREADY_ENROLLED` and `FULL` are normal business outcomes in many enrollment systems. The caller can display a message and does not treat it as a bug. `invalid student ID` is still rejected with IllegalArgumentException because the caller violated the input contract.

### 13.2. Two Simultaneous Invariants

- `studentIds.size() <= capacity`.
- Each studentId appears at most once.

`LinkedHashSet` helps ensure uniqueness, while `enroll` protects capacity. Using a Set does not automatically protect capacity; a business method is needed.

### 13.3. Why Check for Duplicates Before Full?

An already-enrolled student who resends the request when the course is full will receive `ALREADY_ENROLLED` instead of `FULL`. This is a useful **policy choice/idempotent-ish semantics**. Another domain might want to return outcomes in a different order, but it must be clearly defined.

### 13.4. Multiple Concurrent Threads Still Need Synchronization

Two threads can both see size=1 when capacity=2 and then both add two new studentIds, exceeding capacity. A method's single-threaded invariant is not enough in a concurrent context; you need locks or database unique+capacity constraints.

## 14. An Operation Should Leave the Object Usable on Failure

Consider the method:

~~~java
void updateLimits(int low, int high) {
    this.low = low;
    if (low > high) {
        throw new IllegalArgumentException();
    }
    this.high = high;
}
~~~

This is an **anti-pattern fragment**: field low is assigned before validation. If low > high, an exception is thrown, yet the object still holds half of the update.

Fix:

~~~java
void changeRange(int low, int high) {
    if (low > high) {
        throw new IllegalArgumentException("low > high");
    }
    this.low = low;
    this.high = high;
}
~~~

For a single-threaded observer and simple primitive assignments, this operation preserves the invariant better. With multiple threads, a shared lock or atomic snapshot is needed so readers do not observe an intermediate combination of fields.

### 14.1. Strong Exception Guarantee

A useful design goal is: **if an operation fails due to business validation, the observable object state remains unchanged**. Depending on context, this is often called failure atomicity/strong exception safety. It does not mean Java automatically provides rollback for every method.

### 14.2. Side Effects Must Be Analyzed Separately

If a method has already sent an email and then throws an exception, you cannot “undo the email” just by restoring fields. If charging a payment gateway succeeds and updating the database fails, you need compensation/idempotency/outbox/process design, not just a try/catch inside the entity.

## 15. Immutable Values Make Invariants Easier to Protect

Value objects can help eliminate invalid data right from the time they are created. For example, Money:

- Currency code is non-empty.
- Amount has 2 decimal places according to the demo.
- Amount is non-negative (within the business scope of the example).
- Only two amounts with the same currency can be added.
- Every addition returns a **new Money**, without mutating the existing Money.

### 15.1. Why Use a Record?

A record fits a small value carrier with final components. However, the constructor still needs validation; a record does not automatically prove amount/currency are valid.

### 15.2. BigDecimal and Scale

`BigDecimal` avoids many issues of binary floating-point when representing decimal numbers, yet scale/rounding/currency semantics still must be decided. The demo uses `setScale(2, RoundingMode.UNNECESSARY)` to **reject** inputs requiring rounding instead of silently rounding them.

### 15.3. Do Not Expose an “Amount Setter” on Money

If Money is an immutable value object, adding money should return a new Money. An Account entity can own a Money balance and update the reference through guarded business operations.

## 16. Complete Program 5 — Money Protecting Currency and Amount

File **`MoneyInvariantDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public class MoneyInvariantDemo {
    record Money(BigDecimal amount, String currency) {
        Money {
            Objects.requireNonNull(amount, "amount");
            Objects.requireNonNull(currency, "currency");

            if (currency.isBlank()) {
                throw new IllegalArgumentException("empty currency");
            }

            amount = amount.setScale(2, RoundingMode.UNNECESSARY);
            if (amount.signum() < 0) {
                throw new IllegalArgumentException("negative money");
            }
        }

        Money plus(Money other) {
            Objects.requireNonNull(other);
            if (!currency.equals(other.currency)) {
                throw new IllegalArgumentException("different currency");
            }
            return new Money(amount.add(other.amount), currency);
        }
    }

    public static void main(String[] args) {
        Money first = new Money(new BigDecimal("10.00"), "USD");
        Money second = new Money(new BigDecimal("2.50"), "USD");

        Money sum = first.plus(second);

        System.out.println("Sum = " + sum.amount()
                + " " + sum.currency());
        System.out.println("Original = " + first.amount());

        try {
            first.plus(new Money(new BigDecimal("1.00"), "EUR"));
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }

        try {
            new Money(new BigDecimal("-1.00"), "USD");
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 MoneyInvariantDemo.java
java MoneyInvariantDemo
~~~

**Exact stdout:**

~~~text
Sum = 12.50 USD
Original = 10.00
Rejected = different currency
Rejected = negative money
~~~

### 16.1. Constructor Normalization Preserves the Real Invariant

The compact record constructor normalizes parameter `amount` to scale 2 before Java assigns it to the final component field. The default record accessor, equals/hashCode/toString all subsequently see the normalized field; it is not just a custom accessor presenting a “pretty view” while storage remains raw.

### 16.2. Checking Currency Before Adding

`Money.plus` refuses to add USD and EUR. This is not a business-valid addition without an exchange rate/context. Do not let the BigDecimal type make us forget units.

### 16.3. Rounding Policy Must Not Be Chosen Arbitrarily

A real monetary system needs to consider decimals per currency, exchange rates, taxes, accounting rounding, negative amounts, and refunds. This lesson models only non-negative values and scale 2 to illustrate invariants. The domain can change the policy, yet must still preserve verifiable rules.

## 17. Invariants Across Multiple Objects: Designing the Aggregate Boundary

When a rule involves multiple objects, you must determine **who has the authority to decide and update**.

For example, an Order containing OrderLines:

~~~text
Order (aggregate root)
  |
  +-- Line A: sku, qty, unit price
  |
  +-- Line B: sku, qty, unit price

Invariant:
  order.status == SHIPPED => lines cannot be modified
  total == sum(line amounts)
~~~

If a caller can retrieve `order.getLines()` and modify each Line arbitrarily, Order no longer protects the invariant. Let Order own the collection and accept only commands such as `addLine/removeLine` in allowed states.

### 17.1. Place Rules Where Sufficient Data Exists to Check Them

A `Line` knows whether qty/price are valid. `Order` knows how many lines it has and its status. Therefore, the Line constructor protects line-level invariants; Order methods protect order-level invariants.

### 17.2. Do Not Make Aggregates Too Large

If all business invariants of the entire system are bundled into a single root object, locks/transactions/complexity become too large. Choose a boundary that is small yet **sufficient** to protect strong consistency rules. Cross-aggregate rules may need to be handled via application services and eventual consistency.

### 17.3. An Invariant Can Exist in Both the Domain and the Database

For example, balance >=0 can have a DB check constraint; student enrollment uniqueness can have a unique index. Domain checks fail early and keep the model clear; DB constraints protect persistent state against concurrent/external writers. The two layers complement each other rather than replacing one another.

## 18. Complete Program 6 — An Object Maintaining Data, Snapshots, and State Transitions

File **`TeamMembershipDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class TeamMembershipDemo {
    record Member(String id) {
        Member {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("invalid ID");
            }
        }
    }

    static final class Team {
        private final int capacity;
        private final List<Member> members = new ArrayList<>();
        private boolean locked;

        Team(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("invalid capacity");
            }
            this.capacity = capacity;
        }

        void add(Member member) {
            if (locked) {
                throw new IllegalStateException("team locked");
            }
            if (member == null) {
                throw new IllegalArgumentException("null member");
            }
            if (members.contains(member)) {
                throw new IllegalStateException("duplicate member");
            }
            if (members.size() == capacity) {
                throw new IllegalStateException("team full");
            }
            members.add(member);
        }

        void lock() {
            locked = true;
        }

        List<Member> members() {
            return List.copyOf(members);
        }
    }

    public static void main(String[] args) {
        Team team = new Team(2);
        team.add(new Member("a"));

        List<Member> snapshot = team.members();
        team.add(new Member("b"));

        System.out.println("Snapshot size = " + snapshot.size());
        System.out.println("Current size = " + team.members().size());

        try {
            team.add(new Member("c"));
        } catch (IllegalStateException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }

        team.lock();

        try {
            team.add(new Member("c"));
        } catch (IllegalStateException ex) {
            System.out.println("Locked = " + ex.getMessage());
        }

        System.out.println("Final size = " + team.members().size());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 TeamMembershipDemo.java
java TeamMembershipDemo
~~~

**Exact stdout:**

~~~text
Snapshot size = 1
Current size = 2
Rejected = team full
Locked = team locked
Final size = 2
~~~

### 18.1. Snapshots Help Prevent Callers from Bypassing Guards

`members()` returns List.copyOf, not the internal ArrayList. The caller cannot use `snapshot.add(new Member(...))` to exceed capacity.

### 18.2. An Old Snapshot Does Not Become a Live View

After adding member b, the snapshot taken earlier still has size 1, while the new snapshot from Team has size 2. This is the correct behavior for a structural snapshot.

### 18.3. Member Is a Record with Its Own Invariant

Team checks capacity, uniqueness, and locked; the Member constructor checks the ID. Dividing responsibilities helps each class protect what it owns.

### 18.4. Why Is Duplicate Detection Using `contains` Reliable?

The record Member has generated value equality by component id. `new Member("a")` is value-equal to another Member("a"). With mutable member objects, equality/hashCode semantics need to be designed more clearly.

## 19. Thread Safety: Single-Threaded Invariants Are Not Enough

Consider:

~~~java
void withdraw(long amount) {
    if (amount > balance) {
        throw new IllegalStateException();
    }
    balance -= amount;
}
~~~

One thread sees balance = 100; another thread also sees balance = 100; both withdraw 80. If updates interleave without synchronization, the account may debit incorrectly or suffer a lost update. **Check-then-act is a unit that must be synchronized**, not just each field assignment.

### 19.1. Volatile Does Not Make a Sequence of Operations Atomic

`volatile long balance` provides visibility/ordering semantics for field access under the Java memory model, but it does not turn `if (balance >= amount) balance -= amount` into an atomic transaction. Use a lock, CAS loop, or serialized executor as appropriate.

### 19.2. Use a Common Lock to Protect State

For a single Account, `synchronized` on methods can protect the same monitor. For transferring money between two Accounts, both sides must be coordinated under one trusted concurrency boundary; locking each Account individually without ordering can deadlock.

### 19.3. The Demo Uses a Global Lock Intentionally

The next example uses a single shared lock for the entire bank **to prove correctness easily**. It creates a bottleneck with many accounts/transactions; a production system can use deterministic lock ordering by account ID, a transaction store, or database isolation.

### 19.4. Concurrent Operations Must Be Linearizable Under Contract When Needed

A transfer should appear as an atomic logical update to observers using the same synchronization. If a reader can observe after-debit yet before-credit, it may temporarily see the total balance drop; this can violate an observable invariant even if the final state is right.

## 20. Complete Program 7 — In-Memory Transfer Under One Lock

File **`ConcurrentTransferDemo.java`**:

~~~java
public class ConcurrentTransferDemo {
    static final class Account {
        private long balanceCents;

        Account(long initialBalance) {
            if (initialBalance < 0) {
                throw new IllegalArgumentException("negative balance");
            }
            balanceCents = initialBalance;
        }
    }

    static final class Bank {
        private final Object mutex = new Object();

        void transfer(Account from, Account to, long amount) {
            if (from == null || to == null || from == to) {
                throw new IllegalArgumentException("invalid accounts");
            }
            if (amount <= 0) {
                throw new IllegalArgumentException("invalid amount");
            }

            synchronized (mutex) {
                if (from.balanceCents < amount) {
                    throw new IllegalStateException("insufficient funds");
                }

                long targetNext =
                        Math.addExact(to.balanceCents, amount);

                from.balanceCents -= amount;
                to.balanceCents = targetNext;
            }
        }

        long balance(Account account) {
            synchronized (mutex) {
                return account.balanceCents;
            }
        }

        long total(Account first, Account second) {
            synchronized (mutex) {
                return Math.addExact(
                        first.balanceCents, second.balanceCents);
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Bank bank = new Bank();
        Account a = new Account(2_000);
        Account b = new Account(2_000);

        Thread first = new Thread(() -> {
            for (int i = 0; i < 1_000; i++) {
                bank.transfer(a, b, 1);
            }
        });

        Thread second = new Thread(() -> {
            for (int i = 0; i < 1_000; i++) {
                bank.transfer(b, a, 1);
            }
        });

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("A = " + bank.balance(a));
        System.out.println("B = " + bank.balance(b));
        System.out.println("Total = " + bank.total(a, b));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ConcurrentTransferDemo.java
java ConcurrentTransferDemo
~~~

**Exact stdout:**

~~~text
A = 2000
B = 2000
Total = 4000
~~~

### 20.1. Why Does the Result Not Depend on Scheduling?

Each thread executes 1000 transfers of 1 cent in opposite directions. Initially each account has 2000, so even if one thread executes completely first, the source account never runs short of funds. Each transfer is carried out completely under the mutex; both threads have joined before printing.

### 20.2. Why Is targetNext Computed Before Mutation?

If adding to the to account causes long overflow, `Math.addExact` throws an exception before debiting the from account. Thus there is no case of “debited the sender without crediting the recipient” due to overflow.

### 20.3. Why Do balance()/total() Also Lock?

If only transfer locks while getters do not use the same synchronization policy, readers can observe inconsistent data or lack guaranteed visibility. The demo brings reads under the same monitor.

### 20.4. Limitation of a Single Bank Object

The mutex resides in Bank. If the same two accounts are operated on by **two different Bank instances**, they use two different mutexes and are not mutually protected. A production design needs a single owner/concurrency boundary or persistent transaction, not just copy-pasting the Bank class.

### 20.5. This Is Not a Database Transaction

If account balances are stored in a DB, Java synchronized only protects threads within one JVM/Bank object and does not block other processes/instances. You need DB isolation, lock/version checks, and transaction boundaries.

## 21. Optimistic Locking and Version Numbers

In a system that persists data, two requests can read the same state version. If both update without detecting a conflict, one change can overwrite the other request's change.

A common pattern:

~~~text
Read aggregate:
  id=7, version=4, balance=1000

Request A:
  calculate candidate version=5

Update database:
  UPDATE accounts
  SET balance=..., version=5
  WHERE id=7 AND version=4

Affected rows = 1
  -> A committed.

Affected rows = 0
  -> Conflict; re-read/decide whether to retry or reject.
~~~

This is a **SQL pseudocode/transaction pattern**, not a Java example to run.

### 21.1. What Does the Version Check Protect?

It detects that the state has changed since the caller read the version. That way, concurrent updates are not silently overwritten.

### 21.2. Retries Must Follow Business Logic

Not every conflict should be retried automatically without limit. If the price, inventory, user authorization, or business decision has changed, you may need to return a conflict to the client. For an idempotent operation, the retry strategy may differ.

### 21.3. Uniqueness Must Be Enforced at the Database When There Are Multiple Writers

For example, course registration might check that the student is not already present, yet two concurrent requests enroll at the same time. A unique index on (course_id, student_id) can protect persistent uniqueness; application code still needs to handle constraint violations and preserve capacity.

## 22. Designing Operations with Multiple External Side Effects

A method such as:

~~~text
reserve inventory
charge payment gateway
save order
send confirmation email
~~~

looks like a single business operation, yet **not all effects can be rolled back by a Java exception**.

### 22.1. Separate Business Decisions from Infrastructure Orchestration

- Domain entity/value objects protect local invariants and state transitions.
- The application service orchestrates the use case, loads/saves aggregates, calls gateways, and manages transaction boundaries.
- Infrastructure adapters carry out persistence, messaging, and payment APIs.
- When operations span beyond one database, consider idempotency keys, compensating actions, saga/outbox, or valid intermediate states.

### 22.2. Do Not “Pay First, Validate Later”

If an order's state cannot be paid, the code should detect that before charging whenever possible. However, even with prior validation, a concurrent state change or network failure can still happen. External operations need an appropriate verification/commit mechanism, not just an `if`.

### 22.3. A Domain Event Is Not a Transaction Commit

A domain event `OrderPaid` can describe a valid state transition. However, publishing an event before DB commit can cause downstream consumers to process a state that does not exist yet. Outbox/transactional messaging are patterns that resolve consistency between state and messages.

### 22.4. Do Not Call a Temporary State “Invalid” If the Domain Allows It

If `PAYMENT_PENDING`, `RESERVATION_PENDING`, or `COMPENSATION_REQUIRED` are needed, model them as valid business states with clear handling behavior. An invariant does not mean only final states are allowed.

## 23. Non-Overlapping Time Intervals: Defining Operations Instead of Free Start/End Edits

A room-booking system might require:

- Start before end.
- No two bookings for the same room overlap.
- Use intervals of the form **[start, end)**: start inclusive, end exclusive.
- Two bookings `[09:00,10:00)` and `[10:00,11:00)` **do not overlap**.

If `setStart` and `setEnd` are freely allowed on each booking, a caller can create inverted or conflicting time ranges without being checked.

### 23.1. Separate the Immutable Interval Value from the BookingBook Owner

- `TimeSlot` record validates start < end.
- `RoomSchedule` checks overlap against the existing list of reservations.
- `book(slot)` adds only when there is no overlap.
- Do not expose the internal mutable List.

### 23.2. Overlap Formula

Two half-open intervals A=[aStart,aEnd) and B=[bStart,bEnd) overlap when:

~~~text
aStart < bEnd  AND  bStart < aEnd
~~~

With LocalDateTime, use `isBefore` for the strictly-less comparison. Cases where start equals end fall under a “touching boundary” and therefore do not overlap.

## 24. Complete Program 8 — Non-Overlapping Booking Schedule

File **`BookingInvariantDemo.java`**:

~~~java
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

public class BookingInvariantDemo {
    record Slot(LocalDateTime start, LocalDateTime end) {
        Slot {
            if (start == null || end == null || !start.isBefore(end)) {
                throw new IllegalArgumentException("invalid interval");
            }
        }

        boolean overlaps(Slot other) {
            return start.isBefore(other.end)
                    && other.start.isBefore(end);
        }
    }

    static final class Schedule {
        private final List<Slot> bookings = new ArrayList<>();

        boolean book(Slot candidate) {
            if (candidate == null) {
                throw new IllegalArgumentException("null slot");
            }
            for (Slot existing : bookings) {
                if (existing.overlaps(candidate)) {
                    return false;
                }
            }
            bookings.add(candidate);
            return true;
        }

        int count() {
            return bookings.size();
        }
    }

    static LocalDateTime at(int hour, int minute) {
        return LocalDateTime.of(2026, 1, 1, hour, minute);
    }

    public static void main(String[] args) {
        Schedule schedule = new Schedule();

        System.out.println("First = " + schedule.book(
                new Slot(at(9, 0), at(10, 0))));

        System.out.println("Overlap = " + schedule.book(
                new Slot(at(9, 30), at(10, 30))));

        System.out.println("Touching = " + schedule.book(
                new Slot(at(10, 0), at(11, 0))));

        System.out.println("Bookings = " + schedule.count());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 BookingInvariantDemo.java
java BookingInvariantDemo
~~~

**Exact stdout:**

~~~text
First = true
Overlap = false
Touching = true
Bookings = 2
~~~

### 24.1. Why Is 09:30–10:30 Rejected?

The new interval [09:30,10:30) overlaps with [09:00,10:00). The `overlaps` function returns true, so Schedule does not add the booking.

### 24.2. Why Is 10:00–11:00 Valid?

The two intervals touch at 10:00, but the half-open convention excludes the end endpoint of the first booking, so they do not overlap.

### 24.3. This Snippet Does Not Yet Handle Timezones/DST or Concurrency

The demo uses LocalDateTime in an assumed uniform context. A real system may need ZonedDateTime/Instant, a timezone/DST policy, and database locking/a unique exclusion constraint to prevent two concurrent requests from double-booking.

### 24.4. Why Is a Business Method Better Than setStart/setEnd?

`book` checks the entire set of existing slots before commit. A setter on an individual booking does not have enough information to uphold the schedule-wide no-overlap invariant.

## 25. How Does Boundary Validation Differ from Domain Validation?

REST/API/UI layers typically need to validate syntax and user experience:

- JSON missing fields.
- Unparseable date strings.
- Malformed phone numbers.
- A form needing to display multiple errors at once.

The domain must protect rules that hold true whether data arrives from a UI, batch import, message consumer, or internal API:

- Positive amount.
- Do not withdraw more than the balance.
- Only ship an order that has been paid.
- Do not exceed capacity.
- No overlapping bookings.

### 25.1. Is Duplicate Validation Wasteful?

Not necessarily. Boundary validation helps UX and stops invalid input early. Domain validation keeps the object consistent if another boundary is forgotten; database constraints protect persistent invariants against concurrent writers. Each layer has a different responsibility.

### 25.2. If a Rule Belongs to a Configurable Policy, Which Object Checks It?

You can pass a `WithdrawalPolicy`/`PricingPolicy` into the domain operation instead of hard-coding it. However, when a policy can change over time, the operation needs a clear policy version/time and must ensure state commits according to the confirmed result.

### 25.3. Do Not Make Entities Directly Dependent on Frameworks

A simple entity can use constructors, standard exceptions, and value objects. There is no need for an HTTP status code, servlet request, or DB connection inside the `withdraw` method. The application layer maps domain failures to transport responses.

## 26. Making Invariants Hard to Break with Types

A strong way to reduce bugs is to create **types describing valid values**, instead of passing primitives/Strings everywhere.

For example:

~~~java
record StudentId(String value) {
    StudentId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("blank student id");
        }
    }
}

record PositiveQuantity(int value) {
    PositiveQuantity {
        if (value <= 0) {
            throw new IllegalArgumentException("qty <= 0");
        }
    }
}
~~~

These are **record declaration fragments**. A method `reserve(Sku sku, PositiveQuantity qty)` does not need to accept arbitrary negative integers under a typed API, because the PositiveQuantity constructor rejects them.

### 26.1. Types Reduce Checks but Do Not Replace Domain State Guards

A PositiveQuantity guarantees qty>0, yet Inventory must still check current stock >= qty. Value object types protect rules about **values**, whereas aggregate operations protect rules about the **relationship between state and actions**.

### 26.2. An Enum Does Not Automatically Preserve State Transitions

`enum Status {DRAFT, PAID, SHIPPED}` only creates constants. If an object has a public setStatus, out-of-order states can still occur. You need methods with transition guards or a typestate API if the complexity justifies it.

### 26.3. Sealed Result Types Can Represent Outcomes

Example (conceptual):

~~~java
sealed interface ReservationResult
        permits Reserved, Rejected {
}

record Reserved(String confirmationId)
        implements ReservationResult {
}

record Rejected(String reason)
        implements ReservationResult {
}
~~~

These record values can make business outcomes clearer than a boolean when the caller needs a reason and payload. However, do not use a verbose sealed hierarchy if a small enum is enough.

## 27. Idempotency: Does Repeating a Command Corrupt State?

An idempotent operation satisfies the idea: executing the same intent again creates no new side effects beyond the first time according to its contract.

For example, `close()` is often **designed** to be idempotent in custom resources; `markDelivered(orderId)` can be designed to return the same result if already delivered, depending on the domain. However, not every `AutoCloseable.close` implementation is required to be idempotent, and “repeating a money transfer” definitely needs distinct request IDs to avoid debiting twice.

### 27.1. Duplicate Requests Over the Network

A client timeout may trigger a retry because it does not know whether the server has processed the request. A `transfer` without an idempotency key can execute twice if both requests reach the server. The domain/API layer must check and store operation IDs within the transactional boundary.

### 27.2. Set Membership and Idempotency

In the example, `Course.enroll("s1")` returns ALREADY_ENROLLED when called again. It does not add a duplicate record, so the state change is idempotent even though the return value of the first and subsequent calls differs. Describe the exact semantics of the result clearly.

### 27.3. Do Not “Swallow” Errors to Fake Idempotency

If an operation fails due to a DB outage, silently returning success just because the existing status looks close enough can hide an incident. Idempotency must have an appropriate durable record/version/identity when spanning multiple processes.

## 28. Testing: Proving Invariants Across Sequences of Operations, Not Just the Happy Path

A good test suite consists of:

1. Constructors accepting valid input.
2. Constructors rejecting invalid input.
3. Business operations succeeding and producing the right postconditions.
4. Precondition violations being rejected.
5. State remaining **unchanged** after a rejected operation.
6. Invalid transitions (for example, shipping before paying) being blocked.
7. Returned collections not allowing callers to bypass invariants.
8. Value objects validating amount/quantity/currency.
9. Failed multi-field operations leaving no partial mutations.
10. Concurrent operations not losing updates or breaking totals/limits.
11. Persistence conflicts and rollbacks preserving DB invariants.
12. External side effects having idempotency and failure handling.

### 28.1. “Given–When–Then” Style Tests

~~~text
Given:
  balance = 1000 cents

When:
  withdraw(1200)

Then:
  IllegalStateException (insufficient funds)
  balance remains = 1000
~~~

This is a **test specification**, not Java source code.

### 28.2. Matrix-Style State Transition Testing

| Current State | Command | Expected Outcome |
| --- | --- | --- |
| DRAFT | addLine | Valid |
| DRAFT with lines | pay | → PAID |
| Empty DRAFT | pay | Reject, remains DRAFT |
| DRAFT | ship | Reject |
| PAID | ship | → SHIPPED |
| PAID | addLine | Reject |
| SHIPPED | cancel | Reject |
| CANCELLED | pay | Reject |

A state table helps uncover branches that were “allowed because forbidding them was forgotten” more easily than writing tests only for the happy path.

### 28.3. Property-Based Tests

For Account:

- Create a non-negative initial balance.
- Generate a random sequence of deposit/withdraw inputs.
- After each successful operation, assert balance>=0.
- If an operation is rejected, assert balance is unchanged.
- For transfer, assert total balance is conserved when both accounts belong to one operation.

For Inventory, assert every SKU has quantity>=0 after a sequence of additions/reservations.

### 28.4. Mutation Testing

If removing the guard `amount <= balance` still lets tests pass, the test suite has a gap. Mutation testing can detect missing negative-path checks and untested invariants.

### 28.5. Concurrency Tests Are Not Just “Run Many Threads and Hope for Luck”

Flaky results do not fully prove an algorithm right or wrong. Use stress tests with deterministic invariants, concurrency testing tools, code reviews against the Java memory model, and corresponding database isolation tests.

## 29. Complete Program 9 — A Simple Invariant Test Harness Without JUnit

File **`InvariantContractTestDemo.java`**:

~~~java
public class InvariantContractTestDemo {
    static final class Counter {
        private final int max;
        private int value;

        Counter(int max) {
            if (max <= 0) {
                throw new IllegalArgumentException("invalid maximum");
            }
            this.max = max;
        }

        void increment() {
            if (value >= max) {
                throw new IllegalStateException("limit reached");
            }
            value++;
        }

        void decrement() {
            if (value <= 0) {
                throw new IllegalStateException("already zero");
            }
            value--;
        }

        int value() {
            return value;
        }
    }

    static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        Counter counter = new Counter(2);

        require(counter.value() == 0, "initial");
        counter.increment();
        counter.increment();
        require(counter.value() == 2, "after increment");

        try {
            counter.increment();
            throw new AssertionError("expected exception");
        } catch (IllegalStateException ex) {
            require(counter.value() == 2, "failed increment changed state");
        }

        counter.decrement();
        require(counter.value() == 1, "after decrement");

        System.out.println("All invariant checks passed");
        System.out.println("Final value = " + counter.value());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 InvariantContractTestDemo.java
java InvariantContractTestDemo
~~~

**Exact stdout:**

~~~text
All invariant checks passed
Final value = 1
~~~

### 29.1. Why Not Use the assert Keyword?

Java `assert` statements can be disabled when `-ea` is not enabled. The demo uses an explicit `require` throwing AssertionError when an invariant test fails, so test results do not depend on the JVM assertion flag.

### 29.2. Verify Failure Atomicity, Not Just the Exception

After the third increment is rejected, the demo verifies `counter.value()==2`. Asserting only that an exception was thrown is not enough: a bad implementation might increment to 3 before throwing.

### 29.3. Why Not Use a Setter?

Counter only has increment/decrement, making the invariant `0 <= value <= max` clear. A public setter for arbitrary values would cause more failing test cases and hand responsibility for protecting state to the caller.

## 30. Common Design Mistakes and How to Fix Them

1. **Private fields with unconditional setters open.** Encapsulation is still broken through the API; replace them with guarded business commands.
2. **Validation only in the controller.** Place important invariants in the domain owner; the controller still validates UX.
3. **Assigning fields before checking.** Validate candidate state before committing.
4. **Mutating items one by one before knowing the whole batch is valid.** Use prepare-then-commit/transactions.
5. **Returning a mutable internal List/Map.** Return a snapshot/projection or expose only business methods.
6. **List.copyOf containing mutable elements can still be mutated.** Review object ownership/deep copy when needed.
7. **Total amount as a field set independently from order lines.** Derive the value or update atomically according to the invariant.
8. **A Status enum with a public setStatus still present.** Use state transition methods.
9. **Allowing negative balances assuming the database will block them.** Check in the domain so the API always protects semantics; DB constraints provide defense in depth.
10. **Using double for money without understanding rounding.** Use cents/BigDecimal/a Money value object with a currency policy.
11. **Not checking for arithmetic overflow.** Use `Math.addExact`/`multiplyExact` or BigDecimal according to the domain.
12. **An invalid constructor allowing object creation and asking the caller to fix it later.** Validate from construction; use a factory/builder if creation has multiple steps.
13. **Using a builder that produces an incomplete object usable externally.** A builder can be temporarily mutable, but `build()` must reject an invalid final state.
14. **Catching every Exception and returning false.** Loses business vs infrastructure/bug information.
15. **Arbitrarily throwing checked exceptions from getters to mask invalid state.** Prevent invalid state from construction/operations instead.
16. **Allowing the same object to be updated from multiple threads without synchronizing check+update.** Use locks/CAS/serialization per policy.
17. **Locking only setters while getters read without locking.** Readers can see intermediate state or wrong visibility.
18. **One lock per service instance while state is shared across services.** Need a real concurrency boundary.
19. **Using a Java lock to replace a DB transaction.** Does not protect writers in other processes.
20. **Running a transaction across multiple external services while promising absolute rollback.** Need saga/outbox/idempotency/compensation semantics.
21. **Confusing business rejection with an invalid parameter.** Choose clear error/result types.
22. **Automatically retrying non-idempotent commands.** Can debit twice.
23. **Not handling duplicate requests.** Use operation identity/unique constraints when needed.
24. **Not protecting null fields/mutable aliases.** Create value objects, use requireNonNull, and apply appropriate defensive copies.
25. **Making aggregates too large.** Every command has to lock a “God Object”, making scaling hard.
26. **Putting all rules in a service while the entity only has public setters.** Clarify the aggregate owner so the entity preserves local invariants itself.
27. **Mistaking a getter-only API for deep immutability.** Referents can still be mutable.
28. **Missing negative-path tests.** An invalid state can exist even if the happy path passes.
29. **Testing an exception without asserting state is unchanged.** Can miss partial mutations.
30. **Publishing events before persistence commits.** Consumers may see an event without committed data.
31. **Not defining mutation policies/intermediate states.** Arbitrary state-transition code cannot be reviewed thoroughly.
32. **Allowing collection duplicate entries to break rules.** Use a Set/unique key while still keeping capacity/state guards.
33. **Normalizing input in a getter so equals/toString use raw state.** Normalize in the constructor when it is a data invariant.
34. **Using a mutable entity as a HashMap key.** Changing fields that affect equals/hashCode can break lookups.
35. **Designing generically named `update`/`process` methods without a contract.** Split them into clear, testable business actions.

## 31. Decision-Making Process When Adding a Business Operation

When writing a new method in an entity/aggregate, ask yourself:

**Step 1 — Describe the intent:** What does the method accomplish in the language of the domain? `approve`, `reserve`, `cancel`... instead of `setFlag(true)`.

**Step 2 — Identify the owner:** Which object/aggregate has enough state to validate the rule? Does the rule need an external DB/service?

**Step 3 — List preconditions:** Input type, bounds, current state, permission/context, version.

**Step 4 — List invariants:** Which relationships between fields must stay true? Are there multi-entity invariants?

**Step 5 — Build a candidate:** Compute the new state before assigning; identify the failure paths.

**Step 6 — Commit under control:** Mutate internally under the appropriate concurrency/transaction boundary.

**Step 7 — Handle side effects:** Events, emails, gateways according to an outbox/idempotency/compensation policy if needed.

**Step 8 — Design result/errors:** What is returned on success, what categories of business errors exist, and can it be retried?

**Step 9 — Write tests:** Happy path, rejection, unchanged-on-failure, concurrency, persistence, external failures.

**Step 10 — Review public escape hatches:** Are there exposed collections/setters/reflection mappers that allow bypassing rules?

## 32. Review Questions with Answers

**Question 1.** What is an object invariant?

**Answer:** A condition that must hold true across all valid states of an object/aggregate, for example balance>=0.

**Question 2.** Does an invariant mean fields cannot change?

**Answer:** No; state can change as long as the invariant condition continues to hold true.

**Question 3.** Is it enough if every field is private, yet there is an unchecked setBalance(long)?

**Answer:** No. The setter still allows breaking the invariant from the public API.

**Question 4.** Why is withdraw more meaningful than setBalance?

**Answer:** It represents a business action, knows the amount and current balance, and can validate and protect the postcondition.

**Question 5.** What does a constructor need to check?

**Answer:** Initial inputs/invariants, avoiding creating invalid instances.

**Question 6.** If withdraw has insufficient funds, what must happen?

**Answer:** Reject per the contract and keep the balance unchanged.

**Question 7.** Why use Math.addExact when adding long cents?

**Answer:** To catch overflow before assigning the new state.

**Question 8.** Does a Status enum restrict transitions on its own?

**Answer:** No; it only defines constants. Entity methods must protect the valid transition edges.

**Question 9.** Why not use a public setStatus?

**Answer:** It allows bypassing conditions such as paying before shipping.

**Question 10.** How must order lines and total relate?

**Answer:** Total is derived from or updated consistently with the lines; avoid a separate setter that creates contradictions.

**Question 11.** If Order returns its internal ArrayList through a getter, what is the risk?

**Answer:** The caller can add/remove lines without going through guards and break the state invariant.

**Question 12.** Does List.copyOf always deep-copy elements?

**Answer:** No; it only creates an unmodifiable structural representation; mutable elements still need an ownership policy.

**Question 13.** How should an inventory.reserve with three SKUs perform checks?

**Answer:** Validate the entire request and sufficient stock before committing the batch.

**Question 14.** What is failure atomicity in a domain method?

**Answer:** If an operation is rejected/fails per contract, the object is not left in a partially updated state.

**Question 15.** Does a Java exception automatically roll back field assignments?

**Answer:** No.

**Question 16.** What does the Quantity record constructor help with?

**Answer:** Rejecting non-positive quantities from the moment the value object is created.

**Question 17.** What should Money.plus do with USD and EUR if there is no exchange rate?

**Answer:** Reject or require a clear conversion policy; do not silently add them.

**Question 18.** Does BigDecimal decide tax/rounding policies on its own?

**Answer:** No. The domain must choose the scale/rounding/currency semantics.

**Question 19.** What is the Course capacity invariant?

**Answer:** enrolledCount<=capacity along with uniqueness if needed.

**Question 20.** Does a Set automatically maintain the capacity invariant?

**Answer:** No, a Set only helps with uniqueness; enroll must check capacity.

**Question 21.** Why does Course.enroll return ALREADY_ENROLLED before FULL?

**Answer:** So retries for the same student do not report FULL when already enrolled; this is an intentional policy.

**Question 22.** Is a method that is correct single-threaded guaranteed to be correct with multiple threads?

**Answer:** No; check-then-act can race.

**Question 23.** Does volatile make withdraw's check+subtract atomic?

**Answer:** No.

**Question 24.** What scope does synchronized protect in the Bank example?

**Answer:** Operations sharing one Bank.mutex; it does not automatically protect other processes or other Bank objects.

**Question 25.** Why must transfer compute the recipient's new balance before debiting?

**Answer:** So overflow does not cause a partial debit.

**Question 26.** If a database has multiple writers, is synchronized inside one JVM enough?

**Answer:** No; database transactions/isolation/constraints are needed.

**Question 27.** What does optimistic locking typically use?

**Answer:** Version checks/conditional updates to detect concurrent conflicts.

**Question 28.** If sending an email is followed by throwing an exception, can restoring fields roll back the email?

**Answer:** No; external side effects need idempotency/compensation/process design.

**Question 29.** Do booking intervals [09:00,10:00) and [10:00,11:00) overlap?

**Answer:** No, under the half-open interval convention.

**Question 30.** Who maintains the no-overlap invariant: Booking or Schedule?

**Answer:** Booking/Slot validates start<end; Schedule knows the other bookings and therefore enforces the no-overlap rule.

**Question 31.** Does controller validation replace domain validation?

**Answer:** No; the controller handles input/UX, while the domain protects invariants regardless of entry point.

**Question 32.** Does a database unique constraint replace business logic?

**Answer:** Not completely; it supplements protection for persistent state/concurrency.

**Question 33.** Why is idempotency important for transfer?

**Answer:** Network retries can execute the same request twice if the operation ID is not recognized.

**Question 34.** Is a test asserting only the exception without asserting unchanged state sufficient?

**Answer:** No; an implementation could mutate and then throw the exception.

**Question 35.** Does protecting invariants mean never using generic setters for DTOs?

**Answer:** No; objects purely transporting data can use setters, whereas domain behavior needs appropriate guards.

**Question 36.** Are “fail fast” and “atomic failure” the same?

**Answer:** No. Fail fast rejects early; atomic failure also requires not leaving state partially updated on failure.

**Question 37.** Are internal invariants of a single entity and cross-aggregate consistency the same?

**Answer:** No; cross-aggregate rules may require transactions/sagas and different policies.

**Question 38.** Why might a List snapshot be needed?

**Answer:** So callers cannot mutate the internal collection and bypass business checks.

**Question 39.** Can a sealed result type be used for outcomes?

**Answer:** Yes, when distinguishing success/failure variants with clear payloads is needed.

**Question 40.** What is the most memorable rule from this lesson?

**Answer:** **Expose only business-meaningful actions; validate before committing; keep invariants true after success and keep state unchanged when rejected; protect collection aliases and concurrency/persistence boundaries.**

## 33. Practice Exercises

### Exercise 1 — Fixing an Anemic BankAccount

Given a class with `getBalance/setBalance`, convert it to `deposit/withdraw`. Apply validation for amount>0, balance>=0, and Math.addExact. Write tests for balance, negative inputs, insufficient funds, and unchanged-on-failure.

### Exercise 2 — Order State Machine

Design an enum DRAFT, PAID, SHIPPED, CANCELLED. Write methods addLine/pay/ship/cancel following state guards and a state transition table. Test all invalid transitions. Do not expose a public setStatus.

### Exercise 3 — Inventory Batch Reservation

Accept Map<Sku,Quantity> to reserve. If any SKU is short, deduct no SKUs. Use prepare-then-commit, and test with failures at the start and end of the request, overflow, and empty input.

### Exercise 4 — Course Capacity

Each Course has a capacity and Set<StudentId>. Duplicate enrollment returns ALREADY_ENROLLED, full capacity returns FULL, and success returns ENROLLED. Add a concurrent test and analyze where locks/DB constraints are needed.

### Exercise 5 — Immutable Money

Create record Money(BigDecimal, Currency) with invariants for non-negative amount, scale, and matching currency when using plus. Test invalid amount, different currency, and equality/value semantics.

### Exercise 6 — Defensive Copy

Create class Team with a mutable List<ImmutableMember>. Do not expose the internal List; return a snapshot. Try caller.add on the snapshot and verify that capacity cannot be exceeded.

### Exercise 7 — Two Accounts and Concurrency

Perform multi-threaded transfers, asserting conserved total and non-negative balances after each operation according to the synchronization strategy. Then analyze why the same code does not protect multiple JVM instances.

### Exercise 8 — Room Booking Schedule

Create TimeSlot(start,end) validating start<end, and RoomSchedule.book validating no-overlap with half-open intervals. Test touching and overlapping intervals, along with modeling database conflicts when two bookings arrive concurrently.

### Exercise 9 — External Payment Use Case

Model states PAYMENT_PENDING/PAID/PAYMENT_FAILED, an idempotency key, and the difference between a domain decision and a payment gateway call. Sketch an outbox/compensation strategy instead of promising to roll back an email or external charge.

## 34. End-of-Lesson Checklist

1. Does each object have clearly stated invariants?
2. Do constructors/factories create a valid state?
3. Does the public API have business methods instead of arbitrary setters?
4. Does each operation have specific preconditions and postconditions?
5. Is the entire input/candidate validated before mutation?
6. Do failure paths preserve the old state?
7. Are there any arithmetic overflow or rounding risks?
8. Could derived fields become inconsistent with source fields?
9. Does the state machine protect all transitions?
10. Are duplicate/capacity/uniqueness conditions handled?
11. Are mutable references to collections exposed?
12. Are value objects/components immutable or given appropriate defensive copies?
13. Does an aggregate root have enough information to check invariants?
14. Are business rules scattered across the UI/controller?
15. Do errors distinguish between validation, business rejection, and infrastructure failures?
16. Is there a concurrency race between check and update?
17. Can readers observe an inconsistent intermediate state?
18. Is an appropriate lock/atomic snapshot/DB transaction in place?
19. Are optimistic versions or unique constraints present when there are persistent concurrent writers?
20. Do external calls have an idempotency/compensation/outbox strategy?
21. Are there tests verifying that rejected operations leave state unchanged?
22. Are there tests covering all state transitions?
23. Are there property-based tests for multiple sequences of operations?
24. Is there audit/logging for meaningful business actions?
25. Is there an ownership policy when state involves listeners, resource pools, or collections?
26. Have overly large “God Aggregates” been avoided?
27. Are immutable value objects used for special quantities?
28. Are rule assumptions documented: currency, timezone, concurrency, refund, capacity?
29. Are boundary values tested: zero, max, empty, duplicate, null?
30. Can you explain to domain stakeholders why a method was rejected and which invariant is protected?

## 35. Conclusion

A class with only **private fields and public setters** is not enough to protect a business model. Good object-oriented design brings **state, validity rules, and permitted operations** together inside a single accountable boundary. Replacing `setBalance` with `deposit/withdraw`, replacing `setStatus` with `pay/ship/cancel`, replacing direct inventory map edits with `reserve`, and replacing direct class roster edits with `enroll` is how you turn business rules from mere promises into verifiable preconditions/postconditions.

The fundamental execution principle is **validate first, compute the candidate, then commit**; when an operation is rejected, the state remains valid and ideally unchanged. Do not let callers bypass rules via mutable collections or overly generic setters. Use value objects to rule out invalid values from the start, state machines to restrict transitions, and aggregate roots to keep related fields consistent.

Finally, the scope of guarantees must be stated clearly: code that is correct single-threaded is not necessarily thread-safe; synchronized within one JVM does not replace a database transaction; modifying fields cannot roll back email/gateway calls. When invariants span multiple objects, threads, processes, or external systems, add concurrency control, versioning, constraints, idempotency, and transaction/outbox/compensation patterns accordingly.

**Core message:** make the right action the most natural API, reject invalid actions where the state is owned, and ensure every state transition preserves the object's validity rules.
