# Object invariants in Java OOP

In object-oriented programming, an object's state may change through many method calls. However, **not every combination of field values is valid**. For example, the quantity of stock reserved for shipment cannot be negative or exceed the total stock on hand. Rules that must hold whenever an object can be legitimately observed and used are called **conditions that remain invariant for that object** (*object invariants*).

Good class design means more than declaring fields `private`; the class must **control how state is created and changed** so that its invariants are always preserved.

## 1. What is an object invariant?

An **object invariant** is a set of logical conditions describing a valid state of **an instance**. It must hold after successful construction and after every public operation that completes normally. For operations that may fail, robust designs generally require that state remain valid and, where appropriate, unchanged when the operation is rejected.

For an inventory item, for example:

- `sku` must not be `null` or blank.
- `unitPrice` must be greater than 0.
- `onHand` (physical inventory on hand) must be nonnegative.
- `reserved` (stock set aside for orders being processed) must be nonnegative and **must not exceed** `onHand`.
- `available` (stock that can still be ordered) always equals `onHand - reserved`, so it must be nonnegative.

Mathematically:

\[
\text{onHand} \ge 0,\quad 0 \le \text{reserved} \le \text{onHand}
\]

\[
\text{available} = \text{onHand} - \text{reserved} \ge 0
\]

Conditions involving **multiple fields** (such as `reserved <= onHand`) are a key reason **not to provide unrestricted setters for individual fields**.

### Distinguishing commonly confused concepts

| Concept | Question it answers | Example |
| --- | --- | --- |
| **Invariant** | Which object states are valid? | `0 <= reserved <= onHand` |
| **Precondition** | What must hold before invoking an operation? | `quantity > 0`, sufficient available stock |
| **Postcondition** | What must hold after an operation succeeds? | Reserving 2 items increases `reserved` by 2 |
| **Immutability** | Can observable state change after construction? | `String`, `LocalDate`, an immutable value object |
| **Encapsulation** | Who can read or modify state, and how? | A `private` field updated through `reserve()` |

**An invariant is not the same as immutability.** An object can be *mutable* while maintaining its invariant throughout every valid operation. Conversely, an immutable object must also be validated to ensure that its **initial state** is valid.

## 2. Why can independent setters violate invariants?

Suppose a class exposes two setters:

~~~java
class BadStock {
    private int onHand;
    private int reserved;

    public void setOnHand(int onHand) {
        if (onHand < 0) {
            throw new IllegalArgumentException("Âm");
        }
        this.onHand = onHand;
    }

    public void setReserved(int reserved) {
        if (reserved < 0) {
            throw new IllegalArgumentException("Âm");
        }
        this.reserved = reserved;
    }
}
~~~

Each setter validates only its own field, so the following is still possible:

~~~java
BadStock stock = new BadStock();
stock.setOnHand(2);
stock.setReserved(5); // Hai giá trị đều không âm, nhưng trạng thái sai!
~~~

The condition `reserved <= onHand` is violated. Adding a check for each field **is not sufficient**; related changes must be coordinated. Even if each setter checks `reserved <= onHand`, you must consider the **update order** when transitioning between two valid states, especially in concurrent programs.

A better design exposes meaningful **business operations**: `reserve`, `release`, `ship`, and `restock`. Each operation checks the relevant conditions and updates state consistently.

## 3. Complete Java example: an inventory object that stays valid

