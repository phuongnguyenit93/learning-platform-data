# Getters, setters, and intention-revealing methods in Java

In object-oriented programming, **encapsulation** is how an object controls external access to and modification of its state. Instead of allowing arbitrary field changes, a class exposes a **public API** with meaningful operations.

Three common tools are:

- **Getter:** returns information that callers are allowed to read, such as `getBalance()` or `isActive()`.
- **Setter:** changes a property according to a defined contract, such as `setDisplayName(...)`.
- **Intention-revealing method:** describes the *business action* a caller wants to perform, such as `deposit(...)`, `withdraw(...)`, `confirm()`, `cancel()`, or `reschedule(...)`.

The key point is that **declaring fields `private` and generating getters/setters for every field does not automatically produce good encapsulation**. Good encapsulation protects the object's *invariants*: conditions that must hold after construction and after each successful operation.

For example, a bank account should not allow calls to `setBalance(-500)` or `setBalance(999999)` from anywhere. The APIs `deposit()` and `withdraw()` express the intent clearly and provide a place to validate the operation.

## 1. Distinguishing getters, setters, and business-oriented methods

| Member | Purpose | Example | Design consideration |
|---|---|---|---|
| Getter | Allow information to be observed | `getName()`, `getBalance()` | Could the returned value expose mutable data? |
| Setter | Assign or change a property | `setNickname("An")` | Does the new value require validation? |
| Intention-revealing method | Perform an operation governed by rules | `withdraw(500)`, `confirm()` | What are the operation's preconditions and postconditions? |
| Constructor/factory | Create an object in a valid state | `new Account("A01")` | Which data must be provided at creation? |
| Derived query method | Answer a question about current state | `hasEnoughBalance(500)` | Should the answer be stored in a field or computed on demand? |

An intention-revealing method makes calling code easier to understand:

~~~java
account.deposit(200_000);
account.withdraw(75_000);
~~~

Compare that with a call that does not express the business operation:

~~~java
account.setBalance(account.getBalance() + 200_000);
account.setBalance(account.getBalance() - 75_000);
~~~

With setters, the caller decides the formula, valid conditions, and how money changes. Different callers may calculate differently, causing negative balances, missed fees, or incorrect updates when operations overlap.

## 2. Why can a class full of getters/setters still have weak encapsulation?

Consider an order class:

~~~java
public class Order {
    private String status;
    private int itemCount;

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public int getItemCount() {
        return itemCount;
    }

    public void setItemCount(int itemCount) {
        this.itemCount = itemCount;
    }
}
~~~

External code can create invalid states:

~~~java
Order order = new Order();
order.setItemCount(-3);
order.setStatus("CONFIRMED");  // Có thể xác nhận đơn hàng âm số lượng.
order.setStatus("UNKNOWN");    // Không có trạng thái nghiệp vụ tương ứng.
~~~

The fields are still `private`, but responsibility for all rules has moved to the caller. Such getters and setters resemble public field access with different syntax.

Potential problems include:

1. There is no single place to validate input values.
2. Setters allow state changes at any time, including when the operation is invalid.
3. Two interdependent properties can temporarily become inconsistent.
4. The name `setStatus("CONFIRMED")` says nothing about why the transition occurs, who may perform it, or which conditions are required.
5. When business rules change, finding every setter call that needs updating becomes difficult.

**The solution is not to ban all setters.** A setter is still suitable when a property can legitimately change independently and changing it does not violate the object's invariant. The task is to choose appropriate mutation permissions and API contracts.

## 3. Complete example: getters for reading, behaviors for controlling state

This example implements a simple bank account. To focus on OOP concepts, money is represented as **`long` amounts in VND**, avoiding floating-point arithmetic for monetary additions and subtractions. The program does not handle actual banking, distributed transactions, or concurrent updates.

Save as **`Demo.java`** (Java 17+):

