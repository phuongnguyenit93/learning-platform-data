# Encapsulating Fields and Internal Structures in Java OOP

> **Scope:** Refactoring — *Encapsulate Field*, *Encapsulate Collection*, and *Hide Representation*. The goal is for objects to protect their own valid state and expose a stable API to callers.

## 1. The Practical Problem: A `private` Field Is Not Enough

In object-oriented programming, **encapsulation** means an object controls how its state is read and changed. Clients should know **what an object can do**, not **how it stores its data**.

Two situations that undermine encapsulation:

~~~java
class Order {
    public final List<OrderLine> lines = new ArrayList<>();
}
~~~

`final` prevents reassigning the **reference** `lines`; it **does not** prevent `order.lines.clear()`, `add()`, or mutation of elements inside the list.

~~~java
class Order {
    private final List<OrderLine> lines = new ArrayList<>();

    public List<OrderLine> getLines() {
        return lines; // Vẫn rò rỉ tham chiếu nội bộ!
    }
}
~~~

Even though the field is `private`, the client can still modify the list directly through the getter:

~~~java
order.getLines().clear();
~~~

This is **representation exposure**: the data structure representing internal state is exposed, letting other code modify it without going through the object's rules.

### Learning Outcomes

After this lesson, you should be able to:

- Recognize exposed fields, mutable collections, mutable elements, and aliased references that leak state.
- Apply `Encapsulate Field` by keeping fields `private` and exposing meaningful operations rather than generating getters/setters for every field.
- Hide `ArrayList`, `HashMap`, or arrays behind a **behavioral contract** independent of the underlying storage structure.
- Distinguish **immutable snapshots**, **unmodifiable views**, and **deep copies**.
- Write tests proving clients cannot modify internal state through returned references.
- Refactor carefully, preserve promised public behavior, and handle API compatibility when necessary.

## 2. Why Encapsulate Internal Structures?

Suppose `ShoppingCart` has these rules:

1. Each SKU appears at most once.
2. An SKU must be non-`null`, nonempty, and not whitespace-only.
3. Unit prices (in cents) are nonnegative; quantities are positive for existing lines.
4. Changing a quantity to `0` removes the line rather than storing a line with quantity `0`.
5. The total is the sum of `unitPriceCents × quantity` across lines; it must not return a negative or incorrect result due to `long` overflow.

If clients can call `cart.lines.add(...)` or assign `cart.lines.get(0).quantity = -5`, they can break all these rules without `ShoppingCart` knowing.

An **invariant** is a condition that must hold in every observable object state after a successful public operation. The cart API should provide `putLine`, `changeQuantity`, `removeLine`, and `totalCents` rather than letting clients freely mutate its `Map`/`List`.

| Design | Protects invariants? | Key point |
|---|---|---|
| `public List<Line> lines` | No | Clients mutate the collection directly |
| `private List<Line> lines` + getter returning the original reference | No | Syntax changes, but representation remains exposed |
| Getter returning `Collections.unmodifiableList(lines)` | Prevents edits through the view only | A **live** view still reflects source changes; mutable elements remain editable |
| Getter returning `List.copyOf(lines)` | Prevents structural edits to the snapshot | **Shallow** copy: mutable elements can still change |
| Snapshot containing **immutable value objects** | Usually safe for reading | Clients cannot modify the list or elements through returned references |
| Rule-checked mutation API | Can enforce invariants | Every valid change passes through a controlled method |

**Encapsulation does not imply total immutability:** A cart may still change through **permitted** public operations. What matters is that no shortcut bypasses validation and business rules.

## 3. Runnable Java 17 Example: From Leaky Cart to Safe API

Create one `EncapsulationDemo.java` file with JDK 17 or later. The example includes an **intentionally unsafe** version to demonstrate the consequences and an improved version to test.

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;

public class EncapsulationDemo {

    // BEFORE: client có thể sửa cả danh sách lẫn đối tượng nằm trong đó.
    static final class MutableLine {
        public String sku;
        public long unitPriceCents;
        public int quantity;

        MutableLine(String sku, long unitPriceCents, int quantity) {
            this.sku = sku;
            this.unitPriceCents = unitPriceCents;
            this.quantity = quantity;
        }
    }

