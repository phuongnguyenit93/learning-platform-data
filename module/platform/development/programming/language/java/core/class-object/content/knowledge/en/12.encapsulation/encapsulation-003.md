# Getters and Setters: Purpose, Limitations, and When They Are Not Needed in Java

In object-oriented programming with Java, a **getter** is a method that provides the ability to *read* part of an object's state; a **setter** is a method typically used to *modify* a property of an object. They are common tools to support **encapsulation**, but **simply having a field does not require creating both `getX()` and `setX()`**.

A truly well-encapsulated class does not just hide fields with `private` and provide public methods to read and write every value. That class must **decide what the outside is allowed to know and allowed to modify**, protect valid state conditions (*invariants*), control the mutable objects it holds, and expose operations that align with business semantics.

For example, a bank account may allow reading the balance via `getBalance()`, but **should not expose `setBalance(...)` for callers to arbitrarily assign a number**. The `deposit(...)` and `withdraw(...)` APIs express valid actions more accurately.

This lesson is for **Java 17+**; it covers how to create getters/setters, their purpose, limitations, when they are unnecessary, the difference between field access and method access, validation, defensive copying, immutable objects, records, JavaBeans conventions, mutable objects, inheritance, and concurrency. All complete programs state compilation instructions and stdout.

## 1. What Are Getters and Setters?

A class with state:

~~~java
class Student {
    private String name;
    private int age;
}
~~~

Both fields are declared `private`; code outside the class cannot directly write `student.name` or `student.age`.

If you want to expose read access to the name and age, and allow changing the name according to a contract, you can add:

~~~java
class Student {
    private String name;
    private int age;

    Student(String name, int age) {
        setName(name);
        setAge(age);
    }

    public String getName() {
        return name;
    }

    public int getAge() {
        return age;
    }

    public void setName(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        this.name = name;
    }

    private void setAge(int age) {
        if (age < 0 || age > 150) {
            throw new IllegalArgumentException("Tuổi không hợp lệ");
        }
        this.age = age;
    }
}
~~~

This is a **class declaration snippet**, without a `main` method to run standalone. Breakdown:

- `getName()` returns the name of the current object; the caller has permission to **read** the exposed information.
- `setName(...)` validates the input and then updates the field; the caller is allowed to **request a name change according to rules** rather than touching the field directly.
- `getAge()` publicly exposes read access for age.
- `setAge(...)` is marked `private` only to illustrate that **it is not necessary to expose a setter for every field**. The constructor can use this internal method to validate the initial value.
- Outside the class, code still cannot write `student.age = -20;` or call `student.setAge(20)` because there is no appropriate public access.

**Getters and setters are ordinary methods**, not special syntax that the Java compiler automatically generates for every field. The names `getName` and `setName` are common conventions; Java does not require all getters to be named that way.

## 2. Encapsulation Is Not Just `private` Fields and a Full Set of Getters/Setters

Encapsulation can be understood through two goals:

1. **Hide internal representation:** external code does not need to know which fields exist, or how data is computed or cached.
2. **Protect behavior and valid state:** external code may only perform operations that the class actually supports, so that invariants are maintained.

A poor example:

~~~java
class BadBankAccount {
    private long balance;

    public long getBalance() {
        return balance;
    }

    public void setBalance(long balance) {
        this.balance = balance;
    }
}
~~~

This class uses a `private` field but exposes `setBalance` unconditionally. Callers can write:

~~~java
account.setBalance(-1000);
account.setBalance(1_000_000_000L);
~~~

If business rules do not allow a negative balance or require balance changes to correspond to a transaction, this API has permitted an invalid state/action. Getters/setters **do not automatically guarantee encapsulation**.

A more suitable design:

~~~java
class BankAccount {
    private long balance;

    BankAccount(long openingBalance) {
        if (openingBalance < 0) {
            throw new IllegalArgumentException("Số dư âm");
        }
        balance = openingBalance;
    }

    public long getBalance() {
        return balance;
    }

    public void deposit(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Số tiền phải dương");
        }
        balance = Math.addExact(balance, amount);
    }

    public void withdraw(long amount) {
        if (amount <= 0 || amount > balance) {
            throw new IllegalArgumentException("Rút tiền không hợp lệ");
        }
        balance -= amount;
    }
}
~~~

The class exposes two **business operations**, instead of a setter granting full authority to assign the balance. Calling `deposit(100)` expresses the intent to deposit money; `withdraw(30)` expresses the intent to withdraw money; these methods can enforce validation, auditing, access control, or other logic later on.

**Principle:** do not equate "hiding fields" with "controlling state changes". The API should make it **hard for users to perform incorrect behavior** and **easy to perform correct behavior**.

## 3. Getters Provide Read Access, but Do Not Necessarily Return Raw Fields

A getter can:

- Return a primitive or immutable value.
- Return a value computed from fields.
- Return a copy of mutable data.
- Return a view or read-only structure according to the contract.
- Perform permission checks or format conversion if the API genuinely needs it.
- Withhold sensitive data that the class must keep confidential.

Example of a getter that computes a value:

~~~java
class Rectangle {
    private final int width;
    private final int height;

    Rectangle(int width, int height) {
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException("Cạnh phải dương");
        }
        this.width = width;
        this.height = height;
    }

    public long getArea() {
        return (long) width * height;
    }
}
~~~

`getArea()` **has no corresponding `area` field**. It computes the value from the two fields; casting to `(long)` before multiplication helps avoid `int` integer overflow in the intermediate multiplication step (for two positive `int` values, the largest result still lies within the `long` range).