~~~java
public class Demo {
    public static void main(String[] args) {
        BankAccount account = new BankAccount("A-101", "Lan");

        account.deposit(500_000);
        account.withdraw(125_000);
        account.renameOwner("Lan Nguyễn");

        System.out.println("Tài khoản: " + account.getAccountNumber());
        System.out.println("Chủ tài khoản: " + account.getOwnerName());
        System.out.println("Số dư: " + account.getBalance());
        System.out.println("Đủ tiền trả 400000? "
                + account.hasEnoughBalance(400_000));

        try {
            account.withdraw(500_000);
        } catch (IllegalStateException ex) {
            System.out.println("Bị từ chối: " + ex.getMessage());
        }

        try {
            account.close();
        } catch (IllegalStateException ex) {
            System.out.println("Không thể đóng: " + ex.getMessage());
        }
        account.withdraw(account.getBalance());
        account.close();
        System.out.println("Đã đóng: " + account.isClosed());
    }
}

final class BankAccount {
    private final String accountNumber;
    private String ownerName;
    private long balance;
    private boolean closed;

    public BankAccount(String accountNumber, String ownerName) {
        this.accountNumber = requireText(
                accountNumber, "Mã tài khoản");
        this.ownerName = requireText(ownerName, "Tên chủ");
        this.balance = 0;
        this.closed = false;
    }

    // Getter: quan sát trạng thái, không tự thay đổi tài khoản.
    public String getAccountNumber() {
        return accountNumber;
    }

    public String getOwnerName() {
        return ownerName;
    }

    public long getBalance() {
        return balance;
    }

    public boolean isClosed() {
        return closed;
    }

    public boolean hasEnoughBalance(long amount) {
        return amount > 0 && !closed && balance >= amount;
    }

    // Hành vi: nạp tiền theo quy tắc.
    public void deposit(long amount) {
        requireOpen();
        requirePositive(amount);
        balance = Math.addExact(balance, amount);
    }

    // Hành vi: chỉ trừ khi đủ tiền.
    public void withdraw(long amount) {
        requireOpen();
        requirePositive(amount);

        if (amount > balance) {
            throw new IllegalStateException("Không đủ số dư");
        }

        balance -= amount;
    }

    // Hành vi: đổi tên và duy trì điều kiện tên hợp lệ.
    public void renameOwner(String newName) {
        requireOpen();
        ownerName = requireText(newName, "Tên chủ");
    }

    // Hành vi: chuyển trạng thái sang đã đóng.
    public void close() {
        requireOpen();
        if (balance != 0) {
            throw new IllegalStateException(
                    "Phải tất toán số dư trước khi đóng");
        }
        closed = true;
    }

    private void requireOpen() {
        if (closed) {
            throw new IllegalStateException(
                    "Tài khoản đã đóng");
        }
    }

    private static void requirePositive(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException(
                    "Số tiền phải lớn hơn 0");
        }
    }

    private static String requireText(
            String value, String fieldName) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    fieldName + " không được để trống");
        }
        return value.strip();
    }
}
~~~

Run:

~~~bash
javac Demo.java
java Demo
~~~

Output:

~~~text
Tài khoản: A-101
Chủ tài khoản: Lan Nguyễn
Số dư: 375000
Đủ tiền trả 400000? false
Bị từ chối: Không đủ số dư
Không thể đóng: Phải tất toán số dư trước khi đóng
Đã đóng: true
~~~

The `Không thể đóng` line illustrates the rule that, with a balance of 375.000 VND, `close()` rejects the request **before changing state**. The program then withdraws the remaining balance, closes the account successfully, and prints `Đã đóng: true`. Thus, one run exercises both a rejected path and a successful path.

This example demonstrates three points:

- **Getters** only expose data that the class chooses to make readable. There is no `setAccountNumber()` because the account number must not change during the object's lifetime.
- **Intention-revealing methods** such as `deposit()`, `withdraw()`, `renameOwner()`, and `close()` govern valid changes. For example, `withdraw()` checks the amount and balance *before* subtraction; insufficient funds leave the state unchanged.
- **Invariants** such as `balance >= 0` and “no transactions after closing” are enforced centrally in the class. `Math.addExact()` also prevents silent `long` overflow when adding money.

> In real financial software, an in-memory object alone does not guarantee transaction safety when multiple threads or servers access it. Checking balances, recording transactions, and preventing duplicate updates must be designed at the appropriate storage and transaction layer.

### State-control flow diagram

