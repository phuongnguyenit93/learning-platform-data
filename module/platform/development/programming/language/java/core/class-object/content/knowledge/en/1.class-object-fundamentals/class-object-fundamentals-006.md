# Overview of Fields, Methods, Constructors, and Static Members in Java

In Java, a **class** describes a type of object: where data is held, how behavior is performed, and how an object is validly created. Four components to distinguish are **fields**, **methods**, **constructors**, and **static (class-level)** members. This article applies to Java 17+ and focuses on how to read, write, and use them together.

## 1. Viewing a Class as a Blueprint

~~~java
class BankAccount {
    private String owner;                    // per-object field
    private long balance;                    // per-object field
    private static int accountCount;         // shared class-level field

    BankAccount(String owner) {               // constructor
        this.owner = owner;
        accountCount++;
    }

    void deposit(long amount) {               // instance method
        if (amount <= 0) {
            throw new IllegalArgumentException("Số tiền phải dương");
        }
        balance += amount;
    }

    long getBalance() {                       // instance method
        return balance;
    }

    static int getAccountCount() {            // static method
        return accountCount;
    }
}
~~~

This is an **illustrative class declaration snippet**, not yet a program with a `main` method to run on its own. It shows:

| Component | Purpose | Belongs To | Typical Usage |
| --- | --- | --- | --- |
| Instance field (`owner`, `balance`) | Hold individual state | Each `BankAccount` object | Accessed via object methods |
| Instance method (`deposit`, `getBalance`) | Operate on object state and behavior | The object receiving the call | `account.deposit(100)` |
| Constructor (`BankAccount(...)`) | Initialize a new object | Object creation process | `new BankAccount("An")` |
| Static field (`accountCount`) | Hold shared class state | The class, within its corresponding class load | `BankAccount.getAccountCount()` |
| Static method (`getAccountCount`) | Provide behavior independent of `this` | The class | `BankAccount.getAccountCount()` |

For example, two accounts have their own `owner` and `balance`, yet both observe the same `accountCount` variable. **Parameter variables and local variables are not fields**: they exist within the context of a method or constructor call and are not stored as object state.

## 2. Fields: Where Is State Stored?

A **field** is a variable declared directly inside the body of a class (or interface). For a class, a field has a type, a name, an access scope, and may have modifiers such as `static`, `final`, `volatile`. Instance fields are associated with each object; static fields are associated with the corresponding class.

### 2.1. Initial Values and Declaration Location

When an object is created, instance fields first receive default values: numeric types receive `0` (or `0.0`), `boolean` receives `false`, `char` receives the null character (`'\u0000'`), and reference types receive `null`. Then, field initializers and instance initializer blocks are executed in declaration order, before the constructor body of that class itself. Static fields also receive default values before the class's static initializers run.

~~~java
class Profile {
    int age;                       // defaults to 0
    boolean active;                // defaults to false
    String name = "Chưa đặt";      // assigned during object initialization
}
~~~

Unlike fields, **local variables do not have a default value for direct use**: the compiler requires a variable to be assigned before being read. For example, `int x; System.out.println(x);` in the same method will result in a compilation error.

### 2.2. Access, Name Shadowing, and Immutability

Generally, fields should be made `private`, with modifications controlled through constructors or methods. If a parameter has the same name as a field, use `this.field` to explicitly refer to the current object's field:

~~~java
class Person {
    private final String name;

    Person(String name) {
        this.name = name; // left side is the field; right side is the parameter
    }

    String getName() {
        return name;
    }
}
~~~

For an instance field, `final` means the field can only be **assigned a value once along each valid initialization path**. A `final` field of a reference type prevents reassigning the reference, but **does not by itself make the referenced object immutable**. For example, `final List<String> names` can still point to an `ArrayList` that allows adding elements; it is `names = otherList` that is prohibited after the first assignment.

Do not expose mutable internal state if invariants need to be protected: a getter returning a mutable list directly, for instance, still allows external code to modify the data. Consider a defensive copy or an unmodifiable collection when appropriate.

### 2.3. Reading and Writing Fields

Inside an instance method, you can write `balance` or `this.balance`. From the outside, a field can only be accessed if Java access rules permit it. `private` is accessible only within the declaring class (including nested contexts permitted by Java), not by “all classes in the same package”. A field may hold a `null` reference: accessing `p.name` when `p == null` causes a `NullPointerException`.

## 3. Methods: Behavior, Inputs, and Return Values

The typical structure of a method consists of modifiers, a return type, a name, a parameter list, `throws` declarations if any, and a method body. Instance methods are invoked on an object; static methods are typically invoked using the class name.

~~~java
class Calculator {
    int add(int a, int b) {
        return a + b;
    }

