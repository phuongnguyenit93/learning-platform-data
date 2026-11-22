# Reading and Updating Fields Using the Dot Operator in Java

In Java, the **dot operator** (`.`) is used to access a **member** of a type or object. For a **field**, the syntax `object.field` or `ClassName.staticField` allows **reading** the value and, if the field allows writing and the code has access, **updating** the value.

Example:

```java
Student student = new Student();
student.age = 20;                       // Write a new value to the age field
System.out.println(student.age);        // Read the age field: 20
```

This is an illustrative snippet, assuming a `Student` class with an accessible `age` field already exists. The dot does not create an object on its own, nor does it automatically call a getter/setter: `student.age` directly denotes the selected field, whereas `student.getAge()` is a method call.

This article focuses on **reading and updating fields** using the dot operator: syntax, how to determine which object is modified, instance/static fields, `this`, `final`, access scope, `null`, inheritance, and common errors.

## 1. What Is a Field?

A **field** is a variable declared inside the body of a class (or a type that can contain fields), at the **member** level, outside methods/constructors/local blocks. Fields are used to store state or data associated with a class or an instance.

```java
class Product {
    String name;                   // Instance field
    int quantity;                  // Instance field
    static int totalCreated;       // Static field

    void add(int amount) {
        int newQuantity = quantity + amount; // newQuantity is a local variable
        quantity = newQuantity;               // quantity is a field
    }
}
```

- `name` and `quantity` are **instance fields**: each `Product` object has its own field state.
- `totalCreated` is a **static field**: a field associated with the `Product` class (more precisely, with the loaded class definition), shared across instances.
- `newQuantity` is a **local variable** and cannot be read as `product.newQuantity` from outside the method.
- The parameter `amount` is also not a field: it only exists within the scope of the `add` call.

Distinguishing between a **field** and a **local variable** helps determine when the dot operator can be used. The dot must select a valid member of a type or object; it cannot arbitrarily select just any variable name appearing in the source code.

## 2. Syntax for Reading and Updating Instance Fields

Suppose a class has two accessible fields:

```java
class Rectangle {
    int width;
    int height;
}
```

Inside a method containing a reference variable `rectangle` of type `Rectangle`:

```java
Rectangle rectangle = new Rectangle();

rectangle.width = 4;              // Write instance field
rectangle.height = 3;             // Write instance field

int w = rectangle.width;          // Read instance field
int area = rectangle.width * rectangle.height;

System.out.println(w);            // 4
System.out.println(area);         // 12
```

Key syntax:

| Syntax | Effect | Example |
| --- | --- | --- |
| `object.field` where a value is needed | Reads the current value of the field | `int n = rectangle.width;` |
| `object.field = expression;` | Evaluates the expression on the right and assigns it to the field | `rectangle.width = 10;` |
| `object.field += expression;` | Reads, computes, and writes back to the field | `rectangle.width += 2;` |
| `object.field++;` | Increments a compatible numeric field value by 1 | `rectangle.width++;` |
| `object.field = other.field;` | Copies the **value** from another field | `a.width = b.width;` |
| `object.method()` | **Calls a method**, not field-reading syntax | `rectangle.toString();` |

The `rectangle` variable must reference a valid object when accessing an instance field. Writing `rectangle.width = 10` does not create another `Rectangle`; it modifies the `width` field in the **currently referenced object**.

The expression after `=` must have a type **compatible** with the declared type of the field. For example, `rectangle.width = "rộng";` does not compile because `width` has type `int` whereas `"rộng"` is a `String`.

A field **read** can participate in an expression (`rectangle.width * 2`), a condition (`rectangle.width > 0`), or a method call (`Math.max(rectangle.width, 1)`). A field **write** must comply with assignability and access rules (see the `final` and `private` sections).

## 3. Runnable Java 17 Program: Reading, Writing, Incrementing, and Aliasing

Save all the code below into a file named **`FieldAccessDemo.java`**:

```java
class Account {
    String owner;
    int balance;
    static int created;

    Account(String owner, int balance) {
        this.owner = owner;
        this.balance = balance;
        created++;
    }
}

public class FieldAccessDemo {
    public static void main(String[] args) {
        Account account = new Account("Lan", 100);

        System.out.println(account.owner);
        System.out.println(account.balance);

        account.balance = 130;
        account.balance += 20;
        System.out.println(account.balance);

        Account alias = account;
        alias.balance++;
        System.out.println(account.balance);

        Account other = new Account("Minh", 50);
        System.out.println(other.owner);
        System.out.println(Account.created);

        System.out.println(account == alias);
        System.out.println(account == other);
    }
}
```

Compile and run in the directory containing the file:

```bash
javac -encoding UTF-8 FieldAccessDemo.java
java FieldAccessDemo
```

**Exact stdout:**

```text
Lan
100
150
151
Minh
2
true
false
```

Explanation:

1. `new Account("Lan", 100)` creates the first object with `owner = "Lan"` and `balance = 100`.
2. `account.owner` and `account.balance` read **the fields of that object**.
3. `account.balance = 130` overwrites the old balance; `account.balance += 20` reads `130` and then writes `150`.
4. `Account alias = account;` only **copies the reference value** without creating a new object. `alias.balance++` updates the same object, so `account.balance` reads `151`.
5. `other` references a different object with `owner = "Minh"`. Every execution of the `Account` constructor increments the static field `created`, so `Account.created` equals `2`.
6. The `==` operator on two reference variables checks whether they refer to the same object; `account == alias` is `true`, whereas `account == other` is `false`.

Logical diagram before printing the final lines:

```text
account ──┐
          ├──> Account #1 { owner: "Lan", balance: 151 }
alias   ──┘

other   ─────> Account #2 { owner: "Minh", balance: 50 }

Account.created = 2   (static: associated with the class)
```

`#1` and `#2` are merely labels illustrating identity, not actual memory addresses.

Key takeaway: **the dot operator accesses a field of the object referenced by the left-hand expression**; it does not permanently bind a field to a variable name. Therefore, two variables referencing the same object can observe the same change.

## 4. Reassigning a Reference Variable vs. Updating a Field

These two operations look similar but are completely different:

```java
Account first = new Account("An", 100);
Account second = new Account("Bình", 200);

first.balance = 150;       // Modify the balance field on the object referenced by first
first = second;            // Reassign the first variable; do NOT modify any object
```

This snippet uses the `Account` class from Section 3 and is not a standalone program. After the last line, both `first` and `second` reference `"Bình"`'s object (balance `200`). The original object of `first` still keeps a balance of `150` as long as it exists; losing a reference does not automatically change its balance to `200`.

You can determine the effect from the **left-hand side of the assignment**:

- `first = second;`: the assignment target is the **reference variable** `first`.
- `first.balance = 150;`: the assignment target is the **field** `balance` of the object currently selected through `first`.
- `first.owner = "Linh";`: the assignment target is the **reference field `owner`** of the object; assigning a new string changes the reference value of the field without modifying the inside of the old `String` object.

If a field has a reference type, assignment also **copies the reference value**. It does not automatically deep-copy the referenced object.

## 5. Using `this.field` Inside a Class to Read/Write the Object's Own Fields

Inside an **instance method** or **constructor**, `this` can be used to refer to the current object.

```java
class User {
    String name;

    User(String name) {
        this.name = name;
    }

    void rename(String name) {
        this.name = name;
    }

    void printName() {
        System.out.println(this.name);
    }
}
```

In `User(String name)`, the parameter `name` has the same name as the `name` field:

- `name` standing alone inside the method/constructor refers to the nearest **parameter** due to *shadowing*.
- `this.name` refers to the **instance field** of the current object.
- `this.name = name;` assigns the parameter's value to the object's field.

