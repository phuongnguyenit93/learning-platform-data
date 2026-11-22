# Superclasses, Subclasses, and Inheritance in Java OOP

**Inheritance** allows a new class to **extend or specialize** an existing class. The inherited-from class is the **superclass** (*superclass/parent class*), while the inheriting class is the **subclass** (*subclass/child class*). Java uses `extends` to declare inheritance between two classes.

Inheritance is useful when objects of different concrete types share a **common nature** and follow the same behavioral contract. For example, salaried and hourly employees are both **employees** with IDs, names, and payable wages, but their pay calculations differ.

The decisive benefit is not merely reducing repeated code. Inheritance establishes an **is-a** relationship: a subclass object should be usable wherever a superclass object is expected without violating the superclass contract.

## 1. Identifying Superclasses and Subclasses

A short example:

~~~java
class Vehicle {
    void start() {
        System.out.println("Khởi động phương tiện");
    }
}

class Car extends Vehicle {
    void openTrunk() {
        System.out.println("Mở cốp xe");
    }
}
~~~

~~~java
Car car = new Car();
car.start();     // Phương thức kế thừa từ Vehicle
car.openTrunk(); // Phương thức riêng của Car

Vehicle vehicle = car; // Hợp lệ: Car là một Vehicle
vehicle.start();       // Hợp lệ
// vehicle.openTrunk(); // Không biên dịch: Vehicle không khai báo phương thức này
~~~

Here:

- `Vehicle` is the **superclass** of `Car`.
- `Car` is the **subclass** of `Vehicle`.
- `Car extends Vehicle` means that “`Car` is a kind of `Vehicle`.”
- `Car` can reuse inherited behavior while adding behavior of its own.
- A `Vehicle` reference can point to a `Car` instance. The compiler determines **which methods can be called** from the variable's declared type; for overridden instance methods, runtime dispatch chooses **which implementation executes** according to the object's actual type.

Diagram of the type relationship:

~~~mermaid
classDiagram
    class Vehicle {
        +start() void
    }
    class Car {
        +openTrunk() void
    }
    Vehicle <|-- Car
~~~

The hollow triangular arrow points from the **subclass to the superclass**. It represents inheritance between *types*, not the existence of two separate objects every time `new Car()` is evaluated.

## 2. Practical Example: Calculating Pay for Two Employee Types

Requirements:

- Every employee has an identifier and full name.
- A **salaried** employee receives a fixed monthly salary.
- An **hourly** employee has an hourly rate and number of hours worked.
- The system prints pay slips without repeatedly checking employee types with `if` statements.

Design:

~~~mermaid
classDiagram
    class Employee {
        <<abstract>>
        -id String
        -fullName String
        +getId() String
        +getFullName() String
        +role() String
        +monthlyPay() BigDecimal*
        +printPayslip() void
    }
    class SalariedEmployee {
        -fixedSalary BigDecimal
        +role() String
        +monthlyPay() BigDecimal
    }
    class HourlyEmployee {
        -hourlyRate BigDecimal
        -hoursWorked int
        +role() String
        +monthlyPay() BigDecimal
    }
    Employee <|-- SalariedEmployee
    Employee <|-- HourlyEmployee
~~~

Here, `Employee` is an **abstract superclass** because a generic employee has no concrete pay formula. The two subclasses provide their own implementations.

### Standalone Runnable Java Example

Save all the following code as `InheritanceDemo.java` (Java 11+):

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

public class InheritanceDemo {

    static abstract class Employee {
        private final String id;
        private final String fullName;

        protected Employee(String id, String fullName) {
            this.id = requireText(id, "id");
            this.fullName = requireText(fullName, "fullName");
        }

        public final String getId() {
            return id;
        }

        public final String getFullName() {
            return fullName;
        }

        public String role() {
            return "Nhân viên";
        }

        // Mỗi loại nhân viên có công thức lương riêng.
        public abstract BigDecimal monthlyPay();

        // Quy trình chung không thay đổi giữa các lớp con.
        public final void printPayslip() {
            System.out.println(role() + " | " + id + " | "
                    + fullName + " | "
                    + monthlyPay().toPlainString());
        }