The following example runs on **Java 11+**. Create `InvariantDemo.java`.

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public class InvariantDemo {

    static final class StockItem {
        private final String sku;
        private final BigDecimal unitPrice;
        private int onHand;
        private int reserved;

        public StockItem(String sku, BigDecimal unitPrice,
                         int initialOnHand) {
            String normalizedSku =
                    Objects.requireNonNull(sku, "sku").trim();
            Objects.requireNonNull(unitPrice, "unitPrice");

            if (normalizedSku.isEmpty()) {
                throw new IllegalArgumentException("SKU không được rỗng");
            }
            if (unitPrice.signum() <= 0) {
                throw new IllegalArgumentException("Giá phải lớn hơn 0");
            }
            if (initialOnHand < 0) {
                throw new IllegalArgumentException("Tồn kho không được âm");
            }

            this.sku = normalizedSku;
            this.unitPrice = unitPrice;
            this.onHand = initialOnHand;
            this.reserved = 0;
        }

        public String getSku() {
            return sku;
        }

        public BigDecimal getUnitPrice() {
            return unitPrice;
        }

        public int getOnHand() {
            return onHand;
        }

        public int getReserved() {
            return reserved;
        }

        // Dữ liệu dẫn xuất: không lưu một field available riêng.
        public int getAvailable() {
            return onHand - reserved;
        }

        public void reserve(int quantity) {
            requirePositive(quantity);
            if (quantity > getAvailable()) {
                throw new IllegalStateException("Không đủ hàng để giữ");
            }
            reserved += quantity;
        }

        public void release(int quantity) {
            requirePositive(quantity);
            if (quantity > reserved) {
                throw new IllegalStateException("Không thể trả quá số đã giữ");
            }
            reserved -= quantity;
        }

        public void ship(int quantity) {
            requirePositive(quantity);
            if (quantity > reserved) {
                throw new IllegalStateException("Chưa giữ đủ hàng để giao");
            }
            // Hàng được giao rời kho và hết trạng thái giữ chỗ.
            reserved -= quantity;
            onHand -= quantity;
        }

        public void restock(int quantity) {
            requirePositive(quantity);
            // Nếu overflow, Math.addExact ném ngoại lệ trước khi gán.
            int nextOnHand = Math.addExact(onHand, quantity);
            onHand = nextOnHand;
        }

        public String snapshot() {
            return "onHand=" + onHand
                    + ", reserved=" + reserved
                    + ", available=" + getAvailable();
        }

        private static void requirePositive(int quantity) {
            if (quantity <= 0) {
                throw new IllegalArgumentException("Số lượng phải dương");
            }
        }
    }

    public static void main(String[] args) {
        StockItem item = new StockItem(
                "BOOK-01", new BigDecimal("120000"), 10
        );

        System.out.println("Ban đầu: " + item.snapshot());

        item.reserve(4);
        System.out.println("Giữ 4: " + item.snapshot());

        try {
            item.reserve(7); // Còn bán được 6, thao tác thất bại.
        } catch (IllegalStateException ex) {
            System.out.println("Từ chối: " + ex.getMessage());
        }
        System.out.println("Sau lỗi: " + item.snapshot());

        item.ship(3);
        System.out.println("Giao 3: " + item.snapshot());

        item.release(1);
        System.out.println("Hủy giữ 1: " + item.snapshot());

        item.restock(5);
        System.out.println("Nhập 5: " + item.snapshot());
    }
}
~~~

Run:

~~~bash
javac InvariantDemo.java
java InvariantDemo
~~~

Output:

~~~text
Ban đầu: onHand=10, reserved=0, available=10
Giữ 4: onHand=10, reserved=4, available=6
Từ chối: Không đủ hàng để giữ
Sau lỗi: onHand=10, reserved=4, available=6
Giao 3: onHand=7, reserved=1, available=6
Hủy giữ 1: onHand=7, reserved=0, available=7
Nhập 5: onHand=12, reserved=0, available=12
~~~

### Why does each method preserve the invariant?

| Operation | Condition before mutation | Update formula | Why does the result remain valid? |
| --- | --- | --- | --- |
| Construction | Valid `sku`, positive price, initial stock ≥ 0 | `reserved = 0` | `0 <= 0 <= onHand` |
| `reserve(q)` | `q > 0` and `q <= onHand - reserved` | `reserved += q` | The new `reserved` does not exceed `onHand` |
| `release(q)` | `q > 0` and `q <= reserved` | `reserved -= q` | The new `reserved` is nonnegative |
| `ship(q)` | `q > 0` and `q <= reserved` | `reserved -= q; onHand -= q` | Both decrease by the same amount; `onHand` remains ≥ `reserved` |
| `restock(q)` | `q > 0` and no integer overflow in the sum | `onHand += q` | Only total stock increases; available stock does not decrease |

Every update **starts from a valid state**. If `reserve(7)` is rejected when only 6 units are available, the method throws an exception **before any change**, preserving the old state.