    static final class LeakyCart {
        public final List<MutableLine> lines = new ArrayList<>();

        long totalCents() {
            long sum = 0;
            for (MutableLine line : lines) {
                sum += line.unitPriceCents * line.quantity;
            }
            return sum;
        }
    }

    // AFTER: value object bất biến, dùng để trả kết quả đọc.
    // String, long, int ở đây không để lộ mutable component.
    public record LineSnapshot(
            String sku, long unitPriceCents, int quantity) {
        public LineSnapshot {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("sku must not be blank");
            }
            if (unitPriceCents < 0) {
                throw new IllegalArgumentException("unitPriceCents must be >= 0");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be > 0");
            }
        }
    }

    static final class ShoppingCart {
        // Có thể đổi Map thành cấu trúc khác mà API không đổi.
        // LinkedHashMap giữ thứ tự chèn cho ví dụ.
        private final Map<String, LineSnapshot> lines = new LinkedHashMap<>();

        // Upsert: SKU mới thì thêm; SKU cũ thì thay giá và số lượng.
        public void putLine(String sku, long unitPriceCents, int quantity) {
            LineSnapshot next = new LineSnapshot(sku, unitPriceCents, quantity);
            lines.put(next.sku(), next);
        }

        // Chỉ thay số lượng; quantity = 0 xóa dòng.
        public void changeQuantity(String sku, int quantity) {
            if (quantity < 0) {
                throw new IllegalArgumentException("quantity must be >= 0");
            }
            LineSnapshot current = lines.get(sku);
            if (current == null) {
                throw new NoSuchElementException("Unknown SKU: " + sku);
            }
            if (quantity == 0) {
                lines.remove(sku);
                return;
            }
            lines.put(sku,
                new LineSnapshot(sku, current.unitPriceCents(), quantity));
        }

        public boolean removeLine(String sku) {
            return lines.remove(sku) != null;
        }

        // Snapshot tách khỏi Map nội bộ; các element đều bất biến.
        public List<LineSnapshot> lines() {
            return List.copyOf(lines.values());
        }

        public long totalCents() {
            long result = 0;
            for (LineSnapshot line : lines.values()) {
                long itemTotal = Math.multiplyExact(
                    line.unitPriceCents(), line.quantity());
                result = Math.addExact(result, itemTotal);
            }
            return result;
        }

        public int lineCount() {
            return lines.size();
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void expectUnsupported(Runnable operation) {
        try {
            operation.run();
        } catch (UnsupportedOperationException expected) {
            return;
        }
        throw new AssertionError("Expected UnsupportedOperationException");
    }

    private static void expectIllegalArgument(Runnable operation) {
        try {
            operation.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("Expected IllegalArgumentException");
    }

    public static void main(String[] args) {
        // Chứng minh lỗi: client sửa state mà không qua validation.
        LeakyCart old = new LeakyCart();
        MutableLine leaked = new MutableLine("BOOK", 100, 2);
        old.lines.add(leaked);
        check(old.totalCents() == 200, "initial old total");
        leaked.quantity = -3; // alias ngoài giỏ hàng làm hỏng invariant
        check(old.totalCents() == -300, "expected broken old total");
        System.out.println("LEAK: client changed old cart total to -300");

        ShoppingCart cart = new ShoppingCart();
        cart.putLine("BOOK", 100, 2);
        cart.putLine("PEN", 99, 1);
        check(cart.totalCents() == 299, "initial safe total");
        check(cart.lineCount() == 2, "initial line count");

        List<LineSnapshot> snapshot = cart.lines();
        expectUnsupported(snapshot::clear);
        check(snapshot.get(0).quantity() == 2, "snapshot initial quantity");

        // Thao tác hợp lệ đi qua API có kiểm soát.
        cart.changeQuantity("BOOK", 3);
        check(cart.totalCents() == 399, "safe updated total");
        check(snapshot.get(0).quantity() == 2,
            "old snapshot must not change after cart update");
        check(cart.lines().get(0).quantity() == 3,
            "new snapshot must reflect new state");

        // Input sai bị chặn và không làm thay đổi state.
        expectIllegalArgument(() -> cart.putLine("BAD", -1, 1));
        expectIllegalArgument(() -> cart.putLine("X", 100, 0));
        expectIllegalArgument(() -> cart.putLine("  ", 100, 1));
        expectIllegalArgument(() -> cart.changeQuantity("BOOK", -1));
        check(cart.lineCount() == 2 && cart.totalCents() == 399,
            "invalid operations must not corrupt cart");

        // Đổi số lượng về 0 sẽ xóa dòng, không tạo dòng không hợp lệ.
        cart.changeQuantity("BOOK", 0);
        check(cart.lineCount() == 1, "remove by quantity zero");
        check(cart.totalCents() == 99, "total after removal");

        System.out.println("PASS: cannot modify exposed snapshot");
        System.out.println("PASS: invariants enforced by public methods");
        System.out.println("PASS: old snapshot is independent");
        System.out.println("Final total (cents): " + cart.totalCents());
    }
}
~~~

Compile and run:

~~~bash
javac EncapsulationDemo.java
java EncapsulationDemo
~~~

Expected output:

~~~text
LEAK: client changed old cart total to -300
PASS: cannot modify exposed snapshot
PASS: invariants enforced by public methods
PASS: old snapshot is independent
Final total (cents): 99
~~~

**Why Is the New Version Safer?**

1. `lines` is `private`, so clients cannot add/delete lines through field access.
2. `putLine` and `changeQuantity` are the **only entry points** for line changes in this model. Validation occurs **before** state updates.
3. `LineSnapshot` is a record with `String`, `long`, and `int` components; it contains no mutable-object references. The cart creates a new record when changing quantity.
4. `List.copyOf(lines.values())` creates an unmodifiable snapshot. Old snapshots do not change when `ShoppingCart` is updated internally.
5. `Math.multiplyExact` and `Math.addExact` detect overflow by throwing `ArithmeticException`, preventing silently incorrect negative `long` results.

The example does not address **concurrency**: `LinkedHashMap` is not thread-safe. If multiple threads modify the cart, restrict ownership per request/transaction or synchronize at the correct boundary; immutable snapshots do not automatically make the whole `ShoppingCart` thread-safe.

## 4. Three Commonly Confused Concepts: Copy, View, and Immutable Element

Consider a `List<Person>` where `Person` has a setter:

~~~java
final class Person {
    private String name;
    Person(String name) { this.name = name; }
    String getName() { return name; }
    void setName(String name) { this.name = name; }
}
~~~

| Statement | Can the returned list's structure be changed? | Are later source changes visible? | Can `Person` be mutated through the reference? |
|---|---|---|---|
| `return people;` | Yes | Yes, same object | Yes |
| `return Collections.unmodifiableList(people);` | Not through the view | **Yes** (live view) | **Yes** |
| `return new ArrayList<>(people);` | Yes, but only in the copy | Later source additions/removals are not visible | **Yes** |
| `return List.copyOf(people);` | No | Generally a structural snapshot of a mutable source | **Yes** |
| `return people.stream().map(p -> new ImmutablePerson(p.getName())).toList();` | Not through the returned list | No, when elements are immutable | No |

`List.copyOf` copies a mutable collection's structure but **does not deep-copy** elements. If an element is mutable, both source and copy still reference the same object. `Collections.unmodifiableList` only wraps a list; its original owner may still change it, and the view will reflect those changes.

`Stream.toList()` (Java 16+) produces an unmodifiable list, but **also does not automatically deep-copy its elements**.

### Use Real Defensive Copies for Mutable Elements

If `Person` must remain mutable, copy elements on **output**:

~~~java
public List<Person> peopleSnapshot() {
    return people.stream()
        .map(p -> new Person(p.getName()))
        .toList();
}
~~~

And copy them on **input**:

~~~java
public void addPerson(Person incoming) {
    java.util.Objects.requireNonNull(incoming);
    people.add(new Person(incoming.getName()));
}
~~~

This way, mutating `incoming` after `addPerson` or changing a `Person` returned by `peopleSnapshot` does not affect internal state, **provided** names are immutable `String` values and the class contains only the fields being copied. Nested objects, arrays, collections, and mutable `Date` values may require deeper copies of owned components. No universal clone function safely handles every object graph.

## 5. Applying Encapsulate Field Correctly

Consider a public field:

~~~java
class BankAccount {
    public long balanceCents;
}
~~~

Mechanically changing it to `private` plus a setter is insufficient:

~~~java
class BankAccount {
    private long balanceCents;

    public long getBalanceCents() { return balanceCents; }
    public void setBalanceCents(long balanceCents) {
        this.balanceCents = balanceCents; // vẫn cho phép caller gán âm
    }
}
~~~

If the contract is "the balance must remain nonnegative," the API should expose **valid actions**:

~~~java
final class BankAccount {
    private long balanceCents;

    BankAccount(long openingBalanceCents) {
        if (openingBalanceCents < 0) {
            throw new IllegalArgumentException("Negative opening balance");
        }
        this.balanceCents = openingBalanceCents;
    }

    long balanceCents() {
        return balanceCents; // primitive: trả theo giá trị, an toàn
    }

    void deposit(long amountCents) {
        if (amountCents <= 0) {
            throw new IllegalArgumentException("Deposit must be positive");
        }
        balanceCents = Math.addExact(balanceCents, amountCents);
    }

    void withdraw(long amountCents) {
        if (amountCents <= 0 || amountCents > balanceCents) {
            throw new IllegalArgumentException("Invalid withdrawal");
        }
        balanceCents -= amountCents;
    }
}
~~~

This lets clients increase/decrease balances only under valid conditions. Transferring between accounts requires an appropriate transactional operation; merely calling `withdraw` and then `deposit` does not guarantee atomicity if either step fails.

### Choose APIs According to the Nature of State

- Read-only configuration fields: use `private final` with a safe getter or constructor arguments.
- Constrained business values: prefer `deposit`, `withdraw`, `changeQuantity`, `rename`, and `activate` over `setAnything`.
- Object-owned collections: expose snapshots and validate mutations through `add/remove/update`.
- Computed values: prefer a `totalCents()` method rather than letting clients update a `total` field that may become inconsistent.
- DTOs that transfer data between layers/APIs: records or JavaBeans with setters may be appropriate; not every DTO must be a rich domain model.

**Key point:** The goal is not "as few getters/setters as possible." An API should reflect permitted object operations and the invariants that must be maintained.

## 6. Hiding Data Structures Reduces Implementation Coupling

Compare these two APIs:

~~~java
// Client phụ thuộc vào cấu trúc lưu trữ.
Map<String, LineSnapshot> getInternalMap();

// Client phụ thuộc vào khả năng cần dùng.
void putLine(String sku, long priceCents, int quantity);
void changeQuantity(String sku, int quantity);
List<LineSnapshot> lines();     // snapshot đọc
long totalCents();
~~~

With the second design, the implementation can switch from `LinkedHashMap` to a more suitable structure, add an SKU index, cache totals, or store other records while callers continue using the public contract.

~~~mermaid
classDiagram
    class CartClient {
      +renderCart()
      +updateQuantity()
    }
    class ShoppingCart {
      -Map~String,LineSnapshot~ lines
      +putLine(String,long,int)
      +changeQuantity(String,int)
      +removeLine(String) boolean
      +lines() List~LineSnapshot~
      +totalCents() long
    }
    class LineSnapshot {
      <<record>>
      +sku() String
      +unitPriceCents() long
      +quantity() int
    }
    CartClient --> ShoppingCart : gọi API công khai
    ShoppingCart o--> LineSnapshot : chứa dữ liệu bất biến
~~~

**Hiding implementation details** does not mean clients know nothing about the data. Clients may need SKU names, prices, and quantities for legitimate business purposes; they need not know whether those values are stored in an `ArrayList`, `LinkedHashMap`, or database table.

## 7. Safe Refactoring in a Running Project

1. **Identify data ownership:** Who may create, hold, modify, and discard collections or objects? Find every existing mutation path: public fields, getters, setters, constructor aliases, callbacks, and serialization.
2. **Document the contract first:** Does the field allow null or duplicates? Does order matter? Which exception types are promised? Which operations must preserve data?
3. **Add characterization/regression tests:** Cover valid data, invalid inputs, boundaries, and side effects clients actually expect.
4. **Move updates into the state owner:** For example, `addLine`, `removeLine`, and `changeQuantity`. Validate before mutating, keeping state valid even when exceptions occur.
5. **Restrict field access:** Make fields `private` where possible, migrating clients to the new API in controlled steps.
6. **Protect inputs and outputs:** Copy incoming collections when taking ownership; return suitable snapshots or views; for mutable elements, use safe copies or value objects.
7. **Retire old shortcuts:** Stop returning mutable references and exposing arbitrary setters that break invariants. For published public APIs, plan deprecation/migration or compatible adapters.
8. **Run tests and review diffs:** Check invariants, concurrency contracts where applicable, performance with large collections, and serialization/API compatibility.

~~~mermaid
flowchart TD
    A["Quan sát alias / field rò rỉ"] --> B["Xác định invariant và contract hiện có"]
    B --> C["Viết test bảo vệ hành vi"]
    C --> D["Tạo API thao tác có kiểm soát"]
    D --> E["Ẩn field và defensive copy"]
    E --> F{"Test regression + bất biến PASS?"}
    F -->|Không| G["Sửa nguyên nhân rồi chạy lại"]
    G --> F
    F -->|Có| H["Đổi client, dọn API cũ, review"]
~~~

### Compatibility Concerns

- **API/source compatibility:** Changing a `public` field to `private` breaks client code accessing it. Published libraries need migration plans and versioning.
- **Collection contracts:** If clients are promised **ordering**, switching from `LinkedHashMap` to `HashMap` and returning a list may change observable order. If order is not contractual, avoid tests that unnecessarily impose one.
- **ORM/JPA/serialization:** Frameworks may require constructors, access strategies, or annotations. Maintain framework compatibility rather than exposing public fields for convenience.
- **Performance:** `List.copyOf` creates snapshots when needed; frequent snapshots of very large collections can be costly. Consider paged queries, controlled iterators, or suitable immutable data structures without sacrificing invariants.
- **Thread safety:** Returning a safe snapshot does not automatically make collection updates thread-safe. Depending on context, use synchronization, immutable aggregates, or transactions.
- **JSON representation:** DTOs may differ from domain models. Adapters/mappers should convert between them without leaking domain storage structures into public payloads.

## 8. Testing Encapsulation: Prove Callers Cannot Break State

Tests should verify **behavior**, not just whether a field is marked `private`.

| Test case | Action | Expected result |
|---|---|---|
| Do not expose mutable lists | Receive `lines()` and call `clear()` | Blocked; cart remains unchanged |
| Independent snapshots | Take snapshot A, update the cart, then take B | A retains old state; B reflects new state |
| Do not expose mutable elements | Attempt to modify a returned element | No direct mutation path; copy mutable DTOs |
| Validate before writing | Call `putLine("", 100, 1)` | Throw `IllegalArgumentException`; total and lineCount remain unchanged |
| Quantity invariant | Call `changeQuantity("BOOK", 0)` | Remove BOOK; do not store quantity = 0 |
| Invalid operation | Call `changeQuantity("UNKNOWN", 2)` | Throw `NoSuchElementException`; existing data stays unchanged |
| Calculation overflow | Provide values large enough to overflow | Never return a wrapped total; report a detectable error |
| Contract stability | Replace the internal `Map` implementation | Valid client scenarios still produce correct results |

Use JUnit 5 (JUnit Jupiter), placing tests in the same package as `EncapsulationDemo`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;

class ShoppingCartTest {
    @Test
    void returnedCollectionCannotMutateCart() {
        var cart = new EncapsulationDemo.ShoppingCart();
        cart.putLine("BOOK", 100, 2);

        List<EncapsulationDemo.LineSnapshot> before = cart.lines();
        assertThrows(UnsupportedOperationException.class, before::clear);

        cart.changeQuantity("BOOK", 3);
        assertEquals(2, before.get(0).quantity());
        assertEquals(3, cart.lines().get(0).quantity());
        assertEquals(300, cart.totalCents());
    }

    @Test
    void failedValidationDoesNotCorruptState() {
        var cart = new EncapsulationDemo.ShoppingCart();
        cart.putLine("BOOK", 100, 2);

        assertThrows(IllegalArgumentException.class,
            () -> cart.putLine("PEN", -1, 2));
        assertThrows(IllegalArgumentException.class,
            () -> cart.changeQuantity("BOOK", -4));

        assertEquals(1, cart.lineCount());
        assertEquals(200, cart.totalCents());
    }

    @Test
    void removingByZeroKeepsInvariant() {
        var cart = new EncapsulationDemo.ShoppingCart();
        cart.putLine("BOOK", 100, 2);
        cart.changeQuantity("BOOK", 0);

        assertTrue(cart.lines().isEmpty());
        assertEquals(0, cart.totalCents());
    }
}
~~~

The tests rely on demo classes in the same package (nested classes are not declared `public`). Real projects should place each type in an appropriate file and choose access modifiers based on package/module APIs.

Also test **input-object boundaries**. If a constructor accepts `List<MutableLine>` and stores the reference directly, callers can still change `MutableLine` objects or the list afterward, even if getters perform defensive copies.

## 9. Common Refactoring Mistakes

**Mistake 1 — "Private fixes everything."** Getters returning the original `List`/`Map` still expose data. Examine all **reference paths** into and out of the object.

**Mistake 2 — Adding setters for every field.** Unrestricted setters for `balance`, `items`, and `status` may permit invalid states. Prefer valid domain operations.

**Mistake 3 — Assuming `final` makes an object immutable.** A `private final List<T>` can still change contents when the owner calls `add/remove`; that is valid when controlled. If the reference leaks, outside code can modify it too.

**Mistake 4 — Confusing an unmodifiable view with a snapshot.** `Collections.unmodifiableList(source)` blocks edits through the wrapper but still reflects changes in `source`; `List.copyOf(source)` creates a structural snapshot (while sharing element references).

**Mistake 5 — Copying a list but not its elements.** `new ArrayList<>(people)` does not deep-copy `Person`. Calling `peopleCopy.get(0).setName("X")` may modify internal data when both lists share the same element.

**Mistake 6 — Assuming records are deeply immutable.** Records containing `List`, `Date`, or arrays only have final fields; elements and nested objects may be mutable. Make defensive copies in constructors and accessors as needed.

**Mistake 7 — Forgetting atomicity during mutation.** Updating state before validation or potentially failing logic can leave an object partially changed. Calculate and validate first, then commit; multiple resources may require a transaction.

**Mistake 8 — Breaking a library's public API without a plan.** Changing a `public field` to private is not automatically a compatible refactoring at the library boundary. API compatibility tests and migration guidance may be necessary.

## 10. Practice Exercises

**Exercise 1 — Identify the Exposure:**

~~~java
class Library {
    private final List<StringBuilder> titles = new ArrayList<>();

    void add(StringBuilder title) { titles.add(title); }
    List<StringBuilder> getTitles() { return List.copyOf(titles); }
}
~~~

Describe **two paths** that unintentionally change internal titles: modifying `StringBuilder` after passing it into `add`, and modifying a `StringBuilder` returned by `getTitles`. Try fixing the design with `List<String>` (using immutable `String` elements) or by copying values on input/output.

**Exercise 2 — Replace Setter APIs:** An `Employee` exposes `setSalaryCents(long)` publicly. Define salary invariants and propose domain-specific methods (`adjustSalary` or `changeSalary` with validation and context-appropriate authorization). Test negative amounts and values exceeding business limits.

**Exercise 3 — Cart Lines:** Change `ShoppingCart.lines()` to return a live unmodifiable view instead of a snapshot. Write a test distinguishing **whether A remains unchanged after an update**, then decide which behavior matches the contract.

**Exercise 4 — Change Internal Representation:** Replace `LinkedHashMap` with another structure while keeping `putLine`, `changeQuantity`, `removeLine`, and `totalCents`. If result ordering was never promised, do not make clients depend on the internal order.

**Exercise 5 — Null, Races, and Overflow:** Extend tests for null SKUs, missing SKUs, large monetary values, and concurrent calls. Distinguish validation defects from thread-safety requirements that need to be added to the contract.

### Completion Criteria

You can identify state leaks through fields, getters, constructors, or mutable elements; design mutation APIs that maintain invariants; choose appropriate **snapshots/views/copies**; and prove with Java tests that clients cannot arbitrarily corrupt internal structures. When refactoring libraries or running systems, also check public API, framework, and concurrency compatibility.
