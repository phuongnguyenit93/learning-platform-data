# Distinguishing Concrete Classes from Abstract Classes in Java OOP

A system may support several notification channels: email, SMS, and in-app notifications. All must validate input, but the actual delivery mechanisms differ. In Java, an **abstract class** describes shared behavior and the parts that subclasses must complete; a **concrete class** provides complete implementations so it can be instantiated and perform its work.

The key is not "which class is better" but **each class's role in the design**:

- An abstract class describes an object type that is *not yet complete enough for direct use*; it may provide shared code and state.
- A concrete class fully implements every remaining abstract method and can be instantiated with `new` if its constructor is accessible.
- Consuming code can depend on the abstract parent type while actual objects are instances of concrete subclasses.

## 1. Identifying Classes by Their Syntax

~~~java
// Lớp trừu tượng: không tạo instance trực tiếp bằng new Vehicle().
abstract class Vehicle {
    abstract void move(); // Chưa có phần thân
}

// Lớp cụ thể: đã triển khai hành vi còn thiếu.
class Bicycle extends Vehicle {
    @Override
    void move() {
        System.out.println("Đạp xe");
    }
}
~~~

~~~java
Vehicle vehicle = new Bicycle(); // Hợp lệ
vehicle.move();                   // In: Đạp xe

// Vehicle v = new Vehicle();     // Lỗi biên dịch
Bicycle bicycle = new Bicycle();  // Hợp lệ
~~~

`vehicle` has the **declared type** `Vehicle`, but the object created by `new Bicycle()` is a **concrete Bicycle**. When an overridden instance method is called, Java selects the implementation based on the object's actual type (dynamic polymorphism).

Java has no `concrete` keyword. A class is concrete if it **does not declare `abstract`**, fulfills all inherited abstract-method obligations, and can be instantiated when the access rules allow.

| Criterion | Abstract class | Concrete class |
| --- | --- | --- |
| Declaration | Uses `abstract class` | `class` without `abstract` |
| Direct `new` of the class | No | Yes, if constructor and access permissions allow |
| May have unimplemented methods (`abstract method`) | May or may not | Cannot leave any inherited abstract methods unimplemented |
| May contain fields, constructors, and implemented methods | Yes | Yes |
| Can be extended | Yes, unless otherwise restricted | Yes, unless declared `final` |
| Can serve as a reference type | Yes | Yes |
| Can support polymorphism | Commonly | Can be either parent class or subclass |

**Two common misconceptions:** an abstract class **does not have to** contain an `abstract` method, and a concrete class **does not have to** declare its own methods if it inherits all required implementations.

## 2. Complete Example: Standardizing Notification Delivery

The problem: every channel must validate `recipientId` and `content` before sending. Email and SMS then have different delivery mechanisms. We put the shared process in an abstract class and require each concrete subclass to implement the delivery step.

Save as **`NotificationDemo.java`**. The code is compatible with Java 11+ and uses only the standard library:

~~~java
import java.util.List;
import java.util.Objects;

public class NotificationDemo {

    // Abstract class: biểu diễn một kênh thông báo chưa xác định cách gửi.
    static abstract class NotificationChannel {
        private final String channelName;

        protected NotificationChannel(String channelName) {
            this.channelName = Objects.requireNonNull(
                    channelName, "channelName");
        }

        public final String getChannelName() {
            return channelName;
        }

        // Quy trình chung; final để lớp con không bỏ qua bước kiểm tra.
        public final void send(String recipientId, String content) {
            String id = Objects.requireNonNull(
                    recipientId, "recipientId").trim();
            String message = Objects.requireNonNull(
                    content, "content").trim();

            if (id.isEmpty() || message.isEmpty()) {
                throw new IllegalArgumentException(
                        "Người nhận và nội dung không được rỗng");
            }

            deliver(id, message); // Chọn triển khai của lớp con thực tế.
        }

        // Hợp đồng bắt buộc: lớp cụ thể phải triển khai.
        protected abstract void deliver(
                String recipientId, String content);
    }

    static final class EmailChannel extends NotificationChannel {
        EmailChannel() {
            super("EMAIL");
        }

        @Override
        protected void deliver(String recipientId, String content) {
            System.out.println("[EMAIL] tới " + recipientId
                    + ": " + content);
        }
    }

    static final class SmsChannel extends NotificationChannel {
        SmsChannel() {
            super("SMS");
        }

        @Override
        protected void deliver(String recipientId, String content) {
            System.out.println("[SMS] tới " + recipientId
                    + ": " + content);
        }
    }

