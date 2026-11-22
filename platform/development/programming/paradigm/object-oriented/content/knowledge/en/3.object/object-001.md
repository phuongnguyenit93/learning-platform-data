# Object Identity, State, and Behavior in Java

In object-oriented programming (OOP), an **object** is more than a collection of variables and functions. It is a concrete entity at runtime with **identity**, **state**, and **behavior**. These three aspects help us model entities such as orders, bank accounts, shopping carts, players, and devices in software.

Imagine two orders belonging to the same customer, Lan, each containing a notebook and both marked “Confirmed.” They may have identical data yet remain **two different orders**. Conversely, an order may start as “Draft” and later become “Confirmed” while remaining **the same order**.

This is the essential distinction:

- **Identity:** Which object is this? Is it the very same object referenced elsewhere?
- **State:** What data does the object hold at this moment?
- **Behavior:** Which operations can the object perform, which questions can it answer, and under what rules may it change its state?

## 1. Comparing the Three Aspects

| Aspect | Question to answer | Example with `Order` | Can it change over time? |
|---|---|---|---|
| **Identity** | Is it *the same object*? | Two variables refer to one `Order` | An object's identity does not change during its lifetime |
| **State** | What data does the object currently contain? | Item list, `DRAFT`/`CONFIRMED` status | May change if the design allows it |
| **Behavior** | What can the object do? | `addItem()`, `confirm()`, `cancel()` | Methods are defined by its type; results/actions may depend on state |

Put another way, **identity** lets us track *the same object over time*; **state** describes *its current condition*; **behavior** defines *how it can respond*.

### Everyday Example

An access card has its own identifier. It may be active today and blocked tomorrow. The `unlock()` behavior is valid only when the person performing it is authorized, and `enter()` must check the current state. Blocking the card does not turn it into another card.

In software systems, distinguish two kinds of identity:

1. **Java object identity:** a particular instance existing in JVM memory, distinguished when comparing references with `==`.
2. **Business identity:** an order ID, UUID, account number, and so on, used to track the same business entity across databases, application executions, and services. Two distinct Java objects can represent the same business record.

These concepts are related but **not equivalent**.

## 2. Objects, Classes, and References

A **class** describes a type and its operations; an **object** is a concrete instance of that type; a **reference variable** is how Java code refers to that object.

~~~java
Order first = new Order("Lan");
Order second = new Order("Lan");
Order alias = first;
~~~

In this snippet:

- `new Order("Lan")` is executed twice, creating two separate instances referenced by `first` and `second`.
- `alias = first` only copies **the reference value**. Without `new`, no third object is created.
- `first == second` is `false`; `first == alias` is `true`.
- If `alias` invokes a state-changing method, `first` also observes the change because both refer to **one object**.

~~~mermaid
flowchart LR
    F["Biến first"] --> A["Order object #1<br/>customer: Lan<br/>status: DRAFT"]
    AL["Biến alias"] --> A
    S["Biến second"] --> B["Order object #2<br/>customer: Lan<br/>status: DRAFT"]
~~~

This models reference relationships, not physical JVM memory locations. The number of reference variables **does not equal** the number of objects.

Also note that `Order x;` merely *declares* a local reference variable; it creates no object and must be assigned before being read. `Order x = null;` creates no object either: `null` indicates that the reference currently points to none.

## 3. Complete Java Example: An Order with Identity, State, and Behavior

The following example models an order with these rules:

- Each instance receives a `UUID` identifier when it is created.
- The order stores the customer name, item list, and current status.
- Items can be added and the order confirmed only while it is in draft.
- An empty order cannot be confirmed; only a confirmed order can be canceled.