If the class later changes how it stores dimensions or caches the result while still guaranteeing the `getArea()` contract, callers do not need to modify their logic just because internal fields changed.

### 3.1. Getters for Primitives and Immutable Objects Are Usually Simple

~~~java
class Product {
    private final String sku;
    private final int quantity;

    Product(String sku, int quantity) {
        this.sku = java.util.Objects.requireNonNull(sku);
        this.quantity = quantity;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }
}
~~~

Returning `int` returns a primitive value; callers cannot modify the field simply by reassigning the variable that receives the result. Returning `String` is also generally safe regarding **String content**, because String is immutable. However, not every reference type is immutable: a getter directly returning a `List`, an array, a `Date`, or a mutable object can expose internal state.

### 3.2. A Getter Does Not Necessarily Need to Exist

If a class only needs to perform an action and callers have no legitimate need to read a separate field, **there is no mandatory reason to create a getter**. For example, a class holding secret credentials to send requests can use the credentials internally without exposing `getPassword()`.

Getters are also part of the **API contract**: exposing too much data makes callers depend on implementation details and makes changing the internal structure harder later on.

## 4. Setters Provide Conditional Modification Access

A good setter is typically responsible for:

1. **Validating input** according to business rules (non-null, non-blank, within the allowed range).
2. **Maintaining relationships between the object's fields**.
3. **Not leaving the object in an invalid state** if the operation fails.
4. **Reporting clear errors** when the caller makes an invalid request.
5. **Determining side effects**: whether to emit notifications, invalidate caches, audit, or persist data.

Example:

~~~java
class Course {
    private String title;

    Course(String title) {
        setTitle(title);
    }

    public void setTitle(String title) {
        if (title == null) {
            throw new IllegalArgumentException("title null");
        }

        String normalized = title.trim();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("title rỗng");
        }

        this.title = normalized;
    }

    public String getTitle() {
        return title;
    }
}
~~~

`setTitle` validates, normalizes, and only then assigns the field. If the argument is invalid, the method throws `IllegalArgumentException` before changing `title`. Callers cannot directly assign an empty title through the field because it is private.

**Point to consider:** silently normalizing with `trim()` is part of the contract. If leading/trailing whitespace has business meaning, it must not be removed just because the setter's author thinks it "should be clean".

### 4.1. Setters Are Not Required to Be Named `setX()` If the Business Operation Is an Action

`setQuantity(100)` conveys the message "set the current quantity to 100". If the actual operation is adding stock, `increaseStock(100)` expresses it more accurately. If the operation is closing an account, `close()` is better than `setStatus("CLOSED")` when the state transition requires conditions.

Method names are part of the API design language. You should not call every command a setter if the action involves **business logic**, **state transition rules**, or **affecting multiple fields**.

## 5. Complete Example: Not Using `setBalance` for an Account

Create the file **`EncapsulationDemo.java`**:

~~~java
public class EncapsulationDemo {
    static final class BankAccount {
        private final String id;
        private long balance;