~~~mermaid
flowchart LR
    U["Code bên ngoài"] --> G["Getter<br/>getBalance()"]
    G --> R["Quan sát số dư"]
    U --> D["Hành vi<br/>withdraw(amount)"]
    D --> V{"Kiểm tra điều kiện"}
    V -->|Hợp lệ| S["Thay đổi field private"]
    V -->|Không hợp lệ| E["Báo lỗi, giữ nguyên trạng thái"]
    X["setBalance(value)"] -.->|"Không cung cấp"| S
~~~

External code only requests an **action**; the class decides whether to allow it and how to update internal data. Thus, when business rules change, the behavior can be updated where the state is owned.

## 4. A getter need not return a field verbatim

A getter can return:

- A **field** that is safe to expose.
- A value **computed** from other fields.
- A **copy** or read-only representation of state.
- A representation that explicitly indicates missing data.

For example, there is no need to store an extra `itemCount` if it can be calculated from the list:

~~~java
import java.util.ArrayList;
import java.util.List;

class ShoppingCart {
    private final List<String> items = new ArrayList<>();

    public int getItemCount() {
        return items.size();
    }

    public boolean isEmpty() {
        return items.isEmpty();
    }

    public void addItem(String item) {
        if (item == null || item.isBlank()) {
            throw new IllegalArgumentException(
                    "Tên sản phẩm không hợp lệ");
        }
        items.add(item);
    }
}
~~~

`getItemCount()` is a **query method**; no `itemCount` field is required. Computing it directly avoids synchronizing `items.size()` and `itemCount` after every addition or removal.

A getter named `getTotalPrice()` can also calculate a result from line items, provided its contract is clear. However, a getter that performs an expensive network/database query or significantly changes state may surprise callers. Names such as `fetchLatestPrice()` or `refreshCache()` better express intent when those are the actual operations.

### Not all internal data needs a getter

Even read-only exposure of all internal data makes external code more dependent on the class structure. If callers only need to know “can this order be checked out?”, a `canCheckout()` API often expresses the intent more clearly than making callers retrieve `status`, `items`, and `shippingAddress` and repeat the same checks in many places.

Nevertheless, display screens, reporting tools, and serialization systems need some readable data. Getters are appropriate when that information genuinely belongs to the class's interface.

## 5. Getters returning mutable references need clear contracts

A getter can expose state even when its field is `private`:

```java
class UnsafeBasket {
    private final java.util.List<String> items =
            new java.util.ArrayList<>();

    public java.util.List<String> getItems() {
        return items; // Caller có thể gọi getItems().add("")
    }
}
```

If the class requires every item name to be nonblank, a caller invoking `getItems().add("")` bypasses validation in `addItem()`. With `List<String>`, the getter can return `List.copyOf(items)` as a structurally unmodifiable snapshot; immutable `String` elements are safe to share.

Choose the returned form according to the need: `Collections.unmodifiableList(items)` is a read-only view that reflects changes in the source list; `List.copyOf(items)` is a structural snapshot; `new ArrayList<>(items)` is a separate copy that callers can modify. **None of these automatically deep-copies mutable elements**. A getter returning an array, `Date`, or a child object with setters requires further reference protection.

## 6. When are setters appropriate?

A setter can be appropriate when:

1. The property is genuinely allowed to change independently.
2. The update has one clear meaning.
3. The value can be validated within the setter.
4. The change cannot create an invalid object state or permit actions forbidden by its lifecycle.

For example, a user changing a display name:

~~~java
public final class Profile {
    private String displayName;

    public Profile(String displayName) {
        setDisplayName(displayName);
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        if (displayName == null || displayName.isBlank()) {
            throw new IllegalArgumentException(
                    "Tên hiển thị không được trống");
        }
        this.displayName = displayName.strip();
    }
}
~~~

Here, `setDisplayName()` is appropriate because changing a display name is an independent update and the value rules are enforced at one point. This does not mean a setter should accept every value passed to it.

Depending on the business context, a name such as `renameTo(...)` or `changeDisplayName(...)` might communicate intent more clearly, especially if renaming requires authorization, audit history, or events.

### A setter need not be public

Java allows:

~~~java
class Task {
    private String title;

    public String getTitle() {
        return title;
    }

    private void setTitle(String title) {
        this.title = title;
    }
}
~~~

A `private` setter may be used only within the class. Package-private or `protected` can also be appropriate for specific design needs. **There is no rule requiring getters and setters to have the same access level**, or requiring a setter whenever a getter exists.