        private static String requireText(String text, String field) {
            String result = Objects.requireNonNull(
                    text, field).trim();
            if (result.isEmpty()) {
                throw new IllegalArgumentException(
                        field + " không được rỗng");
            }
            return result;
        }
    }

    static final class SalariedEmployee extends Employee {
        private final BigDecimal fixedSalary;

        SalariedEmployee(String id, String name,
                         BigDecimal fixedSalary) {
            super(id, name); // Khởi tạo phần Employee trước.
            Objects.requireNonNull(fixedSalary, "fixedSalary");
            if (fixedSalary.signum() < 0) {
                throw new IllegalArgumentException(
                        "Lương cố định không được âm");
            }
            this.fixedSalary = fixedSalary;
        }

        @Override
        public String role() {
            return "Toàn thời gian";
        }

        @Override
        public BigDecimal monthlyPay() {
            return fixedSalary;
        }
    }

    static final class HourlyEmployee extends Employee {
        private final BigDecimal hourlyRate;
        private final int hoursWorked;

        HourlyEmployee(String id, String name,
                       BigDecimal hourlyRate, int hoursWorked) {
            super(id, name);
            Objects.requireNonNull(hourlyRate, "hourlyRate");
            if (hourlyRate.signum() < 0 || hoursWorked < 0) {
                throw new IllegalArgumentException(
                        "Đơn giá và số giờ không được âm");
            }
            this.hourlyRate = hourlyRate;
            this.hoursWorked = hoursWorked;
        }

        @Override
        public String role() {
            return "Theo giờ";
        }

        @Override
        public BigDecimal monthlyPay() {
            return hourlyRate.multiply(
                    BigDecimal.valueOf(hoursWorked));
        }
    }

    public static void main(String[] args) {
        Employee a = new SalariedEmployee(
                "E001", "An", new BigDecimal("15000000"));
        Employee b = new HourlyEmployee(
                "E002", "Bình", new BigDecimal("75000"), 80);

        List<Employee> staff = List.of(a, b);

        for (Employee employee : staff) {
            employee.printPayslip();
        }

        System.out.println("Tổng lương: "
                + staff.stream()
                        .map(Employee::monthlyPay)
                        .reduce(BigDecimal.ZERO, BigDecimal::add)
                        .toPlainString());
    }
}
~~~

Compile and run:

~~~bash
javac InheritanceDemo.java
java InheritanceDemo
~~~

Output:

~~~text
Toàn thời gian | E001 | An | 15000000
Theo giờ | E002 | Bình | 6000000
Tổng lương: 21000000
~~~

To focus on inheritance, this example calculates only basic pay, excluding tax, insurance, overtime, pay periods, and multiple currencies. Real systems must model and validate those rules according to domain requirements.

### Responsibility Breakdown

| Component | What belongs here? | Why? |
| --- | --- | --- |
| `Employee` | `id`, `fullName`, shared validation, `printPayslip()` | All employees need this data and behavior |
| `Employee.monthlyPay()` | Abstract method declaration | Every employee must have a way to calculate pay, but no single formula applies |
| `SalariedEmployee` | `fixedSalary`, fixed-pay calculation | Relevant only to salaried employees |
| `HourlyEmployee` | `hourlyRate`, `hoursWorked`, multiplication | Relevant only to hourly employees |
| `List<Employee>` | Instances of multiple subclasses | Reuses the superclass API through polymorphism |

There is no `new Employee()` call: since `Employee` is declared `abstract`, it **cannot be instantiated directly**. A superclass that provides complete behavior without being `abstract` can be concrete and still have subclasses.

## 3. What Does a Subclass Object Inherit?

An `HourlyEmployee` instance contains state declared throughout **both its superclass and subclass hierarchy**:

- The `Employee` portion: `id`, `fullName`.
- The `HourlyEmployee` portion: `hourlyRate`, `hoursWorked`.
- Inherited/exposed methods such as `getId()`, `getFullName()`, and `printPayslip()`.
- Overridden methods such as `role()` and `monthlyPay()`.