Save the entire example as **`Demo.java`** and run it with **Java 17+**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public class Demo {
    public static void main(String[] args) {
        Order first = new Order("Lan");
        Order second = new Order("Lan");
        Order alias = first;

        System.out.println("first == second: " + (first == second));
        System.out.println("first == alias: " + (first == alias));

        alias.addItem("Sổ tay");
        first.confirm();

        System.out.println("first status: " + first.getStatus());
        System.out.println("alias status: " + alias.getStatus());
        System.out.println("first items: " + first.getItems());
        System.out.println("second items: " + second.getItems());
        System.out.println("first.equals(second): " + first.equals(second));

        first.cancel();
        System.out.println("alias after cancel: " + alias.getStatus());
    }
}

enum OrderStatus {
    DRAFT, CONFIRMED, CANCELLED
}

final class Order {
    private final UUID id;
    private final String customer;
    private final List<String> items;
    private OrderStatus status;

    public Order(String customer) {
        if (customer == null || customer.isBlank()) {
            throw new IllegalArgumentException("Tên khách hàng không hợp lệ");
        }

        this.id = UUID.randomUUID();
        this.customer = customer;
        this.items = new ArrayList<>();
        this.status = OrderStatus.DRAFT;
    }

    public UUID getId() {
        return id;
    }

    public String getCustomer() {
        return customer;
    }

    public OrderStatus getStatus() {
        return status;
    }

    // Tạo một bản sao chỉ đọc để bên ngoài không sửa trực tiếp items.
    public List<String> getItems() {
        return List.copyOf(items);
    }

    public void addItem(String item) {
        ensureDraft();

        if (item == null || item.isBlank()) {
            throw new IllegalArgumentException("Tên mặt hàng không hợp lệ");
        }

        items.add(item);
    }

    public void confirm() {
        ensureDraft();

        if (items.isEmpty()) {
            throw new IllegalStateException(
                    "Đơn hàng phải có ít nhất một mặt hàng"
            );
        }

        status = OrderStatus.CONFIRMED;
    }

    public void cancel() {
        if (status != OrderStatus.CONFIRMED) {
            throw new IllegalStateException(
                    "Chỉ được hủy đơn hàng đã xác nhận"
            );
        }

        status = OrderStatus.CANCELLED;
    }

    private void ensureDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                    "Thao tác chỉ hợp lệ khi đơn hàng là DRAFT"
            );
        }
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
first == second: false
first == alias: true
first status: CONFIRMED
alias status: CONFIRMED
first items: [Sổ tay]
second items: []
first.equals(second): false
alias after cancel: CANCELLED
~~~

### Analyzing the Example

**Identity:** `first` and `second` are created by separate `new` expressions, so they are distinct instances even though they initially share a customer name, status, and empty item list. `alias` and `first` refer to the same instance, so `first == alias` is `true`. The `id` identifies an order at the business level but does not determine the result of the `==` reference comparison.

**State:** the `id`, `customer`, `items`, and `status` values describe the state of each `Order`. After `alias.addItem("Sổ tay")`, the item list seen through `first` changes, while `second` still has an empty list. After `first.confirm()`, `alias` sees status `CONFIRMED` because it references the same object.

**Behavior:** `addItem()`, `confirm()`, and `cancel()` are operations an `Order` object provides. They enforce business rules before modifying fields. The `getStatus()` and `getItems()` methods are queries that need not change state.

**Encapsulation:** fields are declared `private`; external code cannot write `first.status = ...` or directly insert an element into the internal list. Public methods provide controlled entry points for valid state changes. The example uses a `final class` to keep the design simple and prevent subclasses from changing its rules through inheritance.

### Behaviors Define State Transitions

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT: new Order(...)
    DRAFT --> DRAFT: addItem(item)
    DRAFT --> CONFIRMED: confirm() khi items không rỗng
    CONFIRMED --> CANCELLED: cancel()
~~~

The diagram shows only **implemented valid state transitions**. For example, `cancel()` in `DRAFT` or `addItem()` in `CONFIRMED` throws `IllegalStateException` rather than performing the requested transition. An object retains its identity throughout `DRAFT → CONFIRMED → CANCELLED`.