    double add(double a, double b) {
        return a + b;
    }

    static boolean isPositive(int value) {
        return value > 0;
    }
}
~~~

This is an illustrative snippet. The two `add` methods are **overloaded** because they have different parameter type lists; changing only the return type is **not enough** to overload. In Java, the signature used to distinguish overloads is based on the name and parameter types (not on the return type); overload resolution takes place at compile time based on the types of the passed expressions and method applicability rules.

An **instance method** has `this`, so it typically reads and modifies the object's own fields. A **static method** does not have `this`; therefore, it cannot directly use `this` or instance fields/methods without an explicit object reference.

~~~java
class Rectangle {
    private final int width;
    private final int height;

    Rectangle(int width, int height) {
        this.width = width;
        this.height = height;
    }

    int area() {
        return width * height;
    }

    static Rectangle square(int side) {
        return new Rectangle(side, side);
    }
}
~~~

Here, `area()` requires the state of a specific rectangle; `square(int)` is a **static factory method** that creates and returns an object itself. A factory method **is not a constructor**, even though it can serve instead of a constructor as an object-creation API.

**Return values:** a method with a type other than `void` must return an appropriate value along every normal completion path; `void` returns no value. Java passes arguments **by value**: for primitive types, the method receives a copy of the value; for reference types, the method receives a copy of the reference. Consequently, you can modify the contents of the object that the reference points to (if the object allows it), but reassigning the parameter itself does not make the reference variable in the caller point to a new object.

**Overriding differs from overloading:** a subclass can override an eligible instance method to change behavior during dynamic dispatch; `static` methods are not overridden by that mechanism, and instead can *hide* a superclass's static method. Fields are also *hidden*, not polymorphically dispatched like instance methods. This is an important distinction when taking an overview of class members.

## 4. Constructors: Establishing Valid State Upon Object Creation

A constructor has **the exact same name as the class** and **declares no return type**, not even `void`. It is invoked during object creation with `new`; it is not called like a regular instance method. Constructors can be overloaded with different parameter lists, but **are not inherited** like methods.

~~~java
class Product {
    private final String code;
    private int stock;

    Product(String code) {
        this(code, 0);
    }

    Product(String code, int initialStock) {
        if (code == null || code.isBlank() || initialStock < 0) {
            throw new IllegalArgumentException("Dữ liệu sản phẩm không hợp lệ");
        }
        this.code = code;
        this.stock = initialStock;
    }
}
~~~

This is an illustrative snippet for **constructor chaining**. `Product(String)` calls `this(code, 0)` to centralize validation rules and field assignments in one place. In Java 17, an explicit `this(...)` or `super(...)` call must be the first statement in a constructor; both cannot be called in the same constructor. Constructor call cycles must not be created (for example, A calling B and then B calling A).

Easily confused rules:

- The **compiler-generated default constructor** only exists if the class **does not declare any constructor at all**. Once `Product(String)` is declared, `new Product()` is no longer automatically valid unless you write a no-argument constructor yourself.
- If a constructor does not explicitly call `this(...)` or `super(...)`, Java inserts the appropriate `super()` call; the code only compiles if the superclass has a no-argument constructor accessible to the subclass.
- A constructor can be `private` to control how objects are created, such as with factory methods; the superclass constructor must be called according to the rules.
- A constructor can throw an exception to reject invalid input state. Do not expose an incompletely initialized object externally through static variables, callbacks, or other threads.
- `final` instance fields must be assigned along every path that completes initialization normally. Use constructors to enforce invariants, such as non-negative stock quantities.

If a constructor calls a method that can be overridden by a subclass, that method may run **before the subclass's own fields have finished initializing**. This is a common design mistake: avoid calling overridable instance methods from a constructor if the method depends on subclass state.

## 5. Static Members: Shared at the Class Level

`static` is for **class fields** and **class methods**; a class can also have static initializer blocks and static nested classes. There is no `static` constructor. You cannot declare a `static` local variable inside a regular Java method. A top-level class cannot be declared `static`; this keyword applies to nested classes in valid positions.

### 5.1. Static Fields

~~~java
class AppSettings {
    static final int MAX_RETRIES = 3;    // primitive constant
    private static int activeSessions;   // shared state
}
~~~

A `static final` field can only be assigned once, but if it points to a mutable object, the object's contents can still change. For a `static final` field of a primitive type or `String` whose initializer is a **constant expression** under Java rules, the value is a *constant variable* and may be compiled inline at usage sites. Do not rely on merely **reading** such a constant variable to trigger the declaring class's static initializer.