~~~mermaid
flowchart TB
    R["Một instance HourlyEmployee"]
    R --> A["Phần trạng thái Employee\nid, fullName"]
    R --> B["Phần trạng thái HourlyEmployee\nhourlyRate, hoursWorked"]
    R --> C["Hành vi được chọn\nmonthlyPay() của HourlyEmployee"]
~~~

This is a **conceptual** diagram, not a JVM memory-layout map. Creating a subclass object does not create two independent objects (an `Employee` and an `HourlyEmployee`).

The superclass's `private` fields **still exist in the instance's state**, but subclass code cannot access them directly by field name. Instead of `this.id` in `HourlyEmployee`, use the superclass getter `getId()`.

### Why Is `private` Still Useful with Inheritance?

If subclasses could freely assign `id`, they could violate employee-ID rules. `Employee` owns the invariant and shared validation. Declaring `id` as `private final` and exposing only a getter lets the superclass retain control.

Common access levels:

| Access level of a superclass member | From a subclass |
| --- | --- |
| `public` | Accessible according to public access rules |
| `protected` | Accessible to subclasses; outside the package, qualifier expressions have additional restrictions |
| No modifier (package-private) | Directly accessible only from the same package |
| `private` | Not directly accessible from subclass code |

`protected` does not mean “public to all subclass code under every circumstance.” Java applies specific access rules, particularly across packages. Prefer keeping fields `private` and exposing intentional operations over sharing all state with the hierarchy.

## 4. Subclass Constructors Initialize Superclass State

Constructors are not inherited methods. When creating `HourlyEmployee`, `super(id, name)` selects an `Employee` constructor to initialize shared data; then the subclass constructor validates `hourlyRate` and `hoursWorked`:

~~~java
HourlyEmployee(String id, String name,
               BigDecimal hourlyRate, int hoursWorked) {
    super(id, name); // Gọi constructor Employee(String, String).
    // Kiểm tra, sau đó gán các trường riêng của HourlyEmployee.
}
~~~

In Java 11, an explicit `super(...)`/`this(...)` invocation must appear first in a constructor. Without `super(...)`, the compiler attempts `super()`, which is valid only if an accessible no-argument superclass constructor exists. `new HourlyEmployee(...)` still creates **one object**, not a separate `Employee` instance.

Avoid calling overridable methods from superclass constructors: dynamic dispatch may reach subclass methods while subclass fields still hold their default values. Static initializers, field initializers, instance blocks, and constructor order are examined in **Subclass initialization and the superclass constructor chain**.

## 5. Method Overriding (`@Override`) Changes Behavior

Inheritance does not mean “subclasses must keep every superclass behavior unchanged.” A subclass can **override** an overridable instance method to provide specialized behavior.

In the payroll example:

~~~java
@Override
public BigDecimal monthlyPay() {
    return hourlyRate.multiply(
            BigDecimal.valueOf(hoursWorked));
}
~~~

The two subclasses have the same **method signature** and compatible return types for the `Employee.monthlyPay()` contract, but use different algorithms.

When writing:

~~~java
Employee employee = new HourlyEmployee(
        "E003", "Hà", new BigDecimal("100000"), 20);

System.out.println(employee.monthlyPay()); // 2000000
~~~

Although `employee` is declared as `Employee`, Java invokes `HourlyEmployee.monthlyPay()` because the object's **actual runtime type** is `HourlyEmployee`. This is **runtime polymorphism** for overridden instance methods.

A subclass can also invoke its superclass implementation through `super.method()` when the superclass provides one:

~~~java
class Person {
    String describe() {
        return "Một người";
    }
}

class Student extends Person {
    @Override
    String describe() {
        return super.describe() + " đang học";
    }
}
~~~

~~~java
Person p = new Student();
System.out.println(p.describe()); // Một người đang học
~~~

Here, `super.describe()` directly invokes the superclass method implementation from subclass code; it differs from `super(...)`, which invokes a superclass constructor.

### `@Override` Helps Detect Mistakes

~~~java
class Base {
    void calculate() {}
}

class Derived extends Base {
    @Override
    void calcuate() {} // LỖI: sai tên, không thực sự override
}
~~~

The `@Override` annotation makes the compiler report misspellings instead of silently defining a new method. Use it whenever overriding is intended.