If there is no variable or parameter with the same name shadowing it, you can write `name` instead of `this.name` inside an instance method. However, `this.name` is useful for making it clear that you are operating on a field.

**You cannot use `this` in a static method or static initializer**, because they do not have a `this` object. To access an instance field from a `static` method, you need a reference to a specific object:

```java
class User {
    String name;

    static void show(User user) {
        System.out.println(user.name);
    }
}
```

The two `User` declarations above are **alternative examples** and should not be compiled in the same package/source set at the same time, as doing so would define the `User` class twice.

## 6. Reading and Updating Static Fields via the Class Name

A field declared with `static` **belongs to the class**, not to an individual instance:

```java
class Settings {
    static String environment = "dev";
    int retries = 3;
}
```

Usage example inside a method:

```java
System.out.println(Settings.environment); // dev
Settings.environment = "prod";
System.out.println(Settings.environment); // prod

Settings instance = new Settings();
System.out.println(instance.retries);      // 3
```

For a `static` field, **prefer `ClassName.field`**: `Settings.environment`. A statement like `instance.environment` may be accepted by Java, but it should be avoided because it misleadingly suggests that `environment` is per-object state.

In particular:

- `static` does not mean immutable: `Settings.environment = "prod"` is valid because the field is not `final`.
- `static final` is commonly used to define constants, but a `static final` field of a reference type does not guarantee that the referenced object is immutable.
- A `static` field has its own access scope. A `private static` field is only accessible from locations permitted by Java's rules; being static does not make it public.
- Using `this.environment` inside an instance method still denotes the **static field**, but it is easily misunderstood and should be replaced with `Settings.environment`.

### Complete Example: Objects Seeing the Same Static Field

Save as **`StaticFieldDemo.java`**:

```java
class Config {
    static int maxConnections = 10;
    int currentConnections;

    Config(int currentConnections) {
        this.currentConnections = currentConnections;
    }
}

public class StaticFieldDemo {
    public static void main(String[] args) {
        Config first = new Config(2);
        Config second = new Config(5);

        System.out.println(first.currentConnections);
        System.out.println(second.currentConnections);
        System.out.println(Config.maxConnections);

        Config.maxConnections = 20;
        second.currentConnections = 7;

        System.out.println(Config.maxConnections);
        System.out.println(first.currentConnections);
        System.out.println(second.currentConnections);
    }
}
```

Run:

```bash
javac -encoding UTF-8 StaticFieldDemo.java
java StaticFieldDemo
```

Output:

```text
2
5
10
20
2
7
```

`currentConnections` is an instance field, so modifying `second.currentConnections` does not change `first.currentConnections`. `maxConnections` is a static field, so accessing it through the class name `Config` reflects the same shared value.

## 7. Multi-Level Dot Operator and Nested Object References

A field can hold a reference to another object. When that happens, you can chain multiple dots to access a field:

```java
class Address {
    String city;
}

class Customer {
    Address address;
}
```

Usage inside a method:

```java
Customer customer = new Customer();
customer.address = new Address();
customer.address.city = "Hà Nội";

System.out.println(customer.address.city); // Hà Nội
```

`customer.address.city` is logically understood as:

1. Read `customer`, obtaining a reference to the `Customer` object.
2. Read the `address` field of `Customer`, obtaining a reference to an `Address` object.
3. Read or write the `city` field of that `Address` object.

**If an intermediate reference level is `null`, accessing the next level can throw a `NullPointerException`.** The following example has a runtime error:

```java
Customer customer = new Customer();
System.out.println(customer.address.city); // NullPointerException
```

Reason: `address` has not been assigned, so it receives the default value `null`. Java **does not have safe navigation syntax `customer?.address?.city`** in Java 17. You can check:

```java
if (customer != null && customer.address != null) {
    System.out.println(customer.address.city);
}
```

These are illustrative snippets meant to be placed inside a method that can access the classes above; they are not standalone program files. Depending on the design, it is better to require a valid object right in the constructor rather than allowing an important field to remain in a `null` state.