Mutable static fields should be treated as **shared state**: two different objects, as well as multiple threads, can access and modify them. The operation `count++` is not atomic; if multiple threads update it concurrently, updates can be lost. In multithreaded scenarios, appropriate synchronization mechanisms must be used (for example, `AtomicInteger`, synchronized, or a design that avoids shared mutable state). `static` by itself does not make code thread-safe.

### 5.2. Static Methods

Static methods are appropriate for pure calculations, utility functions, and factories that do not need `this`. The clearest way to call one is `ClassName.method(...)`. Java allows certain ways of invoking a static method through an object expression, but this should be avoided because it can misleadingly suggest that the call is dispatched based on the object.

~~~java
class UnitConverter {
    private UnitConverter() { } // utility class not intended for instantiation

    static double centimetersToMeters(double centimeters) {
        return centimeters / 100.0;
    }
}
~~~

The snippet above illustrates a utility class. A static method **can** still read or invoke instance members when given an appropriate object, such as `person.getName()`; what is prohibited is using instance members **without an object** in a static context.

### 5.3. Static Initialization and When It Occurs

Static field initializers and static initializer blocks execute in the **order they appear in source code**, during the class initialization phase. This initialization typically occurs right before the first “active use”, such as creating an instance, calling a static method, or accessing a static field that is not a compile-time constant; the JVM has specific rules for class/interface initialization. Each class is initialized once per class entity loaded by the JVM through its corresponding class loader; do not assume it always runs only once across all JVMs or class loaders.

~~~java
class Configuration {
    static String mode = "development";

    static {
        mode = mode.toUpperCase();
    }
}
~~~

After the class is initialized, `Configuration.mode` is `"DEVELOPMENT"`. Avoid complex static initialization, circular dependencies, or hard-to-control side effects. If a static initializer fails due to an exception, using the class can lead to initialization errors such as `ExceptionInInitializerError`.

## 6. Initialization Order: Runnable Java 17 Example

Memory is allocated for an object, fields receive default values, the superclass constructor chain is executed, and then each class's instance field initializers and instance initializer blocks run in their prescribed order before the corresponding constructor body. When a constructor calls `this(...)`, the instance initialization of that same class occurs only **once**, at the link in the chain that executes the superclass call. In the example below, which contains only the nested class `Counter`, you can directly observe the order of static initializers, instance initializers, and constructors.

Save the following content into **MemberOverview.java**:

~~~java
public class MemberOverview {
    static class Counter {
        private static int nextId = 1;

        static {
            System.out.println("Khởi tạo lớp Counter");
        }

        private final int id;
        private String name = "chưa đặt";

        {
            System.out.println("Khởi tạo đối tượng");
        }

        Counter() {
            this("Khách");
        }

        Counter(String name) {
            this.id = nextId++;
            this.name = name;
            System.out.println("Constructor: " + id);
        }

        void rename(String newName) {
            this.name = newName;
        }

        String label() {
            return "#" + id + " " + name;
        }

        static int createdCount() {
            return nextId - 1;
        }
    }

    public static void main(String[] args) {
        Counter first = new Counter();
        Counter second = new Counter("An");

        first.rename("Bình");

        System.out.println(first.label());
        System.out.println(second.label());
        System.out.println("Đã tạo: " + Counter.createdCount());
    }
}
~~~

Compile and run from the directory containing the file (with JDK 17 or later):

~~~bash
javac MemberOverview.java
java MemberOverview
~~~

Expected output:

~~~text
Khởi tạo lớp Counter
Khởi tạo đối tượng
Constructor: 1
Khởi tạo đối tượng
Constructor: 2
#1 Bình
#2 An
Đã tạo: 2
~~~

**Step-by-step explanation:**

1. The first time `new Counter()` is created, the JVM initializes the `Counter` class: it assigns `nextId = 1` and then runs the static block, so it prints “Khởi tạo lớp Counter” **once**.
2. The first object receives default values, then runs the field initializer `name = "chưa đặt"` and the instance initializer block, printing “Khởi tạo đối tượng”. The no-argument constructor delegates to `Counter("Khách")`, and the parameterized constructor assigns `id = 1`, increments `nextId` to 2, and then prints “Constructor: 1”.
3. Creating the second object does not run the static block again. The instance initializer runs for the second object, and the constructor assigns `id = 2`, increments `nextId` to 3, and then prints “Constructor: 2”.
4. `first.rename("Bình")` only modifies `name` of the first object. The second object still has `name = "An"`. The two `id` fields hold two separate values; `nextId` is shared.
5. `Counter.createdCount()` returns `nextId - 1 = 2`, reflecting the number of objects assigned an id in the example. In a real application, this way of counting is only accurate when every object-creation path increments the counter properly and there are no concurrency issues.

### 6.1. Conceptual Distinction Between Memory and Lifecycle