In particular, `Math.addExact` prevents overflow when adding stock to an `int`. If the sum exceeds `Integer.MAX_VALUE`, ordinary `int` addition could produce a negative result; `addExact` throws `ArithmeticException` before the field is updated. This also protects the invariant.

## 4. Viewing invariants as a validation flow

For the `reserve(q)` operation:

~~~mermaid
flowchart TD
    A["Gọi reserve(q)"] --> B{"q > 0?"}
    B -->|Không| E["IllegalArgumentException\nKhông đổi trạng thái"]
    B -->|Có| C{"q <= available?"}
    C -->|Không| F["IllegalStateException\nKhông đổi trạng thái"]
    C -->|Có| D["reserved = reserved + q"]
    D --> G["Trạng thái hợp lệ\n0 <= reserved <= onHand"]
~~~

The ideal sequence is **validate → compute the result → update state**. When a method must change several fields, avoid letting an exception occur *between updates* and leave the object partially changed.

For example, when transferring money between two wallets, do not debit wallet A before checking whether wallet B can accept the credit. For single-threaded in-memory processing, you can **check both conditions**, compute both new balances, and then assign them. For database updates, multiple services, or concurrent processing, transactions, locking, or another suitable mechanism is needed to make the grouped update reliable.

## 5. Invariants, constructors, and the object lifecycle

An invariant does not become true simply because fields are declared `private`. The class must explicitly establish it during construction.

~~~java
public final class TemperatureRange {
    private final int min;
    private final int max;

    public TemperatureRange(int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min phải <= max");
        }
        this.min = min;
        this.max = max;
    }

    public int getMin() { return min; }
    public int getMax() { return max; }
}
~~~

Here the invariant is `min <= max`. The constructor checks it before allowing construction to succeed. Declaring both fields `final` **does not automatically validate** the relationship between them.

If a constructor accepts collections or mutable objects, it must also prevent external code from silently changing the constructed object's state afterward.

~~~java
import java.util.List;
import java.util.Objects;

public final class StudyPlan {
    private final List<String> topics;

    public StudyPlan(List<String> topics) {
        Objects.requireNonNull(topics, "topics");
        if (topics.isEmpty()) {
            throw new IllegalArgumentException("Phải có ít nhất một chủ đề");
        }
        for (String topic : topics) {
            if (topic == null || topic.isBlank()) {
                throw new IllegalArgumentException("Chủ đề không hợp lệ");
            }
        }
        this.topics = List.copyOf(topics);
    }

    public List<String> getTopics() {
        return topics;
    }
}
~~~

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> external = new ArrayList<>(List.of("OOP"));
StudyPlan plan = new StudyPlan(external);

external.clear();                    // Không làm rỗng plan
System.out.println(plan.getTopics()); // [OOP]

// Ném UnsupportedOperationException:
plan.getTopics().clear();
~~~

The invariant of `StudyPlan` is that its topic list is nonempty and every element is a valid string. `List.copyOf` creates an unmodifiable list detached from later changes to the source collection. Because its elements are immutable `String` values, this is safe for the example. With **mutable elements**, `List.copyOf` copies only **references to the elements**, not the entire object graph; use appropriate deep copies or immutable value objects.

**Avoid leaking `this` from a constructor**, for example by registering a partially constructed object with a global listener before all fields and invariants have been established. Another component may observe the unfinished instance, especially in multithreaded programs.

## 6. State can change while the invariant remains true

Returning to `StockItem`, consider two states:

- Before `reserve(4)`: `onHand=10`, `reserved=0`, `available=10`.
- Sau `reserve(4)`: `onHand=10`, `reserved=4`, `available=6`.

**Both states are valid.** This clearly differs from an immutable object: field values change while the invariant is preserved.

An unrestricted setter for reserved stock would break this boundary. Instead of:

~~~java
// Thiết kế dễ bị dùng sai:
public void setReserved(int newReserved) {
    reserved = newReserved;
}
~~~

allow operations that express domain intent:

~~~java
item.reserve(4);
item.release(1);
item.ship(3);
~~~

A meaningful API often makes **invalid states harder to represent and reach**. Method names also make code clearer: “ship 3 reserved units” is more precise than “set reserved to 1 and onHand to 7.”

### Should `checkInvariant()` run after every method?