## 8. `null`: A Valid Receiver Is Required Before Reading a Field

A numeric instance field may default to `0`, and a reference field such as `String label` may default to `null`. However, **reading `box.count` is only valid at runtime when `box` references an object**; if `box == null` itself, reading an instance field throws a `NullPointerException`. If `box` is not null but `box.label == null`, retrieving the reference field returns null, and only subsequently calling `box.label.length()` fails. Local variables must also satisfy *definite assignment* at compile time in order to be read.

This article emphasizes the checking order of **the dot expression and the receiver**; it does not repeat the default-value table for every primitive type.

Runnable example, save as **`NullFieldDemo.java`**:

```java
class Box {
    int count;
    String label;
}

public class NullFieldDemo {
    public static void main(String[] args) {
        Box box = new Box();

        System.out.println(box.count);
        System.out.println(box.label);

        Box absent = null;
        System.out.println(absent == null);

        try {
            System.out.println(absent.count);
        } catch (NullPointerException ex) {
            System.out.println("Không thể đọc instance field qua null");
        }
    }
}
```

Commands:

```bash
javac -encoding UTF-8 NullFieldDemo.java
java NullFieldDemo
```

Stdout:

```text
0
null
true
Không thể đọc instance field qua null
```

`box.count` can be read because `box` is a created object and its unassigned `int` field receives `0`. `absent.count` causes a `NullPointerException` because `absent` does not reference any `Box` object.

**Special note on static fields:** if you write `Box b = null;` and then access `b.someStaticField` (assuming `someStaticField` is declared static in `Box`), Java can still access the static field successfully because that field is not retrieved from the object `b`. This is **not** how you should write it: always use `Box.someStaticField` to avoid confusion.

## 9. Field Access Rights: The Dot Operator Does Not Bypass Access Modifiers

The dot operator is only valid when the **access path is permitted by Java**. You cannot read or modify a `private` field from an arbitrary class simply because you know the variable name and field name.

| Field modifier | Typical accessible locations |
| --- | --- |
| `public` | Code that can access the type containing the field, subject to module and related Java conditions |
| `protected` | Same package and inheritance-based access cases from another package according to `protected` rules |
| No modifier (package-private) | Classes in the same package |
| `private` | Only within the permitted declaration scope of the type containing the field and related Java contexts |

Example:

```java
class Wallet {
    private int money = 100;
}

class Reader {
    void show(Wallet wallet) {
        // System.out.println(wallet.money); // INVALID: money is private in Wallet
    }
}
```

Two classes in the same package are also not allowed to directly access each other's `private` fields merely because they share the same package.

**Subtle point:** methods inside the `Wallet` class itself can access a `private` field of **another Wallet object**, such as `other.money`; `private` restricts **where the code is permitted to access from**, rather than tying secrecy exclusively to the `this` object.

### Encapsulation: Update Through Methods When Data Validation Is Needed

The dot operator is not always used to modify fields directly. A common design is to keep fields `private` and provide read/write methods that validate conditions.

Save as **`EncapsulationDemo.java`**:

```java
class BankAccount {
    private int balance;

    BankAccount(int initialBalance) {
        if (initialBalance < 0) {
            throw new IllegalArgumentException("Số dư âm");
        }
        this.balance = initialBalance;
    }

    int getBalance() {
        return balance;
    }

    void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Số tiền nạp phải dương");
        }
        this.balance += amount;
    }
}

public class EncapsulationDemo {
    public static void main(String[] args) {
        BankAccount account = new BankAccount(100);

        System.out.println(account.getBalance());
        account.deposit(50);
        System.out.println(account.getBalance());

        // account.balance = -100; // Compile error: private field
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 EncapsulationDemo.java
java EncapsulationDemo
```

Stdout:

```text
100
150
```