    public static void main(String[] args) {
        List<NotificationChannel> channels = List.of(
                new EmailChannel(),
                new SmsChannel()
        );

        for (NotificationChannel channel : channels) {
            System.out.println("Đang dùng: "
                    + channel.getChannelName());
            channel.send("KH-001", "Đơn hàng đã xác nhận");
        }

        // new NotificationChannel("UNKNOWN"); // KHÔNG biên dịch
    }
}
~~~

~~~bash
javac NotificationDemo.java
java NotificationDemo
~~~

Output:

~~~text
Đang dùng: EMAIL
[EMAIL] tới KH-001: Đơn hàng đã xác nhận
Đang dùng: SMS
[SMS] tới KH-001: Đơn hàng đã xác nhận
~~~

The example simulates delivery in the console to demonstrate OOP; `KH-001` is a sample recipient ID, not an actual email address or phone number. A production channel would map that ID to contact details, invoke the appropriate provider, and handle errors.

In the example, `NotificationChannel` and its two subclasses are defined as **nested `static` classes** so everything fits into one file. In a real project, they can be split into separate files while preserving the inheritance relationships.

### What Role Does Each Component Play?

**`NotificationChannel` is the abstract class:**

- Has a `private final String channelName` field and a `protected` constructor to initialize shared state from subclasses.
- Fully implements `getChannelName()` and `send(...)`.
- `send(...)` validates inputs and calls `deliver(...)`.
- Declares `protected abstract void deliver(...)`: every channel *must deliver*, but the base class does not know *how*.

**`EmailChannel` and `SmsChannel` are concrete classes:**

- Inherit shared data and workflow from `NotificationChannel`.
- Call `super("EMAIL")` or `super("SMS")` to initialize the parent portion.
- Use `@Override` to implement `deliver(...)` for each channel.
- Can be instantiated using `new EmailChannel()` and `new SmsChannel()`.

**`List<NotificationChannel>` demonstrates polymorphism:**

- The list holds references declared with the **abstract parent type**.
- Each element refers to an instance of a concrete subclass.
- `channel.send(...)` invokes the shared workflow; inside it, `deliver(...)` is dispatched to the corresponding `EmailChannel` or `SmsChannel`.

## 3. Tracing the Call with a Sequence Diagram

~~~mermaid
sequenceDiagram
    actor App as Main
    participant Channel as NotificationChannel (API chung)
    participant Email as EmailChannel instance

    App->>Channel: send("KH-001", "Đơn hàng đã xác nhận")
    Note over Channel,Email: send() là phương thức chung final<br/>được thừa kế bởi EmailChannel
    Channel->>Channel: kiểm tra id và nội dung
    Channel->>Email: deliver(id, message) (dynamic dispatch)
    Email-->>Channel: hoàn tất
    Channel-->>App: hoàn tất
~~~

`Channel` in the diagram represents the **parent-class/API role in the call**; at runtime, `send()` executes on a concrete `EmailChannel` object. No standalone `NotificationChannel` instance is created using `new NotificationChannel()`.

This is a simple form of the **Template Method** pattern: the parent owns the workflow skeleton (`send`), while subclasses implement a variable step (`deliver`). Not every program using an abstract class must apply Template Method; this is just one appropriate use.

## 4. "Abstract" at the Class and Method Levels

Distinguish the two concepts.

### Abstract Classes

~~~java
abstract class AuditService {
    void record(String message) {
        System.out.println("Audit: " + message);
    }
}
~~~

This class **has no abstract methods**, yet it is still abstract because it is declared as such. We may want to prevent instantiating an overly general `AuditService`, allowing only versions with a clear purpose:

~~~java
class FileAuditService extends AuditService {
    // Kế thừa record(); không bắt buộc thêm phương thức mới.
}
~~~

`FileAuditService` is concrete even though it overrides nothing:

~~~java
AuditService audit = new FileAuditService();
audit.record("Đăng nhập");
~~~

### Abstract Methods

~~~java
abstract class Report {
    abstract String render(); // Không có phần thân phương thức.
}
~~~

A class with an `abstract` instance method **must itself be declared `abstract`**. Its subclasses have two choices:

1. Implement all remaining abstract methods to become concrete classes.
2. Continue to declare themselves `abstract` if they do not yet implement everything.

~~~java
abstract class BaseReport {
    abstract String render();
}

abstract class BrandedReport extends BaseReport {
    // Vẫn chưa triển khai render(), nên phải là abstract.
}

class SalesReport extends BrandedReport {
    @Override
    String render() {
        return "Doanh thu tháng này";
    }
}
~~~

Inheritance may span many levels; **only methods that still lack implementations** remain obligations for a concrete subclass. If another parent class already provides a valid implementation, a subclass need not rewrite it.

## 5. Constructors and Shared State in Abstract Classes