## 4. Identifying an Object Correctly

When tracking an object through state changes, ask **“Is this still the very same instance?”**. For two reference variables, Java uses `==` to answer that question. A **value-based** comparison, however, depends on the class's `equals()` contract:

~~~java
Order first = new Order("Lan");
Order alias = first;
Order another = new Order("Lan");

System.out.println(first == alias);   // true: cùng một instance
System.out.println(first == another); // false: hai instance
~~~

In the sample `Order` class, `equals()` is not overridden, so it also checks identity by default. For a value object such as `record Point(int x, int y) {}`, two different instances with the same coordinates can instead compare `equals()` as `true`.

**Business identity**, such as `orderId`, is another distinct concept: two Java objects loaded from the same record may have the same ID but be different instances. Do not use `System.identityHashCode()` as an order identifier: it is neither guaranteed unique nor persistent. When comparing values or using objects as collection keys, design `equals()/hashCode()` with a consistent contract. The lesson on *object identity versus value equality* explores this further.

## 5. State Is More Than the Value of One Variable

An object's state can include:

- **Simple values:** `int quantity`, `boolean active`, `OrderStatus status`.
- **References to other objects:** `List<String> items`, `Customer customer`, `Address shippingAddress`.
- **Derived values:** `getItemCount()` can calculate its result from `items.size()` instead of maintaining a separate counter field.

Each `Order` has its own `items` field. However, references are part of state: two objects *can still refer to the same list* if the program intentionally shares it. Thus, “each object has its own field” **does not mean** that all referenced data is automatically deep-copied.

### Example of Exposing Internal State

~~~java
class UnsafeCart {
    private final List<String> items = new ArrayList<>();

    public List<String> getItems() {
        return items; // Làm lộ danh sách có thể sửa.
    }
}
~~~

External code can then call `cart.getItems().add("Mặt hàng bất kỳ")` without passing through the rules in `addItem()`. This is **representation exposure**: the object loses control of its state.

In the sample `Order`, `List.copyOf(items)` provides a snapshot that cannot be modified through `List` operations. Because the elements are immutable `String` values, this works for the example. If the list contained *mutable* objects, copying the list alone would not guarantee **deep immutability**; consider defensive copies of the elements or making the elements immutable.

### Object Invariants

An invariant is a condition that must hold whenever an object is in a valid, usable state. For `Order`:

- `customer` must not be `null` or blank.
- `id` is initialized at construction and never reassigned.
- `items` must not contain blank or `null` item names.
- A `CONFIRMED` order must contain at least one item.
- No items can be added once the order leaves `DRAFT`.

The constructor establishes valid initial state, and state-changing methods are responsible for preserving the invariants. With data but no validating behavior, invalid state can spread throughout the system.

### `final` Does Not Automatically Make an Entire Object Immutable

~~~java
final class Notebook {
    private final List<String> pages = new ArrayList<>();

    public void addPage(String text) {
        pages.add(text); // Vẫn được: nội dung List thay đổi.
    }
}
~~~

A `final class` cannot be subclassed, while `final` on a reference field prevents that field from being reassigned. Neither **automatically** prevents modification of the referenced object's contents. An immutable object must be designed so that no observable state change is possible after construction, accounting for any references to mutable data.

## 6. Behavior Is a Contract, Not Just a Named Function

An object method generally has:

1. **Preconditions:** When is the call valid? For example, `confirm()` works only when the order is `DRAFT` and contains items.
2. **Effects:** What state changes or data does it return? For example, it changes `status` to `CONFIRMED`.
3. **Postconditions:** What must be true after success? For example, the order is confirmed and has at least one item.
4. **Invalid-case handling:** Throw an exception or return a structured error result according to the API's conventions.

**State-changing behavior** (command):

~~~java
order.addItem("Bút"); // Có thể làm thay đổi items.
order.confirm();       // Có thể đổi status.
~~~

**State-querying behavior** (query):