`account.getBalance()` and `account.deposit(50)` **call methods**, whereas `this.balance` inside `BankAccount` **directly accesses the field**. Both use the dot operator, but adding `()` indicates a method call rather than field access.

Encapsulation helps protect validity conditions (*invariants*) such as a non-negative balance, control data changes, and reduce dependency on the field structure. You do not necessarily have to create getters/setters for every field; choose the API according to the object's requirements.

## 10. `final`: When Can a Field Not Be Updated Using the Dot Operator?

A field declared `final` can only be assigned according to **final initialization rules**. After initialization, no new value may be assigned to that field.

```java
class Ticket {
    final int id;
    String owner;

    Ticket(int id, String owner) {
        this.id = id;            // Assigning a final field in the constructor: valid
        this.owner = owner;
    }
}
```

Usage inside a method:

```java
Ticket ticket = new Ticket(7, "An");

System.out.println(ticket.id);     // 7
ticket.owner = "Bình";             // Valid
// ticket.id = 8;                  // INVALID: cannot reassign a final field
// ticket.id++;                    // INVALID: incrementing also updates a final field
```

**Distinguishing two commonly confused situations:**

```java
final Ticket ticket = new Ticket(7, "An");
ticket.owner = "Bình";              // Valid: modifies the referenced object
// ticket = new Ticket(8, "Lan");   // INVALID: a final reference variable cannot be reassigned
```

- `final Ticket ticket` locks **reassigning the `ticket` variable**; it does not make the entire object immutable.
- `final int id` locks **the value of the `id` field** after the permitted initialization step.
- A `final` field of a reference type such as `final List<String> items` keeps the same **field reference** after initialization, but the contents of the `List` can still change if that list permits it. Achieving immutability requires a stricter design.

Besides `final`, a field may be non-writable due to **access rights**, because the object does not exist, or because of specific language constraints for that kind of field.

## 11. Field Hiding in Inheritance: The Dot Operator Selects Fields by Reference Type

A field **is not polymorphically overridden like an instance method**. When a subclass declares a field with the same name as its superclass, that is **field hiding**; field selection is based on the **compile-time type of the expression to the left of the dot** and member lookup rules.

Save as **`FieldHidingDemo.java`**:

```java
class Parent {
    String label = "cha";

    String describe() {
        return "method cha";
    }
}

class Child extends Parent {
    String label = "con";

    @Override
    String describe() {
        return "method con";
    }
}

public class FieldHidingDemo {
    public static void main(String[] args) {
        Parent asParent = new Child();
        Child asChild = new Child();

        System.out.println(asParent.label);
        System.out.println(asParent.describe());
        System.out.println(asChild.label);
        System.out.println(((Child) asParent).label);
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 FieldHidingDemo.java
java FieldHidingDemo
```

Stdout:

```text
cha
method con
con
con
```

Why?

- `asParent.label` reads **`Parent`'s field** because the type of the expression `asParent` is `Parent`. Even though the actual object is a `Child`, field access is not dynamically dispatched like methods.
- `asParent.describe()` invokes `Child`'s overridden version because it is an **instance method**, which supports dynamic dispatch.
- `asChild.label` reads `Child`'s `label` field.
- `((Child) asParent).label` reads `Child`'s `label` field because the valid cast changed the compile-time type of the member-selection expression.

In the example, an actual `Child` object has **two distinct fields** with the same name `label` (one inherited from `Parent` and one declared in `Child`). Inside the subclass code, `super.label` can be used to access the superclass's field if permitted by Java's access rules.

**Recommendation:** avoid declaring fields with the same name between superclass and subclass when there is no clear reason; prefer encapsulation and methods to avoid confusion between field hiding and method overriding.

## 12. `+=`, `++`, and Compound Updates: Read Then Write

Field-updating operations typically have **two logical parts**: reading the current value and writing the new value.

```java
counter.value = counter.value + 1;
counter.value += 1;
counter.value++;
++counter.value;
```