A common misconception is that "abstract classes cannot be instantiated, so they have no constructors". In fact, **abstract classes can have constructors**, which run as part of creating a subclass instance.

~~~java
abstract class Employee {
    private final String id;

    protected Employee(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("ID không hợp lệ");
        }
        this.id = id;
        System.out.println("Khởi tạo phần Employee");
    }

    public final String getId() {
        return id;
    }

    public abstract BigDecimal calculateSalary();
}

class SalariedEmployee extends Employee {
    private final BigDecimal monthlySalary;

    public SalariedEmployee(String id, BigDecimal salary) {
        super(id); // Phải khởi tạo phần Employee trước.
        this.monthlySalary = salary;
    }

    @Override
    public BigDecimal calculateSalary() {
        return monthlySalary;
    }
}
~~~

*This example requires `import java.math.BigDecimal;` when placed in an actual Java file.*

When calling `new SalariedEmployee("E001", ...)`, Java creates **one SalariedEmployee object** whose state includes fields declared throughout the inheritance chain; the parent constructor runs before the subclass constructor body. It **does not create two independent instances**, one `Employee` and one `SalariedEmployee`.

A subclass cannot directly access its parent's `private` fields, but it can use suitable `public`/`protected` methods exposed by the parent.

### Why Avoid Calling Overridable Methods from Constructors?

The subclass object **may not yet be fully initialized** while the parent constructor runs. If the parent calls an overridable method, Java can dispatch to the subclass override before the subclass fields have their expected values.

~~~java
abstract class Base {
    Base() {
        // Nguy hiểm nếu gọi overridableMethod() ở đây.
    }

    abstract void overridableMethod();
}
~~~

In real designs, have constructors establish the invariants of their own state; avoid allowing `this` to escape or invoking subclass behavior before initialization is complete.

## 6. Common Java Rules and Compilation Errors

| Rule | Invalid or valid example | Explanation |
| --- | --- | --- |
| Do not instantiate an abstract class directly | `new NotificationChannel(...)` | There is no concrete class to instantiate |
| A class containing an abstract method must itself be abstract | `class A { abstract void run(); }` | `A` must become `abstract class A` |
| A concrete class must implement remaining abstract methods | `class B extends A { }` when `A.run()` is abstract | Implementation is missing |
| Abstract methods have no body | `abstract void run() { }` | An abstract declaration ends with `;` |
| Do not combine `abstract` and `final` on a class | `abstract final class A` | One requires subclasses while the other forbids inheritance |
| Do not combine `abstract` with `private`, `static`, or `final` on methods | `private abstract void run();` | Abstract methods must be overridable |
| Abstract classes may have `final` methods | `public final void send(...)` | Valid: fixes the shared workflow |
| Constructors cannot be abstract | `abstract A();` | Constructors initialize objects; they are not overridden |
| Do not reduce access visibility when overriding | Override `public` with `protected` | Invalid because it narrows the contract |
| Concrete classes may be `final` | `final class EmailChannel extends NotificationChannel` | Complete and cannot be extended further |

**Tip:** always use `@Override` on methods intended to implement an override. The compiler will detect misspelled names or signatures that fail to override.

Example:

~~~java
abstract class Animal {
    abstract void makeSound();
}

// LỖI nếu bỏ comment và biên dịch:
// class Cat extends Animal {
//     void makesSound() { } // Sai tên; makeSound() vẫn chưa triển khai.
// }
~~~

Correct version:

~~~java
class Cat extends Animal {
    @Override
    void makeSound() {
        System.out.println("Meo");
    }
}
~~~

Be careful: an abstract class may certainly contain `static` methods. Abstract classes **can have implemented static methods**. What is invalid is a method declared both `static` and `abstract`, because static methods are not overridden like instance methods.

## 7. How Do Abstract Classes and Interfaces Differ?

To understand why an abstract class is needed, compare it with an `interface`. Both can express a **contract** that concrete classes must satisfy, but their inheritance mechanisms differ.

| Criterion | Abstract class | Interface |
| --- | --- | --- |
| Typical purpose | Share state/implementation among closely related classes | Describe a capability that many classes can provide |
| Instance fields | Can hold mutable/immutable instance fields | No instance fields; interface fields are `public static final` |
| Constructors | Yes | No |
| Implemented methods | Yes, at any valid access level | Supports `default`, `static`, and `private` (depending on Java version) |
| Relationship to a Java class | `extends` at most one immediate class | `implements` multiple interfaces |
| Direct instantiation | No | No |
| Sharing common code | Appropriate with a natural inheritance relationship | Can use a `default method`, or composition with a helper/service |

Example of an independent capability:

~~~java
interface Trackable {
    String trackingCode();
}

abstract class Shipment {
    protected final String id;

    protected Shipment(String id) {
        this.id = id;
    }

    abstract int estimateDays();
}

class ExpressShipment extends Shipment implements Trackable {
    ExpressShipment(String id) {
        super(id);
    }

    @Override
    int estimateDays() {
        return 1;
    }

    @Override
    public String trackingCode() {
        return "EXP-" + id;
    }
}
~~~

`ExpressShipment` both inherits shared state from `Shipment` and promises the `Trackable` capability. If two types lack a meaningful "is-a" relationship, composition (`has-a`) or an interface may be more flexible than forcing inheritance from a shared abstract class.

## 8. When to Choose an Abstract Class or a Concrete Class

The choice usually starts with **actual needs**:

- **Concrete class:** when a type already defines complete behavior and is valid to instantiate directly. For example, `EmailChannel` knows how to implement `deliver`.
- **Abstract class:** when subclasses belong to the same family and should share state or workflow while specializing some steps. For example, `NotificationChannel` defines `send` but not `deliver`.
- **Interface:** when unrelated types should support the same capability without necessarily sharing an inheritance tree. For example, `Trackable`.
- **Composition:** when capabilities need to vary independently, or inheritance would tightly couple parent and child classes. For example, `NotificationService` receives a `NotificationChannel` through its constructor instead of extending a channel class.

Marking a class `abstract` just to "make it look more OOP" can add pointless complexity. Conversely, if several classes duplicate a workflow while varying only one step, an abstract class with clear responsibilities can reduce duplication and centralize rules.

Consider also an application that currently has **just one** notification channel with no known need for variation: a simple concrete class may be sufficient. Once multiple delivery methods share a stable workflow, extract an abstraction based on actual commonalities.

### Polymorphism Does Not Require an Abstract Class

Example:

~~~java
class Printer {
    void print() {
        System.out.println("Mặc định");
    }
}

class ColorPrinter extends Printer {
    @Override
    void print() {
        System.out.println("Có màu");
    }
}

Printer p = new ColorPrinter();
p.print(); // Có màu
~~~

`Printer` is a **concrete** class but still serves as a parent type for polymorphism. `abstract` only means the parent cannot be instantiated directly or has an incomplete contract; it is not required for inheritance or overriding.

## 9. Exercises: Identify Errors and Explain Results

**Question 1.** Does the following code compile?

~~~java
abstract class A {
    void hello() { System.out.println("Hello"); }
}
class B extends A { }
~~~

**Answer:** Yes. `B` inherits the implemented `hello()` method and need not override it; `B` is concrete. `new B().hello()` prints `Hello`.

**Question 2.** Does the following code compile?

~~~java
abstract class Shape {
    abstract double area();
}
class Square extends Shape { }
~~~

**Answer:** No. `Square` has not implemented `area()` and is not declared `abstract`. It must override the method:

~~~java
class Square extends Shape {
    private final double side;

    Square(double side) {
        if (side <= 0) throw new IllegalArgumentException("side");
        this.side = side;
    }

    @Override
    double area() {
        return side * side;
    }
}
~~~

**Question 3.** In `NotificationDemo`, `send()` is `final`. How can `EmailChannel` still change the delivery behavior?

**Answer:** `send()` fixes the shared processing steps but invokes `deliver()`, an abstract method overridden in the subclass. Calling `deliver()` on a concrete instance selects the corresponding subclass implementation.

**Question 4.** Does `NotificationChannel channel = new SmsChannel();` create an instance of the abstract class?

**Answer:** No. The actual object is `SmsChannel`, while the `channel` reference is declared with the abstract parent type to use the shared contract.

**Question 5.** Can an abstract class have `private` fields, constructors, static methods, final methods, and no abstract methods?

**Answer:** Yes. `abstract` at the class level only prevents direct instantiation and allows the class to serve as a base for subclasses; it does not require any abstract methods.

**Question 6.** Does adding `PushChannel` require changes to `NotificationChannel.send()`?

**Suggested answer:** Usually not if the common workflow remains valid. Create `PushChannel extends NotificationChannel`, call the parent constructor, and override `deliver()`. This shows the value of separating **stable shared behavior** from **specific extension points**.

## Key Points for Reading OOP Designs

Focus on three things: **which class the `new` expression instantiates**, **the declared type of the reference variable**, and **whether a called method has a shared implementation or still requires an override**.

Abstract classes reuse shared behavior and define required extension points; concrete classes turn that contract into functioning objects. Effective design places shared behavior appropriately, keeps variations in implementations, and avoids inheritance hierarchies without a clear purpose.