Basic overriding rules:

- The name and parameter list must match an overridable method.
- The return type must be compatible (possibly covariant for reference types).
- Access visibility cannot be reduced; for example, a `public` method cannot be overridden as `protected`.
- Checked exception declarations cannot be arbitrarily broadened relative to the superclass method.
- A `final` method cannot be overridden.
- A superclass `private` method cannot be overridden by a subclass because it is not inherited in that sense; a same-signature `static` method is **hidden**, not polymorphically overridden.

## 6. Inheritance and Polymorphism: One API, Many Implementations

In this loop:

~~~java
for (Employee employee : staff) {
    employee.printPayslip();
}
~~~

The code never checks whether an employee is a `SalariedEmployee` or `HourlyEmployee`, yet produces the correct result for each type.

The call sequence is shown in this sequence diagram:

~~~mermaid
sequenceDiagram
    actor App as Main
    participant E as Employee (API)
    participant H as HourlyEmployee

    App->>E: printPayslip()
    Note over E,H: Một instance HourlyEmployee<br/>đang được tham chiếu qua Employee
    E->>H: role()
    H-->>E: "Theo giờ"
    E->>H: monthlyPay()
    H-->>E: 6000000
    E-->>App: đã in phiếu
~~~

In the diagram, `Employee (API)` represents only the **role of inherited code**; no separate `Employee` object is created alongside `HourlyEmployee`. When `printPayslip()` invokes `role()` and `monthlyPay()`, Java dispatches to the concrete instance's overrides.

Benefit: adding a `ContractEmployee` with a new pay calculation need not change the payroll loop as long as the new class honors the `Employee` contract. This is a practical example of extensibility through polymorphism.

## 7. Using Superclass References Without Arbitrary Casts

**Upcasting** means using a superclass-typed variable for a subclass object; Java performs it implicitly:

~~~java
Employee employee = new HourlyEmployee(
        "E004", "Lan", new BigDecimal("90000"), 100);
System.out.println(employee.monthlyPay()); // 9000000
~~~

Calling `monthlyPay()` is valid because it belongs to the `Employee` API, and Java then selects the `HourlyEmployee` implementation. Conversely, calling a method **available only on the subclass** requires checking the runtime type before downcasting. Casting a `SalariedEmployee` to `HourlyEmployee` throws `ClassCastException`.

~~~java
if (employee instanceof HourlyEmployee) {
    HourlyEmployee hourly = (HourlyEmployee) employee;
    System.out.println(hourly.monthlyPay());
}
~~~

Prefer polymorphism through `Employee` instead of repeated `instanceof` checks when the business operation needs only the common contract. Note that `List<HourlyEmployee>` is not a subtype of `List<Employee>`: Java's generic `List<T>` is **invariant**. To read subtype elements through a supertype-oriented API, `List<? extends Employee>` may be used with appropriate write restrictions.

## 8. The “is-a” Relationship Versus “has-a”

Two classes should not be connected with `extends` merely because they share data or use each other.

**Is-a (inheritance):** an `ElectricCar` is a `Vehicle`. Code accepting `Vehicle` may accept `ElectricCar` if the electric car satisfies every promise in the `Vehicle` contract.

**Has-a (composition):** a `Car` has an `Engine`. A car **is not** an engine, so `class Car extends Engine` is the wrong relationship even if the goal is to reuse `start()`.

~~~java
class Engine {
    void start() {
        System.out.println("Động cơ chạy");
    }
}

class Car {
    private final Engine engine;

    Car(Engine engine) {
        this.engine = engine;
    }

    void drive() {
        engine.start();
        System.out.println("Xe bắt đầu chạy");
    }
}
~~~

~~~java
Car car = new Car(new Engine());
car.drive();
~~~

This is **composition**: `Car` holds a reference to `Engine` and delegates some work. Switching to another engine type later may be more flexible than placing every variation in an inheritance hierarchy.

| Relationship | Question to ask | Typical Java approach |
| --- | --- | --- |
| **Is-a** | “Is X a kind of Y, and can X safely substitute for Y?” | `class X extends Y` or `implements` an appropriate type contract |
| **Has-a** | “Does X have/use Y to perform work?” | Reference field, constructor injection, composition |
| **Uses-a** | “Does X use Y only for one operation?” | Method parameter or short-lived dependency |