An internal helper can detect mistakes during development:

~~~java
private void checkInvariant() {
    if (onHand < 0 || reserved < 0 || reserved > onHand) {
        throw new IllegalStateException("Vi phạm invariant của kho");
    }
}
~~~

But the check **does not replace** sound design. If code has already written part of an invalid state before throwing an exception, a check at the end will detect the violation but **will not restore** the data. Prefer checking conditions and computing new values **before writing**.

Java's `assert` statement should not be the only mechanism for validating business inputs either: assertions are usually disabled unless the program runs with `-ea`. Invalid inputs should be rejected by explicit validation logic, typically through `IllegalArgumentException` or a suitable domain-specific exception.

## 7. Exceptions, partial updates, and atomicity

A good method generally aims for this rule: **success moves to a new valid state; failure leaves the object valid**. For many operations, we also want **failure to leave state unchanged** (*strong exception guarantee*), although not every API promises that stronger guarantee.

Incorrect example:

~~~java
public void unsafeReserve(int quantity) {
    reserved += quantity; // Đã thay đổi!
    if (reserved > onHand) {
        throw new IllegalStateException("Không đủ hàng");
    }
}
~~~

If the initial values are `onHand=10, reserved=4`, calling `unsafeReserve(7)` causes `reserved=11` and then throws an exception; the invariant has already been violated.

Correct approach:

~~~java
public void safeReserve(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException("Số lượng phải dương");
    }
    if (quantity > onHand - reserved) {
        throw new IllegalStateException("Không đủ hàng");
    }
    reserved += quantity;
}
~~~

When the operation is rejected, no field has been modified. This matters in services with multiple steps because **throwing an exception does not automatically undo Java assignments already made**.

Distinguish three scopes:

| Scope | Common measures | Key consideration |
| --- | --- | --- |
| One object in one thread | Guard conditions, precomputation, valid assignments | Invariants can be demonstrated method by method |
| Multiple threads sharing one object | Locks/synchronization, concurrent data structures, or immutable models | Validation and update must be coordinated as one operation |
| Multiple tables, records, or systems | Transactions, constraints, versioning/locking, idempotency, and compensating actions | Java-side checks alone cannot guarantee the consistency of shared data |

## 8. Invariants and concurrency

The `StockItem` example above deliberately illustrates OOP logic in a **single-threaded environment**. If multiple threads call `reserve`, they may simultaneously see the same `available` value, validate against an old state, and then both update it.

For example, suppose 1 item remains and two threads each try to reserve 1. If both read `available=1` before either writes, the “enough stock” decision may be made twice. `private` and `final` **do not automatically provide thread safety**.

For a shared Java object, you can protect the entire read/write operation with the same lock, for example:

~~~java
public synchronized void reserve(int quantity) {
    requirePositive(quantity);
    if (quantity > getAvailable()) {
        throw new IllegalStateException("Không đủ hàng");
    }
    reserved += quantity;
}

public synchronized int getAvailable() {
    return onHand - reserved;
}
~~~

These are only two **illustrative** methods of the same `StockItem` class. For complete thread safety, **every read/write path for shared state** (including `release`, `ship`, `restock`, `getOnHand`, `getReserved`, and snapshots involving several fields) must follow a consistent synchronization strategy. For database access or multiple server instances, `synchronized` within one JVM is insufficient; coordination is needed at the data source.

An invariant might hold at a method's start and end but be temporarily violated between statements. If other code can observe that intermediate state, it is still a design flaw. Avoid exposing intermediate state, invoking external callbacks midway through an update, or releasing a lock before the invariant has been restored.

## 9. Testing invariants at boundaries and after failures