Instance fields exist as part of an object's state; static fields are tied to the class and the class loading mechanism. Local variables and parameters belong to the execution context of a method or constructor. Do not infer that every static field must reside in a specific “physical memory region” or that every local variable is always on the stack: the JIT/JVM has the authority to optimize storage. **Static does not guarantee an object lives forever**; object garbage collection and the possibility of class unloading depend on live references and runtime mechanisms.

## 7. Access Rules and Design Choices

The following access levels apply in valid contexts for fields, methods, and constructors:

| Modifier | General Meaning |
| --- | --- |
| `private` | Accessible only within the declaring class and nested access contexts allowed by Java |
| *package-private* (no modifier specified) | Classes in the same package |
| `protected` | Same package, and subclasses outside the package according to `protected` access rules |
| `public` | Accessible from code elsewhere if its enclosing class/module also permits it |

Being in a named module with `module-info.java` can impose additional restrictions at module boundaries. A `public` member does not guarantee access to all code in all modules if the package has not been exported.

How to choose a member based on the question “does this belong to a specific object or the entire class?”:

| Need | Typically Appropriate Choice | Example |
| --- | --- | --- |
| Each object has different data | `private` instance field | `BankAccount.balance` |
| Behavior depends on an object's state | Instance method | `account.deposit(...)` |
| Validate and establish state upon creation | Constructor | `new BankAccount("An")` |
| Computation that does not need object state | Static method | `Math.max(a, b)` |
| Shared constant with a fixed value | `static final` | `MAX_RETRIES` |
| Mutable shared state | Static field, only when truly necessary | Synchronized shared counter |

A constructor must ensure the object is valid; methods should represent clear behaviors or queries. If an object must maintain invariants such as a non-negative balance, restrict permission to update the field and do not allow callers to set values arbitrarily.

## 8. Common Mistakes and How to Spot Them

1. **Using an instance field from a static method without an object**:
   ~~~java
   class Wrong {
       int value = 5;
       static int read() {
           // return value; // Compilation ERROR: non-static variable
           return new Wrong().value; // valid because there is an object
       }
   }
   ~~~
   The commented-out line intentionally illustrates the error and will not compile if uncommented.
2. **Confusing constructors with methods**: `void Product()` is a method named `Product`, **not** a constructor. Constructors do not declare a return type.
3. **Assuming an empty constructor still exists automatically**: simply declaring one parameterized constructor causes the compiler-generated default constructor to no longer exist.
4. **Mistaking `final` for deep immutability**: final locks reassignment of the variable/field, not all internal state inside the referenced object.
5. **Confusing static methods with instance dispatch**: static methods are selected by type at compile time and can hide other static methods; only eligible instance methods are overridden and dynamically dispatched.
6. **Assuming each object has its own copy of a static field**: objects of the same loaded class see the same field; changes from one place can affect another.
7. **Assuming `counter++` on a static field is thread-safe**: this is a read–compute–write sequence of operations and requires a synchronization mechanism or a design that avoids shared state.
8. **Reading a field before setting the intended value**: default values like `0`/`null` can mask missing initialization bugs. Prefer constructors that establish invariants, and use `final` where appropriate.
9. **Overusing static for per-user or per-session data**: data can be shared unintentionally; use objects that own their own state instead of global static fields.
10. **Leaking `this` too early from a constructor**: callbacks or other threads may observe an incompletely initialized object, leading to hard-to-reproduce bugs.

## 9. Self-Check Your Reasoning

**Scenario A.** There are two instances `a` and `b` of the same class. `a.name = "A"` and `b.name = "B"`. Then `a.name = "C"` is assigned. What happens to `b.name`? If `name` is an instance field, it remains `"B"`; each object has its own state.

**Scenario B.** A static field `total` is incremented from 0 to 1 through an object. What will a static method of the class reading `total` see in the same sequential execution context? The value 1, because both operations act on the same static field.

**Scenario C.** A class defines `Book(String title)` but does not define `Book()`. Will the call `new Book()` work? No, because the compiler does not automatically add a no-arg constructor once the class has declared any constructor.

**Scenario D.** Do the default constructor, field initializers, and static blocks run every time an instance method is called? No: static initializers follow class initialization timing; instance initializers and constructors take place during object creation and do not rerun just because a method is called.

When reading a new class, identify in turn: (1) which fields are per-instance and which are static; (2) object creation paths and invariants in constructors; (3) which methods require `this`; (4) who is permitted to access or modify fields; (5) whether static mutable state introduces global dependencies or concurrency bugs. Mastering these five points forms the foundation for understanding encapsulation, inheritance, polymorphism, object lifecycle, and larger Java designs.