        BankAccount(String id, long openingBalance) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("ID không hợp lệ");
            }
            if (openingBalance < 0) {
                throw new IllegalArgumentException("Số dư âm");
            }
            this.id = id;
            this.balance = openingBalance;
        }

        public String getId() {
            return id;
        }

        public long getBalance() {
            return balance;
        }

        public void deposit(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("Tiền gửi phải dương");
            }
            this.balance = Math.addExact(this.balance, amount);
        }

        public void withdraw(long amount) {
            if (amount <= 0 || amount > balance) {
                throw new IllegalArgumentException("Số tiền rút sai");
            }
            this.balance -= amount;
        }
    }

    public static void main(String[] args) {
        BankAccount account = new BankAccount("TK-01", 100);

        System.out.println("Account = " + account.getId());
        System.out.println("Initial = " + account.getBalance());

        account.deposit(50);
        account.withdraw(20);
        System.out.println("After transactions = " + account.getBalance());

        try {
            account.withdraw(1_000);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }

        System.out.println("Final = " + account.getBalance());
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 EncapsulationDemo.java
java EncapsulationDemo
~~~

**Exact stdout:**

~~~text
Account = TK-01
Initial = 100
After transactions = 130
Rejected = Số tiền rút sai
Final = 130
~~~

**Analysis:**

1. The constructor requires a non-blank id and a non-negative opening balance; the object is created successfully with a valid state.
2. `getId()` and `getBalance()` provide the necessary public data without granting permission to assign to the fields.
3. `deposit(50)` adds 50 while checking for a positive amount and `long` overflow via `Math.addExact`; the balance increases from 100 to 150.
4. `withdraw(20)` subtracts 20 after checking bounds, leaving a balance of 130.
5. `withdraw(1_000)` exceeds the balance, so an exception occurs before modifying the field. The catch block prints the fixed message; the final state remains 130.
6. **There is no `setBalance(...)`** because callers must not arbitrarily change the balance. There is no `setId(...)` because the id is determined at creation time and the field is `final`.

This example illustrates a basic object API. In a real transaction system, you also need access control, reconciliation, persistence, concurrency, idempotency, and other business conditions; `private` fields do not replace them on their own.

## 6. A Major Limitation of Getters: Leaking References to Mutable State

One of the most dangerous encapsulation bugs is a getter **directly returning a mutable object** held internally:

~~~java
import java.util.ArrayList;
import java.util.List;

class UnsafeTeam {
    private final List<String> members = new ArrayList<>();

    public List<String> getMembers() {
        return members; // Returns the internal mutable list directly
    }
}
~~~

Callers can execute:

~~~java
UnsafeTeam team = new UnsafeTeam();
team.getMembers().add("Lan");
team.getMembers().clear();
~~~

Even though the `members` field is `private final`, the List object referenced by the field **can still be modified**. No setter needs to exist for the caller to gain the ability to mutate state!

**`final` protects against reassigning the field reference; it does not make the referenced object immutable.** A public getter returning a mutable reference can defeat the purpose of encapsulation even if the field is declared private.

### 6.1. Getters Returning a Snapshot

One way to handle this when a list contains immutable elements such as `String`:

~~~java
import java.util.ArrayList;
import java.util.List;

class Team {
    private final List<String> members = new ArrayList<>();

    void addMember(String member) {
        if (member == null || member.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        members.add(member);
    }

    public List<String> getMembers() {
        return List.copyOf(members);
    }
}
~~~

`List.copyOf` (Java 10+) returns an unmodifiable List that rejects mutating operations and does not contain null. Because the source is a mutable `ArrayList`, the result is a structural snapshot of the list at the time of copying; callers cannot add to or remove from this result to modify the original list.

Important notes:

- `List.copyOf` **does not deep-copy element objects**. With a `List<MutableEmployee>`, callers can modify the shared MutableEmployee objects if the API exposes them.
- `Collections.unmodifiableList(original)` creates an **unmodifiable view through the view**, but if `original` changes elsewhere, the view can reflect those changes; it is not synonymous with a snapshot.
- `new ArrayList<>(members)` creates a mutable snapshot that is **structurally** independent, though callers can modify their own copy; that may be completely appropriate if the intent is to return data for callers to process.
- If state changes concurrently across threads, creating a consistent snapshot also requires a synchronization contract or an appropriate concurrency structure; `List.copyOf` does not make the entire class thread-safe by itself.

### 6.2. For Arrays, Getters Should Also Consider Copying

~~~java
class Scores {
    private final int[] marks;

    Scores(int[] marks) {
        this.marks = marks.clone();
    }

    public int[] getMarks() {
        return marks.clone();
    }
}
~~~

This is a declaration snippet. For `int[]`, cloning copies the array and its primitive values, helping prevent callers from modifying the internal array. The constructor also clones **the input**, because if only the getter cloned while retaining the original array passed by the caller, the caller could still mutate the internal array via the initial reference.

If the input can be null, you must specify whether to reject or handle null; the example uses `marks.clone()`, so it will throw an NPE if null is passed. When writing production APIs, add appropriate validation and messages.

### 6.3. Mutable Elements Require Deeper Protection

~~~java
class Item {
    String name;

    Item(String name) {
        this.name = name;
    }
}

class Catalog {
    private final java.util.List<Item> items;

    Catalog(java.util.List<Item> source) {
        this.items = java.util.List.copyOf(source);
    }

    java.util.List<Item> getItems() {
        return items;
    }
}
~~~

The returned List is **structurally unmodifiable**, but a caller holding an `Item` from `source` can still execute `item.name = ...` if access permissions allow it, and that Item's state changes inside the catalog. This is a **shallow copy**. For invariants that require stabilizing element contents as well, use immutable value objects, copy each element, or design clear ownership.

## 7. Complete Example: Safe Getters and Validated Setters

Create the file **`SafeAccessorsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SafeAccessorsDemo {
    static final class Team {
        private String name;
        private final List<String> members;

        Team(String name, List<String> source) {
            this.members = List.copyOf(source);
            for (String member : this.members) {
                if (member.isBlank()) {
                    throw new IllegalArgumentException("Tên thành viên rỗng");
                }
            }
            setName(name);
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Tên nhóm không hợp lệ");
            }
            this.name = name.trim();
        }

        public List<String> getMembers() {
            return members;
        }

        public int getSize() {
            return members.size();
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(
                List.of("Lan", "Mai"));
        Team team = new Team("Java", source);

        source.clear();
        source.add("Changed");

        System.out.println("Team = " + team.getName());
        System.out.println("Members = " + team.getMembers());
        System.out.println("Size = " + team.getSize());

        team.setName("  Backend  ");
        System.out.println("Renamed = " + team.getName());

        try {
            team.setName("  ");
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }

        try {
            team.getMembers().add("An");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Cannot edit members");
        }

        System.out.println("Final members = " + team.getMembers());
        System.out.println("Final name = " + team.getName());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 SafeAccessorsDemo.java
java SafeAccessorsDemo
~~~

**Exact stdout:**

~~~text
Team = Java
Members = [Lan, Mai]
Size = 2
Renamed = Backend
Rejected = Tên nhóm không hợp lệ
Cannot edit members
Final members = [Lan, Mai]
Final name = Backend
~~~

**Explanation:**

1. The constructor uses `List.copyOf(source)` to snapshot the list structure; when the caller modifies `source`, the team's state does **not** change.
2. `getMembers()` returns the stored unmodifiable list, preventing callers from altering its structure via `add` or `remove`.
3. `getSize()` computes the count from the list without needing a separate `size` field.
4. `setName("  Backend  ")` normalizes it to `"Backend"`; this is the behavior specified by the method.
5. `setName("  ")` fails **before the assignment**, so `name` remains `Backend`.
6. `getMembers().add("An")` throws `UnsupportedOperationException`; the example catches the error to print a stable message without depending on a stack trace.

**Illustration limitation:** the List elements are immutable `String` instances, so structural copying is appropriate. If the elements are mutable objects, you must check for deep immutability. `List.copyOf` also throws an NPE if source is null or contains a null element; you must add an explicit contract/validation if the API requires a different message.

## 8. A Standalone Setter Can Break Multi-Field Invariants

A class often has conditions involving **multiple properties**; for example, a valid date range requires `start <= end`. If two independent setters are exposed, callers can force the object through an invalid intermediate state.

Example of a design prone to problems:

~~~java
import java.time.LocalDate;

class UnsafeRange {
    private LocalDate start;
    private LocalDate end;

    UnsafeRange(LocalDate start, LocalDate end) {
        this.start = start;
        this.end = end;
    }

    public void setStart(LocalDate start) {
        this.start = start;
    }

    public void setEnd(LocalDate end) {
        this.end = end;
    }
}
~~~

This class performs no validation, so `start > end` is possible. Even if checks are added to each setter, replacing the entire range may still require changing **both values at once**. For example, if the current range is from day 10 to 20 and you want to move it to 30 to 40, if `setStart(30)` requires start <= the current end, the first step will be rejected even though the new pair of values is completely valid.

### 8.1. A Command That Updates Both Properties Together

~~~java
import java.time.LocalDate;
import java.util.Objects;

class DateRange {
    private LocalDate start;
    private LocalDate end;

    DateRange(LocalDate start, LocalDate end) {
        reschedule(start, end);
    }

    public void reschedule(LocalDate nextStart, LocalDate nextEnd) {
        Objects.requireNonNull(nextStart, "nextStart");
        Objects.requireNonNull(nextEnd, "nextEnd");

        if (nextEnd.isBefore(nextStart)) {
            throw new IllegalArgumentException("Khoảng ngày không hợp lệ");
        }

        this.start = nextStart;
        this.end = nextEnd;
    }

    public LocalDate getStart() {
        return start;
    }

    public LocalDate getEnd() {
        return end;
    }
}
~~~

`reschedule` validates **the entire new pair**, and then assigns the state. In single-threaded access, callers avoid errors caused by the order of calling two setters. `LocalDate` is immutable, so having getters return references to them is appropriate.

**Concurrency note:** the two field assignments in the `reschedule` method are **not an atomic transaction across threads**. If multiple threads can read and write concurrently, you need synchronization, a lock, or to store the entire range in an immutable object and replace the whole reference according to a safe protocol.

### 8.2. An Immutable Type Is Even Simpler When Modification After Creation Is Unnecessary

~~~java
import java.time.LocalDate;
import java.util.Objects;

record DateRangeValue(LocalDate start, LocalDate end) {
    DateRangeValue {
        Objects.requireNonNull(start, "start");
        Objects.requireNonNull(end, "end");
        if (end.isBefore(start)) {
            throw new IllegalArgumentException("Khoảng ngày không hợp lệ");
        }
    }
}
~~~

Record `DateRangeValue` has final components per record rules, provides `start()` and `end()` accessors, and has no setters. When a new date range is needed, create a new valid instance instead of partially mutating the old one.

For a large class or an object with many cross-field constraints, a **constructor/factory/builder** that produces a valid state is usually more appropriate than a sequence of arbitrary setters.

## 9. When Should You **Not** Create a Setter?

There is no rule saying "every class must have both getters and setters". Typical situations where setters are not needed:

### 9.1. Values That Can Only Be Established at Object Creation

~~~java
class Employee {
    private final String employeeId;

    Employee(String employeeId) {
        if (employeeId == null || employeeId.isBlank()) {
            throw new IllegalArgumentException("ID không hợp lệ");
        }
        this.employeeId = employeeId;
    }

    public String getEmployeeId() {
        return employeeId;
    }
}
~~~

A `final` field is appropriate when identity must not change after creation. `setEmployeeId(...)` would contradict that contract, so no setter is provided.

### 9.2. Fields Computed from Other State

~~~java
class Basket {
    private final java.util.List<String> items =
            new java.util.ArrayList<>();

    public int getItemCount() {
        return items.size();
    }
}
~~~

The count is derived from the list. There is no need for `setItemCount(int)` because callers cannot arbitrarily demand "count = 100" without changing the actual number of items. If items need to be added or removed, use controlled `addItem(...)` and `removeItem(...)` methods.

### 9.3. Changes Requiring a Business Operation

An order moves through the states `NEW → PAID → SHIPPED` subject to conditions. A `setStatus(Status)` API could allow callers to jump straight from NEW to SHIPPED, bypassing checks. Methods like `pay()` and `ship()` reflect **state transition rules** more clearly.

### 9.4. Immutable Objects or Value Objects

A `Money` object consisting of currency and amount can be immutable. To increase the amount, use `plus(...)` returning a new object; a setter on Money is not necessary. Immutable design makes reasoning, caching, and data sharing easier and avoids many bugs caused by aliasing.

### 9.5. Setters That Expose Internal Mechanisms Without External Meaning

A class with a `cachedValue` field purely for optimization probably should not expose `setCachedValue(...)`. Callers only need the computation method, while the cache is an implementation detail.

**Deciding question:** *Does the caller have a valid, meaningful behavior that requires reassigning that exact property?* If not, do not automatically generate a setter.

## 10. When Are Getters **Not** Needed?

Getters are not mandatory by default either:

- **Sensitive data:** credentials, secret keys, and internal tokens should not be returned arbitrarily without a clear need.
- **Implementation-only data:** caches, internal flags, algorithms, locks, and intermediate results are not part of the contract.
- **Data that should be expressed as behavior:** instead of exposing `getInternalList()` and having the caller compute, you can provide `containsItem(x)` or `totalPrice()`.
- **Information that only needs limited exposure:** return `getMaskedCardNumber()` rather than the raw card number when appropriate.
- **No need to expose state for the object to do its job:** an internal service can provide `execute()` without exposing every dependency via getters.

### 10.1. Getters for Every Field Easily Create an "Anemic Domain Model"

A class that is merely a set of fields with getters/setters, while all business rules live in another service, easily causes **logic about the same state to become scattered**:

~~~java
class Order {
    private int quantity;
    private long unitPrice;

    public int getQuantity() { return quantity; }
    public void setQuantity(int value) { quantity = value; }

    public long getUnitPrice() { return unitPrice; }
    public void setUnitPrice(long value) { unitPrice = value; }
}
~~~

In a complex domain model, this style of design can allow negative quantity, negative price, or overflow calculation bugs. Consider `changeQuantity(...)` methods with validation, `total()` with proper calculation, and a constructor that establishes invariants.

However, **not every data class with getters/setters is wrong**. A simple DTO mainly transferring data between layers can be reasonable when it owns no business behavior. What matters is the **role of the class**, not mechanically banning a code pattern.

## 11. Records in Java 17: Accessors Without JavaBeans Setters

A record lets you concisely declare an immutable data type over its **component fields**:

~~~java
public record UserView(String name, int age) {
    public UserView {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên rỗng");
        }
        if (age < 0) {
            throw new IllegalArgumentException("Tuổi âm");
        }
    }
}
~~~

This is a **standalone record**; to compile, save it in `UserView.java`.

The compiler generates component accessors matching the component names:

~~~java
UserView user = new UserView("Lan", 20);

System.out.println(user.name()); // Lan
System.out.println(user.age());  // 20
~~~

Records **do not automatically generate `getName()` or `setName(...)`** like JavaBeans. `name()` and `age()` are the standard record accessors; the corresponding record components are private final fields, and the object has no auto-generated setters.

If you want to change the age, you can create a new record:

~~~java
UserView next = new UserView(user.name(), 21);
~~~

Note: records provide **shallow immutability**. If a component has a mutable `List<String>` type, the record does not automatically deep-copy the List. A compact constructor can handle this with `List.copyOf` or appropriate validation/immutable modeling. Returning a mutable List component through an accessor can still expose element or structural state if left unprotected.

### 11.1. Example with a Record Containing a Collection

~~~java
import java.util.List;

record CourseView(String code, List<String> tags) {
    CourseView {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code rỗng");
        }
        tags = List.copyOf(tags);
    }
}
~~~

This is a declaration snippet. In a compact constructor, reassigning the `tags` parameter to a snapshot is accepted; after the body, the record fields are assigned from the component parameters according to Java rules. Because `String` is immutable and the copied List is unmodifiable, callers cannot use the source list to mutate the structure of the record's tags list.

## 12. JavaBeans Conventions: Property-Based Getter/Setter Naming

Some Java tools use **JavaBeans** conventions to discover "properties". Common conventions:

| Purpose | Common method name |
| --- | --- |
| Read property `name` | `getName()` |
| Write property `name` | `setName(String value)` |
| Read boolean property `active` | `isActive()` or `getActive()` depending on convention/tool |
| Read-only | Getter without a public setter |
| Write-only in certain tool models | Setter without a getter; should not be assumed to be a good API by default |
| Record component `name` | `name()` (differs from classic JavaBeans naming) |

Example:

~~~java
class UserBean {
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

This is an illustrative class. Bean conventions support **introspection**, binding, serialization/mapping, input interfaces, or libraries that rely on property names.

**Do not equate JavaBeans with mandatory rules for every Java class:**

- Java allows methods named `name()`, `rename(...)`, or `isAvailable()` if they are valid in syntax and types.
- JavaBeans typically expects specific signatures such as parameterless `getX()` and single-parameter `setX(value)` with a `void` return type on standard setters; a fluent setter `setX(...)` returning `this` may not be recognized by some libraries under the convention.
- A Boolean field of wrapper type `Boolean` that can be `null` may require a different way of declaring the getter than a primitive `boolean` to avoid unexpected unboxing; check framework requirements.
- Record accessors differ from classic JavaBeans getters; modern frameworks may support records through various paths, but **do not infer that every library will understand `name()` as `getName()`**.
- Some frameworks utilize field access, constructor binding, or annotations instead of necessarily needing public setters.

If a project uses a framework, follow the **specific contract of that framework's version and configuration** rather than letting tool conventions impose unnecessary setters onto the entire domain model.

## 13. DTOs, Entities, and Domain Objects Do Not Share the Same Accessor Needs

### 13.1. DTO (Data Transfer Object)

A DTO that transfers data between layers or across APIs typically has explicit fields/properties, where getters and setters can be useful for serialization/deserialization libraries or form binding. Example:

~~~java
class UserForm {
    private String name;
    private Integer age;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

This is an illustrative data class containing no business logic. `Integer` allows representing "age not yet entered" as null; validation is needed when converting the form into a domain object with strong invariants.

### 13.2. Entity/Domain Model

A domain entity has an identity and a lifecycle, usually needing **controlled business behavior** rather than unconstrained setters. For example, `Order.pay()` changes state conditionally better than `setPaid(true)` when payment checks are involved.

### 13.3. Persistence/Serialization Frameworks

Some libraries/ORMs require constructors, fields, methods, or annotations following certain conventions. For example, JPA entities typically have a public/protected no-arg constructor per the specification, yet **that does not mean every entity field must have a public setter**; field/property access mechanisms and proxies have their own conditions.

You should separate:

1. The **business contract** of the domain object.
2. The **data mapping contract** required by the persistence/serialization framework.
3. The **data exposure format** for external clients to use.

When these requirements conflict, you can use an appropriate DTO, mapper, factory, or constructor binding, rather than opening uncontrolled state mutation on the domain object just to satisfy a tool.

## 14. Getters and Setters Do Not Determine Inheritance or Overriding on Their Own

An ordinary getter/setter is an instance method and can be overridden if it is not `private`, `static`, or `final` and satisfies inheritance rules.

~~~java
class BaseProfile {
    protected String name = "Base";

    public String getName() {
        return name;
    }
}

class NamedProfile extends BaseProfile {
    @Override
    public String getName() {
        return "Named:" + super.getName();
    }
}
~~~

With `new NamedProfile().getName()`, the result is `Named:Base`. A getter called on a variable with static type `BaseProfile` but a runtime object of `NamedProfile` can dispatch to the override.

This matters inside constructors:

~~~java
class Base {
    Base() {
        // avoid calling overridable getter/setter here
    }
}
~~~

**Do not call overridable setters/getters from a constructor when logic depends on subclass state**. The superclass constructor may dispatch to the subclass override before subclass fields finish initializing, leading to null/default values or unintended side effects.

In a constructor, prefer directly validating parameters and assigning state, or calling an appropriate `private`/`static`/`final` helper. There is no technical requirement that every field assignment from a constructor must go through a public setter.

## 15. Getters and Setters Do Not Automatically Provide Thread Safety

Suppose:

~~~java
class UnsafeCounter {
    private int value;

    public int getValue() {
        return value;
    }

    public void setValue(int value) {
        this.value = value;
    }
}
~~~

`private`, getters, and setters **do not automatically guarantee correctness when multiple threads share an object**. With two threads, data races and visibility issues can occur. An operation `setValue(getValue() + 1)` consists of at least two method calls and is not an atomic increment.

Example:

~~~java
class AtomicCounter {
    private final java.util.concurrent.atomic.AtomicInteger value =
            new java.util.concurrent.atomic.AtomicInteger();

    public int getValue() {
        return value.get();
    }

    public int increment() {
        return value.incrementAndGet();
    }
}
~~~

The `increment()` method provides **atomic increment** behavior for the counter, better than an unprotected read-modify-write combination of a getter and setter. There is no need for `setValue(...)` if callers are only allowed to increment the count.

If multiple fields must maintain an invariant together, a single atomic field on its own **does not automatically make the entire object thread-safe**. Define synchronization boundaries by business operation, using locks or immutable snapshots properly.

### 15.1. `volatile` on a Field Does Not Replace Validation or Invariants

A `volatile int value` field supports certain visibility rules, yet `value++` is still not an atomic read-modify-write operation. Adding `volatile` does not turn getters/setters into a transaction, nor does it allow omitting business conditions.

## 16. Choosing Immutable Objects Instead of Unconstrained Setters

When data primarily represents a **value** rather than a mutable entity, an immutable design is often sensible:

~~~java
final class Point {
    private final int x;
    private final int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    public int getX() { return x; }

    public int getY() { return y; }

    public Point movedBy(int dx, int dy) {
        return new Point(
                Math.addExact(x, dx),
                Math.addExact(y, dy));
    }
}
~~~

This is a declaration snippet. `Point` has no setters. `movedBy(...)` creates a new object with the new coordinates, keeping the old object unchanged. Such a design is usually easier to share because callers cannot alter the state of an existing Point through a setter.

**This does not mean every object should be immutable.** An entity representing a changing shopping cart may need update commands. Yet even for a mutable entity, changes should occur through **meaningful behavior**, not necessarily per-field setters.

### 16.1. With Records, Create a New Version

~~~java
record Coordinate(int x, int y) {
    Coordinate movedBy(int dx, int dy) {
        return new Coordinate(
                Math.addExact(x, dx),
                Math.addExact(y, dy));
    }
}
~~~

`Coordinate` is a Java 17 record; it has `x()` and `y()` accessors and no setters. `movedBy` returns a new record instead of mutating the current record's state.

## 17. A Complete Example of Updating Related State Together

Create the file **`RangeUpdateDemo.java`**:

~~~java
import java.time.LocalDate;

public class RangeUpdateDemo {
    static final class DateRange {
        private LocalDate start;
        private LocalDate end;

        DateRange(LocalDate start, LocalDate end) {
            reschedule(start, end);
        }

        public LocalDate getStart() {
            return start;
        }

        public LocalDate getEnd() {
            return end;
        }

        public void reschedule(LocalDate nextStart, LocalDate nextEnd) {
            if (nextStart == null || nextEnd == null) {
                throw new IllegalArgumentException("Ngày null");
            }
            if (nextEnd.isBefore(nextStart)) {
                throw new IllegalArgumentException(
                        "Khoảng ngày không hợp lệ");
            }
            this.start = nextStart;
            this.end = nextEnd;
        }

        public String summary() {
            return start + " -> " + end;
        }
    }

    public static void main(String[] args) {
        DateRange range = new DateRange(
                LocalDate.of(2026, 1, 10),
                LocalDate.of(2026, 1, 20));

        System.out.println("Before = " + range.summary());

        range.reschedule(
                LocalDate.of(2026, 1, 30),
                LocalDate.of(2026, 2, 5));

        System.out.println("After = " + range.summary());

        try {
            range.reschedule(
                    LocalDate.of(2026, 3, 10),
                    LocalDate.of(2026, 3, 1));
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }

        System.out.println("Final = " + range.summary());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 RangeUpdateDemo.java
java RangeUpdateDemo
~~~

**Exact stdout:**

~~~text
Before = 2026-01-10 -> 2026-01-20
After = 2026-01-30 -> 2026-02-05
Rejected = Khoảng ngày không hợp lệ
Final = 2026-01-30 -> 2026-02-05
~~~

In this example, the class has **getters to read both values**, but no independent `setStart` and `setEnd`. The `reschedule` method is a meaningful command that accepts both new values and checks **the relationship between them** before assigning. When validation fails, both start and end keep their previous data.

Once again, if multiple threads read and write the object concurrently, assigning two reference fields requires a synchronization strategy; this example only illustrates invariants in a single-threaded context.

## 18. Choosing an API Across Real-World Scenarios

| State/behavior | What to consider | Why |
| --- | --- | --- |
| ID determined at creation | Getter, no setter | Immutable ID of the instance |
| Modifiable display name | Getter + validated setter or `rename(...)` | Valid and meaningful change |
| Account balance | Getter + `deposit/withdraw` | Prevents arbitrary assignment breaking transactions |
| Number of elements in collection | Getter computing `size()`, no `setSize` | Derived value |
| Internal mutable list | Getter returning snapshot/immutable data | Avoids exposing mutable reference |
| Date range with start/end relation | `reschedule(start,end)` or immutable value | Must validate the pair together |
| Data-transfer DTO | JavaBeans-style getters/setters if framework needs | Simple data transfer contract |
| Immutable value object | Constructor/record accessors, no setter | State does not change after creation |
| Internal cache/lock | No public getter/setter | Implementation detail |
| Counter incremented by multiple threads | `increment()` with atomic/synchronization | Read-modify-write must be atomic |
| Password/secret | Do not arbitrarily expose raw getter | Maintains security boundary |
| Workflow status | Commands `approve()`, `cancel()` | Prevents invalid state transitions |

### 18.1. Should a Setter Return `void` or `this`?

In standard JavaBeans style, a setter has the form:

~~~java
public void setName(String name) {
    this.name = name;
}
~~~

A fluent setter can be written:

~~~java
public Builder setName(String name) {
    this.name = name;
    return this;
}
~~~

Both are **valid Java methods**, but some tools that identify properties by return-type and naming conventions may handle them differently. If the API targets a framework requiring bean conventions, consult the framework documentation; if the API targets a fluent builder, you can use `withName(...)` or `name(...)` to clearly express the design.

### 18.2. Should You Use `setX` with Validation?

You can. A validated setter is valid when the business purpose is genuinely to **change property X**. However, when the change affects multiple fields, requires transaction history, or has invariants spanning multiple fields, a specialized command makes it easier to uphold the contract.

### 18.3. Should a Getter Perform I/O or Mutate Significant State?

A method named `getX()` typically creates the expectation of **reading**. A getter that performs network access, mutates substantial state, or throws unexpected errors makes it hard for callers to predict behavior. Lazy initialization/caching is sometimes reasonable, but you should consider thread safety, exception behavior, performance, and documentation. If the operation is genuinely expensive or has clear side effects, names like `load...`, `fetch...`, or `refresh...` may be more suitable.

## 19. Common Mistakes

1. **Generating getters/setters for every field just because the IDE has Generate.** The IDE saves typing; it **does not decide the public API contract** for you.
2. **Thinking a `private` field + arbitrary public setter is good encapsulation.** The setter can still break invariants.
3. **Using setters instead of business commands.** `setBalance` and `setStatus` can let callers perform invalid actions.
4. **Moving all validation to the caller.** Other callers may forget to check; the class must protect its own invariants.
5. **Directly returning a mutable List/array from a getter.** Callers can modify the internal object through the reference.
6. **Copying only the input without checking what the getter returns.** Callers can still mutate internal state through the getter.
7. **Copying only in the getter without copying mutable input.** Callers can keep the input reference and modify the object's data after the constructor.
8. **Believing `final List` is an immutable list.** Final only prevents reassigning the field reference.
9. **Believing `Collections.unmodifiableList(source)` is always a snapshot.** It can be a view that reflects changes in the source.
10. **Believing `List.copyOf` deep-copies each mutable element.** It protects the structure but does not deep-copy element objects.
11. **Creating separate setters for two related fields.** A single update step can produce an invalid invariant or make valid state transitions hard to perform.
12. **Exposing a setter for a derived field like `count`.** State can contradict the underlying data.
13. **Arbitrarily calling overridable setters inside a constructor.** It can dispatch into the subclass before initialization completes.
14. **Assuming getters/setters are automatically thread-safe.** They do not synchronize or create atomic transactions on their own.
15. **Assuming records automatically have JavaBeans `getX()/setX()`.** Records have component accessors `x()` by default and no setters.
16. **Assuming every interface or framework requires public setters.** Requirements depend on the mapping model, configuration, and version.
17. **Using getters to return sensitive data without access control.** This can leak information that the API should not expose.
18. **Using a setter to emit events or save to the DB without stating it clearly.** Callers cannot anticipate side effects, performance, and errors.

## 20. Self-Check Exercises with Answers

**Question 1.** Why do `private long balance` and `public void setBalance(long x)` not inherently guarantee encapsulation?

**Answer:** Because callers still retain the ability to arbitrarily assign to the state via the setter; without invariants and business validation, the object can enter an invalid business state. Consider `deposit`/`withdraw` if those are the actual actions.

**Question 2.** If the getter `getMembers()` directly returns an internal mutable `List<String> members`, what can the caller do?

**Answer:** The caller can call `clear`/`add` on the returned List, modifying the internal state even though the field is private and final. A snapshot, immutable list, or controlled API is needed.

**Question 3.** If a getter returns `List.copyOf(members)`, can the caller modify mutable element objects?

**Answer:** Yes, if the elements are mutable objects and the caller holds references to them. `List.copyOf` does not create a deep copy of every element object.

**Question 4.** Does a `private final String id` field need a setter?

**Answer:** Usually not, if id is an immutable identifier. The constructor/factory creates the object with a valid id, and a getter can provide the id if callers need to read it.

**Question 5.** Does `getArea()` strictly require an `area` field?

**Answer:** No. The getter can compute the area from `width` and `height`, without needing redundant state.

**Question 6.** Why should a date-range object not always expose independent `setStart` and `setEnd`?

**Answer:** Because the invariant `start <= end` involves two fields; updating one field at a time can pass through an invalid state or cause a valid pair change to be blocked. Consider a `reschedule(start,end)` command or an immutable value.

**Question 7.** Does a Java record `record User(String name)` automatically generate `getName()` and `setName()`?

**Answer:** No. A record has the standard accessor `name()`; it does not auto-generate setters, and component fields are final per record rules.

**Question 8.** Might a DTO used with a binding framework need setters?

**Answer:** Possibly, depending on the framework/configuration. However, do not apply that requirement mechanically to every domain entity; DTOs and domain objects can be separated.

**Question 9.** Does `setCount(getCount() + 1)` increment atomically when multiple threads call it concurrently?

**Answer:** No. That is a read/compute/write sequence; synchronization or an atomic operation such as `AtomicInteger.incrementAndGet()` is required.

**Question 10.** Must `public String getPassword()` always exist just because a `password` field exists?

**Answer:** No. If it is secret data, the API usually should not expose the raw value unconditionally; the class only needs to support safe behaviors with appropriate access control.

**Question 11.** Is a setter `setTitle("  Java  ")` that automatically runs `trim` to produce `"Java"` correct?

**Answer:** Yes, if the class contract specifies such normalization. No, if whitespace is meaningful data that callers expect to be preserved.

**Question 12.** Given `private List<String> list` and a `getList()` method returning a `Collections.unmodifiableList(list)`, does that guarantee a snapshot that will not change later?

**Answer:** No. This can be an unmodifiable **view** of the original list; if the original list changes, the view still reflects it. For a structural snapshot, consider `List.copyOf` or an equivalent copy.

**Question 13.** What risk can occur when a constructor calls a public setter in a class that allows inheritance?

**Answer:** The setter may be overridden by a subclass and dynamically dispatched during superclass initialization, when subclass fields are not ready yet. Use a non-overridable helper or controlled initialization logic.

**Question 14.** Does a getter `getBalance()` mean the caller is allowed to modify the balance?

**Answer:** No. A getter only provides a read value according to the contract; a setter or command for modification is a separate API decision.

## 21. Checklist for Choosing Getters/Setters for a Java Class

Before clicking "Generate Getters and Setters" in your IDE, ask yourself:

1. **Class responsibility:** is this a DTO, value object, entity, or service? They have different needs for exposing state.
2. **Does the getter have a valid purpose?** Does the caller genuinely need to read the value or just a more abstract behavior?
3. **Does the getter leak a mutable reference or sensitive data?** Consider a snapshot, immutable view, derived data, or not exposing it.
4. **Does the setter represent a valid operation?** If not, choose a business-named command or remove the setter.
5. **Does validation belong to the class?** The class must protect its own invariants even if callers forget to check.
6. **Does one setter need to change multiple fields at once?** Use a method that updates the entire state if needed.
7. **Are there final or computed fields?** Usually do not create setters for them.
8. **Should the state be immutable?** A constructor, record, or method returning a new object can be simpler.
9. **Is there mutable object aliasing?** Check both incoming data and outgoing data.
10. **Is there framework code requiring bean conventions?** Check the exact contract of the framework rather than exposing setters across the board.
11. **Could a subclass override the method?** Avoid calling overridable accessors from an uncontrolled constructor.
12. **Do multiple threads access it?** Getters/setters do not replace a concurrency protocol.
13. **Are there side effects or I/O?** Name and document the actual contract.
14. **Is the public API durable?** Once callers depend on a method, changing access/name/behavior can cause a breaking change.

**Conclusion:** Getters and setters are **tools** for encapsulation, not the **goal** of encapsulation. A getter gives callers the ability to observe part of the state; a setter provides an update path. When data should not be modified arbitrarily, **no setter is needed**; when state should not be exposed, **no getter is needed**. A well-designed Java class exposes **exactly what callers need**, validates permitted changes, and preserves its invariants, rather than mechanically copying a `getX/setX` pair for every field.