Immutable objects usually have no setters:

~~~java
public record Coordinates(int latitude, int longitude) {}
~~~

This `record` illustrates the syntax of a value carrier; its component accessors are named `latitude()` and `longitude()`, not `getLatitude()`. All component fields are final, but a record that references mutable data still needs deeper protection if true immutability is required.

## 7. When fields depend on each other, use one cohesive operation

Suppose a booking has `start` and `end` fields. Two independent setters can create an invalid intermediate state:

~~~java
booking.setStart(newStart);
booking.setEnd(newEnd);
~~~

If `newStart` is later than the old `end`, the first setter may make the booking invalid even though the new pair of times is valid. If each setter enforces the full invariant, updating the two fields sequentially may become impossible.

An intention-revealing API can validate both arguments **together**:

~~~java
import java.time.LocalDateTime;
import java.util.Objects;

public final class Booking {
    private LocalDateTime start;
    private LocalDateTime end;

    public Booking(LocalDateTime start, LocalDateTime end) {
        reschedule(start, end);
    }

    public LocalDateTime getStart() {
        return start;
    }

    public LocalDateTime getEnd() {
        return end;
    }

    public void reschedule(
            LocalDateTime newStart, LocalDateTime newEnd) {
        Objects.requireNonNull(newStart, "start");
        Objects.requireNonNull(newEnd, "end");

        if (!newStart.isBefore(newEnd)) {
            throw new IllegalArgumentException(
                    "Giờ bắt đầu phải trước giờ kết thúc");
        }

        // Chỉ cập nhật sau khi đã kiểm tra toàn bộ đầu vào.
        this.start = newStart;
        this.end = newEnd;
    }
}
~~~

This example protects the invariant during sequential execution. If multiple threads concurrently read or modify `Booking`, a suitable synchronization or immutability strategy is needed to prevent observation of partially updated values.

Benefits of `reschedule(start, end)`:

- The API explicitly expresses the business operation of **rescheduling**.
- Both arguments are validated before any mutation.
- Callers do not need to know the field assignment order.
- Future rules, such as “cannot reschedule after completion,” can be added to the same operation.

## 8. Name methods after valid state transitions

For objects with a lifecycle, avoid `setStatus(anyValue)`. APIs such as `confirm()`, `ship(trackingCode)`, and `cancel()` identify the requested **action** and provide a place to validate current state. For example, a draft order may be confirmed only if it contains line items; a canceled order should not revert to a new state unless the workflow permits it.

```java
// Bên trong lớp Order, với enum Status { DRAFT, CONFIRMED, CANCELLED }.
public void confirm() {
    if (status != Status.DRAFT || itemCount <= 0) {
        throw new IllegalStateException("Đơn chưa thể xác nhận");
    }
    status = Status.CONFIRMED;
}
```

Unlike a setter, an action-based API **does not let callers choose arbitrary target states**. Whether an operation should be idempotent (for example, whether a second `cancel()` should succeed or be rejected) is a business contract decision; the method name alone does not answer it.

## 9. Must getters and setters be “simple”?

A getter should generally express **observation**, be predictable, and avoid surprising business effects. A setter can validate or normalize data, or update another property when necessary to preserve an invariant. However, hiding major operations or subtle side effects inside `setX()` can be confusing:

~~~java
// Dễ gây bất ngờ nếu setter này âm thầm gửi email,
// trừ tiền, gọi API ngoài hoặc phát sự kiện nghiệp vụ.
customer.setEmail("new@example.com");
~~~

If changing an email requires verification, model the workflow with explicit operations:

~~~java
customer.requestEmailChange("new@example.com");
// Sau khi nhận và xác minh mã:
// customer.confirmEmailChange(verificationCode);
~~~

These names only illustrate API design: executable code would require implementations of the class, verification workflow, and related data. The design goal is that **readers of the code understand what is being requested** while important rules remain in the responsible object or service.

### Separating commands and queries by purpose

- **Query:** `getBalance()`, `isClosed()`, `canWithdraw(amount)` — returns information.
- **Command:** `deposit(amount)`, `close()`, `renameOwner(name)` — requests a state change.