A linguistic statement that “X is Y” may sound plausible yet be insufficient. The **behavioral contract** is decisive: does every valid requirement imposed on Y still hold when X is substituted?

## 9. Java Inheritance Rules to Remember

| Rule | Example | Result |
| --- | --- | --- |
| A class can directly `extends` at most one class | `class C extends A, B` | Invalid |
| A class can `implements` multiple interfaces | `class C extends A implements X, Y` | Valid |
| An ordinary class without explicit `extends` inherits from `Object` | `class X {}` | Applicable `Object` methods are available |
| A `final` class cannot be subclassed | `final class Token {}` followed by `extends Token` | Compilation error |
| A `final` method cannot be overridden | `final void run() {}` | Subclasses cannot replace its implementation |
| An abstract class cannot be instantiated directly | `new Employee()` in the example | Compilation error |
| A concrete subclass must implement remaining abstract methods | `class X extends Employee` without `monthlyPay()` | Compilation error |
| Constructors are not inherited | `super(id, name)` | Invokes a superclass constructor for initialization |
| Inheritance is transitive | `C extends B` and `B extends A` | C is also a subtype of A |

Java also supports **interfaces** for contract-based polymorphism; `implements` is not the same as multiple class inheritance. A class has only one direct superclass, avoiding many problems of inheriting state and implementations from multiple classes.

### Inheritance Does Not Make Every Member Accessible

`private` members remain access-restricted. Constructors are not inherited. Static methods do not participate in dynamic dispatch like overridden instance methods. A same-named subclass field can **hide** a superclass field; field access is bound by the reference type, unlike overriding of instance methods. Avoid designs that depend on superclass/subclass field-name collisions.

An example contrasting fields and methods:

~~~java
class Animal {
    String name = "Animal";

    String speak() {
        return "Âm thanh chung";
    }
}

class Dog extends Animal {
    String name = "Dog"; // Che khuất field cha.

    @Override
    String speak() {
        return "Gâu";
    }
}

Animal a = new Dog();

System.out.println(a.name);    // Animal (field theo kiểu tham chiếu)
System.out.println(a.speak()); // Gâu (method theo instance thực)
~~~

Here, both `name` fields exist as members declared at different hierarchy levels. Field hiding makes access confusing, so avoid it in ordinary designs.

## 10. Avoid Overusing Inheritance and Preserve Superclass Contracts

A subclass must honor the valid expectations of its superclass. This relates to the **Liskov Substitution Principle (LSP)**: code using the superclass should not encounter surprises because a subclass breaks important superclass guarantees.

An example of poor design:

~~~java
class Bird {
    void fly() {
        System.out.println("Đang bay");
    }
}

class Penguin extends Bird {
    @Override
    void fly() {
        throw new UnsupportedOperationException("Không thể bay");
    }
}
~~~

A penguin is biologically a bird, but **it cannot satisfy the contract that every Bird can fly** imposed by `Bird.fly()`. Code accepting `Bird` and assuming `fly()` always works will fail with a `Penguin`.

A better model separates capabilities:

~~~java
interface Flyable {
    void fly();
}

abstract class Bird {
    abstract void move();
}

class Sparrow extends Bird implements Flyable {
    @Override
    void move() {
        System.out.println("Chim sẻ di chuyển");
    }

    @Override
    public void fly() {
        System.out.println("Chim sẻ bay");
    }
}

class Penguin extends Bird {
    @Override
    void move() {
        System.out.println("Chim cánh cụt đi hoặc bơi");
    }
}
~~~

Here, `Bird` promises only behavior common to all birds, while `Flyable` represents a separate capability. Good inheritance depends on **a consistent contract**, not only similar nouns or a few reused lines.

Before choosing a design, ask:

1. Is the **is-a** relationship correct in behavior, not merely similar data?
2. Can subclasses preserve the superclass's preconditions, postconditions, and invariants?
3. Is shared behavior truly stable, or must each subclass repeatedly override it to work around the superclass?
4. Would composition or an interface satisfy the need with fewer constraints?
5. Could extending a superclass unintentionally change existing subclasses' behavior?