Test more than successful paths: out-of-range values, negative values, 0, and rejected updates often reveal bugs. For example, with **JUnit 5** (using the `StockItem` class from the program above):

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class StockItemTest {

    @Test
    void reserveCannotExceedAvailableAndKeepsStateOnFailure() {
        InvariantDemo.StockItem item =
                new InvariantDemo.StockItem(
                        "BOOK-01", new BigDecimal("120000"), 5
                );
        item.reserve(3);

        assertThrows(IllegalStateException.class, () -> item.reserve(3));

        assertEquals(5, item.getOnHand());
        assertEquals(3, item.getReserved());
        assertEquals(2, item.getAvailable());
    }

    @Test
    void shipNeverMakesStockNegative() {
        InvariantDemo.StockItem item =
                new InvariantDemo.StockItem(
                        "BOOK-01", new BigDecimal("120000"), 2
                );
        item.reserve(2);
        item.ship(2);

        assertEquals(0, item.getOnHand());
        assertEquals(0, item.getReserved());
        assertEquals(0, item.getAvailable());

        assertThrows(IllegalStateException.class, () -> item.ship(1));
    }

    @Test
    void constructorRejectsInvalidInitialState() {
        assertThrows(IllegalArgumentException.class, () ->
                new InvariantDemo.StockItem(
                        "BOOK-01", BigDecimal.ONE, -1
                ));
        assertThrows(IllegalArgumentException.class, () ->
                new InvariantDemo.StockItem(
                        "   ", BigDecimal.ONE, 1
                ));
    }

    @Test
    void overflowDoesNotCorruptState() {
        InvariantDemo.StockItem item =
                new InvariantDemo.StockItem(
                        "BOOK-01", BigDecimal.ONE, Integer.MAX_VALUE
                );
        assertThrows(ArithmeticException.class, () -> item.restock(1));
        assertEquals(Integer.MAX_VALUE, item.getOnHand());
        assertEquals(0, item.getReserved());
    }
}
~~~

Note: the test file needs the corresponding JUnit Jupiter dependency and test runner. The `InvariantDemo.java` code in section 3 **does not depend on JUnit** and runs independently with `javac`/`java`. In a real project, **property-based testing** can generate many sequences of `reserve → release → ship → restock` operations and assert after each valid step that `0 <= reserved <= onHand`.

## 10. Common design mistakes

| Mistake | Consequence | Solution |
| --- | --- | --- |
| Validating each field independently | Misses relationships between fields | Write the invariant for the **entire object** before designing the API |
| Exposing unconstrained public setters | Callers can create invalid states | Use business operations with guards |
| Validating after writing a field | Exceptions can leave state corrupted | Validate and compute first, then update |
| Assuming `final` means “everything is valid” | Initial logical relationships may still be invalid | Validate in the constructor |
| Returning an internal mutable collection | Callers can bypass class rules | Use defensive copies, immutable views, or value objects as appropriate |
| Using `assert` instead of input validation | Checks may never execute | Use exceptions and validation in normal runtime execution |
| Testing only valid cases | Boundary errors go undetected | Test boundaries, exceptions, and state after failures |
| Ignoring sharing between threads | Race conditions violate invariants | Synchronize complete operations or use transactions at the right scope |

## 11. Practice questions

**1.** With `onHand=8, reserved=5`, is `reserve(3)` allowed? What are the values after it succeeds?

**Answer:** Yes, because `available = 8 - 5 = 3`. Afterward, `onHand=8, reserved=8, available=0`; the invariant still holds at the boundary.

**2.** With `onHand=8, reserved=5`, what should happen if `ship(6)` is called?

**Answer:** Reject the operation because only 5 units are reserved. State should remain unchanged; do not decrement `onHand` first.

**3.** Does `private final List<OrderLine> lines` guarantee that the object contains an immutable list?

**Answer:** No. `final` only prevents reassignment of the field reference. Both the list and individual `OrderLine` elements may be mutable; you must control every mutation path or use immutable copies, containers, and elements.

**4.** Why can a mutable object still maintain an invariant?

**Answer:** An invariant constrains **the set of permitted states**; it does not prohibit transitions. Methods are designed so that every successful transition ends in a valid state.

**5.** Is locking needed when multiple threads reserve the same inventory item?

**Answer:** A strategy is needed to coordinate validation and updates: locking, serialized processing, atomic operations, transactions, or an equivalent consistency mechanism appropriate to where the state is stored. If state resides in a database accessed by multiple application instances, locking one object in one JVM is insufficient.

When reading or writing a Java class, ask yourself: **“What must be true for every valid instance? How does the constructor guarantee it? How does each method preserve it, including when an error occurs?”** These three questions turn encapsulation into concrete design and testing rules.