If `counter.value` is a regular `int` field and `counter` references a valid object, all four forms **increment the field value by one**, but they are not completely equivalent in every expression:

- `counter.value++` is **post-increment**: the value of the expression itself is the **old value**, while the field receives the incremented value.
- `++counter.value` is **pre-increment**: the value of the expression itself is the **new value**.
- `counter.value += 1` is **compound assignment**: it combines addition and assignment and has Java's own type and conversion rules; it should not be treated as identical in every respect to `counter.value = counter.value + 1`.
- `counter.value = counter.value + 1` explicitly writes out the read, addition, and reassignment, but may evaluate the left-hand expression/receiver according to different rules when the receiver is an expression with side effects.

Complete example, file **`IncrementDemo.java`**:

```java
class Counter {
    int value = 5;
}

public class IncrementDemo {
    public static void main(String[] args) {
        Counter counter = new Counter();

        int before = counter.value++;
        int after = ++counter.value;

        System.out.println(before);
        System.out.println(after);
        System.out.println(counter.value);

        counter.value += 3;
        System.out.println(counter.value);
    }
}
```

Run:

```bash
javac -encoding UTF-8 IncrementDemo.java
java IncrementDemo
```

Stdout:

```text
5
7
7
10
```

Explanation: starting at `5`, post-increment stores `5` in `before` and updates the field to `6`; pre-increment increments it further to `7` and stores `7` in `after`. After `+= 3`, the field value is `10`.

**Multithreading note:** `counter.value++` and `counter.value += 1` are **not atomic operations** when multiple threads update concurrently. `volatile` also does not automatically make an increment atomic. If multiple threads share state, appropriate synchronization or a solution such as `AtomicInteger` is required; using only the dot operator and `++` does not guarantee correct results under data races.

## 13. Common Compile-Time and Runtime Errors

| Example / Situation | Issue Type | Explanation or Fix |
| --- | --- | --- |
| `account.balance` when `account == null` | `NullPointerException` at runtime (instance field) | Create the object, check for null, or design to avoid null |
| `account.balance = "100";` when `balance` is `int` | Compile-time type error | Assign a value of the same/compatible type, for example `100` |
| `account.secret` when `secret` is `private` in another class | Compile-time access error | Use a valid API such as a getter/method |
| `account.unknown` when the type has no accessible field named `unknown` | Member lookup error | Check the field name and the declared type of the receiver |
| `account.id = 2;` when `id` is an already-initialized instance `final` field | Compile error | Do not reassign a final field |
| `Account.balance` when `balance` is an instance field | Compile error: an object is required | Use `account.balance` in an appropriate context |
| `account.created` when `created` is static | Usually compiles, but hard to read | Prefer `Account.created` |
| `obj.field++` in multithreaded code | Risk of lost update | Use synchronization or an appropriate concurrent data structure |
| `child.field` with the same name as a superclass field | Easy confusion with field hiding | Consider the static type of the receiver; avoid duplicate names |
| `record.name` from outside a record | Record fields are typically `private` | Use the accessor such as `record.name()` |
| `object.getValue` when only a `getValue()` method exists | Syntax/member lookup error | Add `()`: `object.getValue()` |

In the table, the class/field names are merely hypothetical examples. An accurate diagnosis requires checking the declared type, modifiers, and access context of the actual code.

**Another misconception:** the dot operator does not automatically invoke a setter. `account.balance = 10` writes directly to the field if the field is accessible; it does **not** silently execute `account.setBalance(10)`. When data validation, logging, synchronization, or change notification is needed, provide an API and require external callers to invoke that API.

## 14. When a Field Belongs to a Record or a Type With a Dedicated Read API

Java 17 supports `record`, which is commonly used to hold structured data. For a record, components are provided with accessor methods, and the corresponding fields are `private final`:

```java
record Point(int x, int y) {
}

public class RecordFieldDemo {
    public static void main(String[] args) {
        Point point = new Point(2, 3);

        System.out.println(point.x());
        System.out.println(point.y());

        // System.out.println(point.x); // INVALID outside the record: x is a private field
        // point.x = 5;                   // INVALID: x is a private final field
    }
}
```

Save as **`RecordFieldDemo.java`**, then run:

```bash
javac -encoding UTF-8 RecordFieldDemo.java
java RecordFieldDemo
```

Stdout:

```text
2
3
```

`point.x()` is an **accessor method call**, which differs from `point.x`, which is a field access. With a `record`, to represent a different value, you typically create a new instance, such as `new Point(5, point.y())`, instead of modifying a component.

The goal of this example is to avoid assuming that all "named" data in Java is open to direct writing through the dot operator.

## 15. Practice: Predict the Output Before Running

Suppose the following declaration appears in a test file:

```java
class Cart {
    int items;
    static int nextId = 1;
    final int id;

    Cart(int items) {
        this.items = items;
        this.id = nextId++;
    }
}
```

Code used inside `main`:

```java
Cart first = new Cart(2);
Cart shared = first;
Cart second = new Cart(5);

shared.items += 3;
first = second;

System.out.println(shared.items);
System.out.println(first.items);
System.out.println(first.id);
System.out.println(Cart.nextId);
```

Prediction:

- There are **two instances** of `Cart`, because `new Cart(...)` runs twice.
- Initially, `shared` points to the same object as `first`, which has `items = 2`.
- `shared.items += 3` changes `items` of the first object to `5`.
- `first = second` only changes the `first` reference to the second object; `shared` still points to the first object.
- `first.id` reads the `final` field assigned `2` by the constructor for the second object.
- `Cart.nextId` has been incremented twice, from `1` to `3`.

**Stdout output:**

```text
5
5
2
3
```

Both `items` values are `5`, yet they come from **two different objects**. This reminds us that **equal field values do not prove the same reference**, and reassigning a variable does not copy state to another object.

To run standalone, you can place the `Cart` class and a `public class CartDemo` containing `main` with the snippet above in the same file **`CartDemo.java`**, keeping `CartDemo` as the only top-level `public` class.

## 16. Checklist When Reading an Expression `a.b`

To correctly analyze a field access through the dot operator:

1. **What is `a`?** A class name, reference variable, `this`/`super`, or an expression returning an object? If it is a class name, it is usually accessing a static member.
2. **What is `b`?** An instance/static field or a method? `a.b` is a field access, whereas `a.b()` is a method call if `b` is a method.
3. **What is the declared type of the receiver?** It determines the set of selectable members at compile time; field hiding does not have dynamic dispatch like method overriding.
4. **Is access permitted?** Check `public`/`protected`/package-private/`private` and the rules for that type.
5. **Is there an actual object?** For an instance field, if the receiver is `null`, reading/writing can throw a `NullPointerException`.
6. **Can the field be reassigned?** An initialized `final` field cannot be modified with `=`, `++`, or `+=`.
7. **What does the operation modify?** `a = b` modifies the value of the variable `a`, whereas `a.field = value` modifies a field of the object currently referenced by `a`.
8. **Is validation or synchronization needed?** If the field represents critical state, consider encapsulation methods; if multiple threads update concurrently, apply an appropriate synchronization mechanism.

### Key Takeaways

- **Reading a field:** `object.field`; **writing a field:** `object.field = value;` when the code has access and the field permits assignment.
- **Instance fields** belong to individual objects; **static fields** belong to the class, so you should write `ClassName.field`.
- The dot operator **does not create objects automatically, does not call getters/setters automatically, and does not bypass access modifiers**.
- Two variables referencing the same object will observe the same changes to that object's instance fields.
- `this.field` explicitly identifies a field of the current object; `final` restricts writing; a `null` receiver causes an error when accessing an instance field.
- With inheritance, **fields are selected by compile-time type**, unlike instance methods which can be overridden; for data requiring validity control, prefer encapsulation through methods.