~~~java
OrderStatus current = order.getStatus();
List<String> lines = order.getItems();
~~~

In many designs, separating “commands” from “queries” makes code easier to understand and test: asking for state should not silently change observable state without a clear reason. This is a design guideline, not a restriction imposed by Java syntax.

### Why Does `this` Matter?

Inside an instance method, `this` refers to the object receiving the call:

~~~java
class Counter {
    private int value;

    public void increment() {
        this.value++;
    }

    public int getValue() {
        return this.value;
    }
}
~~~

~~~java
Counter a = new Counter();
Counter b = new Counter();

a.increment();
a.increment();
b.increment();

System.out.println(a.getValue()); // 2
System.out.println(b.getValue()); // 1
~~~

The method has the same implementation in the class, but each call acts on **a different receiving object**. Inside an instance method, `this.` can be omitted when names are unambiguous; explicitly writing `this.value` emphasizes that the field belongs to the object.

A `static` method has no implicit `this` and belongs to the class. For example, `main` is static because the JVM can invoke it without creating a `Demo` instance. When learning about object identity and state, do not confuse shared static fields with per-instance state.

## 7. Selecting Behavior Based on the Actual Object Type

OOP also lets a variable declared with an interface or superclass type reference objects of different concrete classes. When invoking an overridden instance method, Java selects the implementation based on **the actual object type** (*dynamic dispatch*).

~~~java
interface Notification {
    String message();
}

class EmailNotification implements Notification {
    @Override
    public String message() {
        return "Gửi email";
    }
}

class SmsNotification implements Notification {
    @Override
    public String message() {
        return "Gửi SMS";
    }
}

Notification channel = new SmsNotification();
System.out.println(channel.message()); // Gửi SMS.
~~~

Variable `channel` is declared as `Notification` but refers to a `SmsNotification` instance. The concrete type implements `message()`. Contrast this with `static` methods, which are not overridden through this dispatch mechanism.

### Identical Behavior Does Not Determine Identity

Two `SmsNotification` instances can both return the message “Send SMS” (translated from the example output) yet remain independent objects if constructed by two separate `new` expressions. Responding identically does not make `a == b` evaluate to `true`. Conversely, one object may respond differently over time as its state changes without losing its identity.

## 8. Methods Receiving Other Objects: Parameters Are Not the Caller's Variables

A method can receive a reference to another object. Java **always passes arguments by value**: when an argument is a reference, the method receives **a copy of that reference value**. The following methods belong inside a suitable Java class:

~~~java
static void addOne(Counter counter) {
    counter.increment(); // Sửa object được chia sẻ.
}

static void replace(Counter counter) {
    counter = new Counter(); // Chỉ gán lại tham số cục bộ.
}
~~~

When the caller passes the same `Counter`, `addOne` can increment it; `replace` does not reassign the caller's reference variable. Parameter passing, runnable examples, and swap scenarios are covered in *References, Values, and Passing Objects*. Here, connect that principle to behavioral responsibility: **Is the method allowed to modify the object it receives?**

## 9. Identity Exists Throughout an Instance's Lifetime

An object is created, initialized to a valid state, receives calls, and may change state repeatedly while remaining **the same instance**. Once it is no longer *reachable* from GC roots, the garbage collector may reclaim its memory at an unspecified time. Assigning `null` to one variable does not delete the object if another reference path still reaches it.

Java object identity applies to an instance's lifetime in the running JVM. To track an entity after reloading data or restarting the program, use a **business identifier** and explicitly persisted data. The lesson *Null Values and Objects That Do Not Exist* separately examines `null`, unassigned variables, and unreachable objects.

## 10. Keeping State and Behavior Consistent

An object with well-designed behavior enforces its stated *invariants*. When reviewing the `Order` design, ask:

1. **Who may change state?** Returning the internal `ArrayList` directly lets callers bypass `addItem()` validation. Return a snapshot or expose an appropriate public operation instead.
2. **Are method conditions clear?** `confirm()` succeeds only when the order is `DRAFT` and has items; invalid calls must produce consistent errors.
3. **Does observable information match the rules?** In this example, `getStatus()` must not silently alter state; `cancel()` must transition from `CONFIRMED` to `CANCELLED`.
4. **Can multiple threads update the same instance?** Checking and then writing inside separate methods does not automatically create an atomic operation. Concurrent access requires suitable ownership or synchronization.

`private` hides fields, and `final` prevents reassignment of reference fields; immutability and concurrency safety require broader design. These implementation decisions support **behavioral contracts** without changing `Order`'s identity.

## 11. Applying the Concepts to Real Problems

Consider a vending-machine management system:

| Entity | Identity | State | Behavior |
|---|---|---|---|
| `VendingMachine` | Unique machine identifier within the system | Remaining stock, held money, maintenance mode | `insertMoney()`, `selectProduct()`, `dispense()` |
| `BankAccount` | Business account number | Balance, frozen status | `deposit()`, `withdraw()`, `freeze()` |
| `GameCharacter` | Character ID | Health, location, equipment | `move()`, `attack()`, `heal()` |
| `Order` | Order ID | Items, processing status | `addItem()`, `confirm()`, `cancel()` |

When designing a class, ask three questions in order:

1. **Which object must be tracked as a distinct entity?** Define the identity boundary and whether a business ID is needed.
2. **Which data describes that object's state?** Identify its fields, relationships to other objects, and invariants to preserve.
3. **Which valid operations may affect that state?** Define meaningful domain methods, verify preconditions, and guarantee postconditions.

If an operation lives in another class but repeatedly needs all of an object's internal data to make decisions, reconsider whether the behavior belongs to the state-owning object. However, object collaboration, domain services, and persistence remain appropriate where rules do not belong exclusively to one entity.

## 12. Check Your Understanding

**Exercise 1: Two Variables—How Many Objects?**

~~~java
Order x = new Order("Minh");
Order y = x;
Order z = new Order("Minh");
~~~

Question: How many `Order` instances exist? What are the respective results of `x == y` and `x == z`?

**Answer:** There are two instances. `x == y` is `true` because they reference the same object; `x == z` is `false` because the objects were created separately.

**Exercise 2: Does Changing State Change Identity?**

~~~java
Order order = new Order("Hà");
Order savedRef = order;

order.addItem("Balo");
order.confirm();
~~~

Question: Is `savedRef == order` still `true`? What does `savedRef.getStatus()` return?

**Answer:** It remains `true`; `savedRef` sees status `CONFIRMED`. Updating state does not create a new object in this example.

**Exercise 3: Behavior and Invariants**

Question: Is `new Order("Hà").confirm()` valid?

**Answer:** No. The order has no items, so `confirm()` throws `IllegalStateException`. This behavior enforces the invariant that a confirmed order must contain at least one item.

**Exercise 4: Value Comparison**

~~~java
record Size(int width, int height) {}
Size a = new Size(10, 20);
Size b = new Size(10, 20);
~~~

Question: What do `a == b` and `a.equals(b)` return?

**Answer:** `false` and `true`, respectively. They are two instances representing the same value.

**Exercise 5: Does a Business ID Prove Two Variables Refer to the Same Object?**

Question: If two different `Order` objects are loaded from a database with the same `orderId`, must `==` return `true`?

**Answer:** No. The same business identifier can have multiple in-memory representations. Define ID-based comparison rules at the business level instead of confusing them with reference identity.

## Key Points to Remember

A **Java object** retains its identity throughout its lifetime, has state represented by its fields and related objects, and exposes behavior through methods. Many variables can refer to one object; many objects can have identical state. Well-designed behaviors control state transitions and maintain invariants. In OOP design, distinguishing **the same object**, **the same value**, and **the same business entity** prevents many problems in data handling, testing, and system integration.