This distinction is a useful design guideline, not a mandatory Java syntax rule. When a query involves expensive computation, caching, or external systems, its contract and name should help callers anticipate the cost.

Do not rely solely on `canWithdraw()` followed by `withdraw()` in concurrent code: the state may change between calls (*time-of-check to time-of-use*). The `withdraw()` command must still validate conditions at update time.

## 10. JavaBeans getters/setters and framework requirements

JavaBeans is a widely used convention for accessor names:

~~~java
public class PersonBean {
    private String name;
    private boolean active;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public boolean isActive() {
        return active;
    }

    public void setActive(boolean active) {
        this.active = active;
    }
}
~~~

Under the usual convention, `getName()/setName()` correspond to the `name` property, while `isActive()/setActive()` correspond to the boolean `active` property. This is **a naming/property-discovery convention**, not special syntax. Java still permits other method names.

Some libraries and frameworks (such as bean introspection, data binding, serialization, or ORM tools) may rely on getters, setters, field access, constructors, records, or annotations, depending on their version and configuration. Therefore:

- Check the framework's **actual contract** before exposing additional setters just to “make the framework work.”
- Do not assume every domain entity needs public setters for all fields.
- If a framework must instantiate objects and assign fields, consider separating a **DTO/binding model** from the **domain model** instead of exposing all domain state-changing operations.
- Validation at the API boundary (such as on a DTO) still does not replace the invariants that the domain object must always maintain.

### DTOs can be simple; domain objects need rules

A **DTO (Data Transfer Object)** carries data between application layers or across the network. For a DTO that merely holds input/output data, accessors or a record are often sufficient:

~~~java
public record ChangeDisplayNameRequest(String displayName) {}
~~~

The application layer must validate the request and use domain-model behavior:

~~~java
// Ví dụ minh họa trong ứng dụng có User và UserRepository:
ChangeDisplayNameRequest request =
        new ChangeDisplayNameRequest("Minh");

user.changeDisplayName(request.displayName());
repository.save(user);
~~~

The final two lines depend on `user`, `repository`, and classes defined in a real project. The purpose is to distinguish **requested data** from **permitted actions on a domain object**.

## 11. Do not expose sensitive data through getters

A field being `private` does not mean it should be exposed through a getter.

For example:

~~~java
final class UserCredentials {
    private final String passwordHash;

    UserCredentials(String passwordHash) {
        this.passwordHash =
                java.util.Objects.requireNonNull(passwordHash);
    }

    // Không tự tạo public getPasswordHash()
    // nếu bên ngoài không có nhu cầu hợp lệ để biết giá trị.
}
~~~

If data is needed for authentication logic, provide an appropriate method or service to perform authentication instead of exposing internal data indiscriminately. Access levels are part of secure design, but actual security also depends on handling sensitive data, access control, and authentication mechanisms.

The same principle applies to tokens, secret keys, personal data, and internal implementation details.

## 12. Setters and immutable objects

Not every object needs to change state after construction. For types that represent values, **immutable objects** have many benefits: easier reasoning, convenient use as value objects, and less risk of modification from elsewhere.

~~~java
import java.util.Objects;

public record Money(String currency, long minorUnits) {
    public Money {
        Objects.requireNonNull(currency, "currency");
        if (currency.isBlank()) {
            throw new IllegalArgumentException("Thiếu đơn vị tiền");
        }
        if (minorUnits < 0) {
            throw new IllegalArgumentException("Giá trị âm");
        }
    }

    public Money plus(Money other) {
        Objects.requireNonNull(other, "other");
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException(
                    "Không thể cộng khác đơn vị tiền");
        }
        return new Money(currency,
                Math.addExact(minorUnits, other.minorUnits));
    }
}
~~~

This `Money` class has no setters. `plus()` returns a **new value** rather than modifying the existing object:

~~~java
Money price = new Money("VND", 50_000);
Money fee = new Money("VND", 5_000);
Money total = price.plus(fee);

System.out.println(price.minorUnits()); // 50000
System.out.println(total.minorUnits()); // 55000
~~~

`minorUnits` represents the smallest currency unit defined by the system; the example uses VND for illustration. Multicurrency applications need clear conventions for currency scales, rounding, business limits, and negative amounts based on transaction type.

A meaningful operation does not necessarily **change** the object's state; it may return a new object, as `plus()` does.