**Inheritance is a tight relationship:** subclasses depend on superclass contracts and structure. If the is-a relationship is unclear or the only goal is to reuse a utility, composition is often simpler and more maintainable.

## 11. Common Learning Mistakes

| Mistake | Cause | Fix |
| --- | --- | --- |
| Assuming `extends` creates independent parent and child objects | Confusing classes with instances | One `new Subclass()` creates one instance containing inherited state |
| Calling `new Employee()` in the example | `Employee` is abstract | Instantiate a concrete subclass |
| Omitting `super(...)` when the superclass has no no-arg constructor | Compiler cannot invoke a suitable constructor | Invoke the superclass constructor explicitly |
| Incorrect override signature | Creates an overload or fails to implement the method | Use `@Override` for compiler checking |
| Direct access to a superclass `private` field | The field is inaccessible by name in subclass code | Use an appropriate `public`/`protected` API |
| Casting every `Employee` to `HourlyEmployee` | The runtime object may be another subtype | Avoid downcasts; use polymorphism or type checks |
| Using setters/overrides to break superclass invariants | Subclass violates the contract | Keep shared rules in the superclass and extend only at permitted points |
| Inheriting just to invoke a helper | No valid is-a relationship | Use composition/delegation |
| Confusing field hiding with method overriding | Java treats fields and methods differently | Avoid duplicate field names; understand dynamic dispatch |

## 12. Self-Check Exercises

**Exercise 1.** Is `Vehicle v = new Car();` valid? Does `v.openTrunk()` compile?

**Answer:** The assignment is valid because `Car` extends `Vehicle`. But `v.openTrunk()` does not compile unless `Vehicle` declares that method; permissible calls depend on the variable's **static type**.

**Exercise 2.** If an `HourlyEmployee` has `hourlyRate=100000` and `hoursWorked=15`, what does `monthlyPay()` return through an `Employee` reference?

**Answer:** `1500000`. Java invokes the `HourlyEmployee` override based on the runtime instance, even though the variable is declared as `Employee`.

**Exercise 3.** Why can't `HourlyEmployee` directly access `this.id` when `id` is `private` in `Employee`?

**Answer:** `private` limits direct field access to the declaring class (apart from the special nestmate access rules defined by Java). The subclass uses the superclass's exposed API, such as `getId()`.

**Exercise 4.** Do `SalariedEmployee` and `HourlyEmployee` both become objects when only `new HourlyEmployee(...)` is called?

**Answer:** No. Only one `HourlyEmployee` instance is created, including the state and behavior inherited from `Employee`.

**Exercise 5.** May a subclass inherit an ordinary superclass method without overriding it?

**Answer:** Yes. If there is no remaining obligation to implement abstract methods, the subclass may inherit all applicable implementations. Override only when permitted behavior needs specialization.

**Exercise 6.** With `Car` and `Engine`, should you use `Car extends Engine` or have `Car` hold an `Engine`?

**Answer:** A `Car` **has** an engine; it **is not** an engine. Composition (`Car` holds an `Engine` reference) is more appropriate.

**Exercise 7.** What is the risk of adding `Penguin extends Bird` if `Bird` promises that `fly()` always works?

**Answer:** It violates the `Bird` substitutability contract if `Penguin.fly()` throws an unexpected error. Model shared behavior to suit every subclass and separate flying ability into `Flyable` when appropriate.

**Exercise 8.** If `ContractEmployee` is later added, must the `List<Employee>` payroll loop include `if (e instanceof ContractEmployee)`?

**Answer:** Usually not, if the new class correctly implements `monthlyPay()`. Polymorphism lets the loop use the common API while each subclass determines its pay formula.

### Remember

The **superclass** describes shared characteristics and a contract for a family of objects; the **subclass** represents a more specific kind, inherits common behavior, and may add or override permitted behavior. `extends` expresses an is-a commitment, not simply a way to copy code.

When reading inheritance code, identify the superclass, subclass, invoked superclass constructor, inherited/overridden methods, runtime object type, and whether the subclass honors the superclass contract.