## 13. Choose a design based on the need

| Need | Typical suitable API | Why |
|---|---|---|
| Read the account holder's name | `getOwnerName()` | Observation only |
| Change a nickname freely within limits | `setNickname(...)` or `renameTo(...)` | One property, with validation |
| Add money to an account | `deposit(amount)` | Protects rules and the balance |
| Subtract money | `withdraw(amount)` | Checks balance and transaction conditions |
| Change an order's state | `confirm()`, `cancel()` | Prevents invalid transitions |
| Change two interdependent times | `reschedule(start, end)` | Validates the pair together |
| Retrieve line items | `getItems()` returns a snapshot/read-only value | Does not expose the internal collection |
| Read the number of elements | `getItemCount()` | Can be calculated without a redundant field |
| Immutable value object | Constructor + accessors + methods producing new values | No need for in-place changes |
| Transfer data through an API | DTO/record or framework-appropriate bean | A data interface suited to the task |
| Secret data that should not be public | Do not expose arbitrary getters | Reduces opportunities for data exposure |

Method names alone are not sufficient design criteria. For example, `setBalance()` may be appropriate for an administration tool or simulation with specific permissions, but dangerous if anyone can call it on a live account. The decision depends on **the class's role, contract, and callers**.

## 14. Knowledge self-check

### Exercise 1 — Identify weaknesses

~~~java
class InventoryItem {
    private int stock;

    public int getStock() {
        return stock;
    }

    public void setStock(int stock) {
        this.stock = stock;
    }
}
~~~

**Question:** What is dangerous about allowing every module to call the setter? How would you redesign it?

**Hint:** A setter may assign negative stock or change quantities without a business reason. Depending on the workflow, consider `receive(quantity)`, `reserve(quantity)`, `releaseReservation(quantity)`, or `ship(quantity)`. Each operation must validate its quantity and update according to inventory rules.

### Exercise 2 — Why copy data?

~~~java
import java.util.ArrayList;
import java.util.List;

class Course {
    private final List<String> students = new ArrayList<>();

    public List<String> getStudents() {
        return students;
    }
}
~~~

**Answer:** The getter returns the mutable list itself, allowing callers to use `add/remove` and bypass class-registration rules. Prefer a read-only snapshot or suitable observable data type. If elements are mutable, also consider copying or protecting them.

### Exercise 3 — Are setters always wrong?

**Answer:** No. `setDisplayName()` can be a simple, valid API if renaming is independent, validated, and compatible with the object's lifecycle. There is no need to create an elaborate class just to change a simple field.

### Exercise 4 — Design an appointment

With `start` and `end` and the condition `start < end`, should independent `setStart()` and `setEnd()` methods be exposed?

**Answer:** They risk creating an invalid intermediate state. `reschedule(start, end)` accepts both values at once, validates the pair, and updates them only afterward, making it more suitable.

### Exercise 5 — Getters and multithreading

In a multithreaded application, if you call `if (account.hasEnoughBalance(100))` followed by `account.withdraw(100)`, does the initial check guarantee the withdrawal will succeed?

**Answer:** No. Another transaction may change the balance between the calls. `withdraw()` must validate the condition and update state safely under the chosen concurrency model.

### Exercise 6 — Value objects

An immutable `Coordinates` object needs to move 5 units along the x-axis. Should it use `setX(x + 5)`?

**Suggested answer:** A setter is unnecessary; `translate(dx, dy)` could return a new `Coordinates` object. This preserves the original value object and expresses the operation's intent.

## How to think about an object's API design

Before adding a getter, setter, or another method, ask:

1. **Does the caller really need to read this data?** Could a smaller amount of information or a derived answer replace exposing all internal state?
2. **Can this property legitimately change independently?** If so, a setter with validation may be suitable.
3. **Is this a business operation?** If so, use an action name such as `confirm()`, `withdraw()`, or `reschedule()`.
4. **Which conditions must always hold?** Validate near the state update and avoid exposing mutable references.
5. **Does this object need to be mutable?** If not, consider an immutable class/record and methods returning new values.

**Key message:** Getters and setters are **tools**, while encapsulation is a **design principle**. Expose exactly what callers need to know and the operations they are permitted to request; keep protection of state and business rules with the component that owns them.
