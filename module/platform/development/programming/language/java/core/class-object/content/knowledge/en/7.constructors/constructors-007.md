# `this()` and `super()` Chaining: Call Placement in Java 21

## 1. Goal: Understanding How Constructors Chain Together

In Java, a constructor is used to complete the initialization of an instance. If a class has multiple constructors, one constructor can **delegate** to another constructor in the same class using `this(...)`. If a class inherits from another class, a constructor can call a constructor of the parent class using `super(...)`.

These two forms are commonly referred to collectively as **explicit constructor invocation**:

- **`this(...)`**: calls **another constructor in the same class**, on **the same object being created**.
- **`super(...)`**: calls **an appropriate constructor of the direct superclass**, to initialize the superclass part of **the same object**.

They are **not** instance methods, nor do they mean “creating another object”. Constructors have no return type and cannot be called again arbitrarily on an already constructed object.

**Core Java 21 rule:** if you write `this(...)` or `super(...)` explicitly in a constructor body, **that call must be the first statement** of the constructor. Before it, you cannot place a local variable declaration, an assignment statement, `System.out.println(...)`, an `if` block, a method call, or any other statement.

Valid example:

```java
class Base {
    Base(int code) {
        System.out.println("Base: " + code);
    }
}

class Child extends Base {
    Child() {
        this(5);  // Start of Child() constructor.
    }

    Child(int code) {
        super(code); // Start of Child(int) constructor.
        System.out.println("Child: " + code);
    }
}
```

These are **compilable class declarations**, without a `main` method to run standalone. When using `new Child()`, `Child()` calls `Child(5)`, the `Child(5)` constructor calls `Base(5)`, and then the rest of the `Child(5)` body runs. No additional `Child` or `Base` object is created beyond the instance under construction.

> This article applies to **Java 21**. When consulting documentation for newer Java versions, note that the rules regarding statements before a constructor invocation may differ. If you need to compile strictly according to Java 21, use JDK 21 or a compiler that supports `--release 21` mode, rather than applying the syntax of another version.

## 2. Distinguishing `this`, `this(...)`, `super`, and `super(...)`

Similar syntax, but different meanings:

| Expression | Kind | What Is It Used For? |
| --- | --- | --- |
| `this` | Reference in instance context | Refers to the current object, for example `this.name`. |
| `this(...)` | Constructor invocation | Delegates to another constructor in the **same class**. |
| `super.field` | Superclass member access according to rules | Explicitly specifies a superclass field in a valid context. |
| `super.method(...)` | Method call from superclass | Uses the appropriate superclass implementation; **not** a constructor invocation. |
| `super(...)` | Constructor invocation | Calls a constructor of the **direct superclass**. |
| `new Child(...)` | Class instance creation expression | Creates a new instance, selects the target constructor, and starts the initialization chain. |

Example:

```java
class Person {
    private final String name;

    Person(String name) {
        this.name = name;       // Field assignment; NOT this(...).
    }

    String name() {
        return this.name;       // Accesses the receiver's field.
    }
}
```

`this.name = name` **does not need** to be the first statement, because it is a field assignment. Java 21's “first statement” constraint applies specifically to the **constructor invocation** forms `this(...)` or `super(...)`.

Similarly, inside an instance method, `super.toString()` is a **method invocation**, does not call a superclass constructor again, and therefore is not subject to the constructor-first placement rule.

## 3. `this(...)`: Delegating Between Constructors in the Same Class

Suppose a class supports multiple ways to initialize: providing no information, providing only a name, or providing both a name and a quantity. There is no need to duplicate validation logic in every constructor. A constructor with fewer parameters can call an overload with more parameters using `this(...)`.

```java
class Course {
    private final String title;
    private final int capacity;

    Course() {
        this("Untitled", 10);
    }

    Course(String title) {
        this(title, 10);
    }

    Course(String title, int capacity) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title required");
        }
        if (capacity <= 0) {
            throw new IllegalArgumentException("capacity must be positive");
        }
        this.title = title;
        this.capacity = capacity;
    }

    String summary() {
        return title + " (" + capacity + ")";
    }
}
```

This is a **compilable class declaration** without its own `main` method. The calls `new Course()`, `new Course("Java")`, and `new Course("Java", 20)` all lead to the `Course(String, int)` constructor, where validation is centralized.

- `Course()` selects the constructor with parameter list `(String, int)` because it receives the two arguments `"Untitled"` and `10`.
- `Course(String)` also selects the `(String, int)` constructor, but passes the name provided by the user.
- `Course(String, int)` is the end of the delegation chain in this class; if there is no explicit `super(...)`, Java 21 inserts the appropriate `super()` call at the beginning of the constructor.
- The `final` fields are assigned only in the full-parameter constructor. The delegating constructors **do not reassign** them.

A single call to `new Course()` creates **one instance**, not three instances. Passing through multiple constructors **does not repeat** object memory allocation or the class's initializers.

### Standalone Program Demonstrating `this(...)`

Create the file **`ThisChainingDemo.java`**:

```java
class Ticket {
    private final String type;
    private final int quantity;

    Ticket() {
        this("standard");
        System.out.println("Ticket() body");
    }

    Ticket(String type) {
        this(type, 1);
        System.out.println("Ticket(String) body");
    }

    Ticket(String type, int quantity) {
        this.type = type;
        this.quantity = quantity;
        System.out.println("Ticket(String,int) body");
    }

    String summary() {
        return type + " x " + quantity;
    }
}

public class ThisChainingDemo {
    public static void main(String[] args) {
        Ticket ticket = new Ticket();
        System.out.println(ticket.summary());
    }
}
```

Compile and run with Java 21:

```bash
javac --release 21 ThisChainingDemo.java
java ThisChainingDemo
```

**Standard output:**

```text
Ticket(String,int) body
Ticket(String) body
Ticket() body
standard x 1
```

The `new Ticket()` call enters `Ticket()`, then delegates along the chain:

```text
new Ticket()
    |
    +--> Ticket()
             |
             +--> Ticket("standard")
                        |
                        +--> Ticket("standard", 1)
                                    |
                                    +--> super() to Object()
                                    |
                                    +--> Assign type, quantity
                                    +--> Print "Ticket(String,int) body"
                        |
                        +--> Print "Ticket(String) body"
             |
             +--> Print "Ticket() body"
    |
    +--> main calls summary()
```

This is a **call-and-return** structure: the deepest target constructor finishes first, and then returns in turn to the delegating constructors to run the statements **after `this(...)`**. `Object()` prints nothing in this example.

**Common point of confusion:** `this(...)` is not a free-form method call that can be placed in the middle of a constructor. In Java 21, it **must appear first** in the constructor and cannot be used in a method or initializer block.

## 4. `super(...)`: Initializing the Superclass Part

A subclass constructor must always adhere to proper superclass initialization. In Java 21, a subclass constructor can begin with an explicit `super(args)` call to select a constructor of the direct superclass.

```java
class Vehicle {
    private final String category;

    Vehicle(String category) {
        this.category = category;
    }

    String category() {
        return category;
    }
}

class Car extends Vehicle {
    private final String model;

    Car(String model) {
        super("road"); // Required when the superclass has no Vehicle().
        this.model = model;
    }

    String describe() {
        return category() + ": " + model;
    }
}
```

The class snippet above compiles, though it does not contain `main`. `Vehicle` only has `Vehicle(String)`, so `Car(String)` **must** call a compatible superclass constructor. `super("road")` comes first in the constructor, followed by the assignment `this.model = model`.

The `super("road")` statement does not cause a separate `Vehicle` object to appear. `new Car("Sedan")` creates one `Car` instance, in which the state inherited from `Vehicle` is also initialized through the superclass constructor.

### Standalone Example: Parent Constructor Executes Before Child Constructor

Create the file **`SuperChainingDemo.java`**:

```java
class Equipment {
    private final String family;

    Equipment(String family) {
        this.family = family;
        System.out.println("Equipment constructor");
    }

    String family() {
        return family;
    }
}

class Laptop extends Equipment {
    private final String model;

    Laptop(String model) {
        super("computer");
        this.model = model;
        System.out.println("Laptop constructor");
    }

    String description() {
        return family() + "/" + model;
    }
}

public class SuperChainingDemo {
    public static void main(String[] args) {
        Laptop laptop = new Laptop("Think");
        System.out.println(laptop.description());
    }
}
```

Compile and run:

```bash
javac --release 21 SuperChainingDemo.java
java SuperChainingDemo
```

```text
Equipment constructor
Laptop constructor
computer/Think
```

In `Laptop(String)`, `super("computer")` transfers control to `Equipment(String)`. Only **after the `Equipment` constructor completes normally** does the remainder of the `Laptop` constructor execute. This is one way Java ensures the superclass part is initialized before the statements in the subclass constructor body.

### `super(...)` Only Calls the Direct Superclass

Suppose the inheritance hierarchy is `Grandparent ← Parent ← Child`. A `Child` constructor does not directly call a `Grandparent` constructor using a form like `super.super(...)`. `Child` calls a `Parent` constructor, and the `Parent` constructor itself calls a `Grandparent` constructor along the parent class's chain. Each class is responsible for the constructor of its **direct** superclass.

## 5. Java 21's “First Statement” Rule

In **Java 21**, a constructor can have an explicit `this(...)` or `super(...)` call, but that call **must appear as the first statement in the constructor body**.

### Valid

```java
class Valid {
    Valid() {
        this(1);
        System.out.println("after this");
    }

    Valid(int value) {
        super();
        System.out.println("value=" + value);
    }
}
```

`this(1)` appears at the beginning of `Valid()`. `super()` appears at the beginning of `Valid(int)`. The `println` statements that follow are valid.

### Invalid: Statement Before `this(...)`

```java
// class Invalid {
//     Invalid() {
//         int count = 1;    // Preceding statement.
//         this(count);       // Invalid in Java 21.
//     }
//
//     Invalid(int count) {
//     }
// }
```

The line `int count = 1;` cannot be placed before `this(count)` in Java 21. Even when you want to prepare a value to pass to another constructor, that value must be computed **within a valid argument expression** or the logic must be moved into an appropriate static helper/factory.

Fix:

```java
class ValidCount {
    ValidCount() {
        this(1);
    }

    ValidCount(int count) {
        System.out.println(count);
    }
}
```

### Invalid: Logging Before `super(...)`

```java
// class Parent {
//     Parent(int id) { }
// }
//
// class BadChild extends Parent {
//     BadChild() {
//         System.out.println("before parent");
//         super(7); // Invalid: not first in Java 21.
//     }
// }
```

Fix this by placing `super(7)` first and printing afterward, or by placing the log during the execution of the superclass constructor if that fits the design.

```java
class Parent {
    Parent(int id) {
        System.out.println("parent " + id);
    }
}

class GoodChild extends Parent {
    GoodChild() {
        super(7);
        System.out.println("child");
    }
}
```

If `new GoodChild()` is called inside a method, the two lines printed in order are `parent 7` and then `child`. The declaration snippet above compiles, though it does not contain its own `main` method.

### Invalid: Hiding a Constructor Invocation Inside a Conditional Block

```java
// class Bad {
//     Bad(boolean enabled) {
//         if (enabled) {
//             this(); // Invalid: constructor invocation cannot be placed inside an if.
//         }
//     }
//
//     Bad() { }
// }
```

Java 21 does not allow placing `this()` or `super()` as an arbitrary statement inside `if`, `for`, `while`, `try`, a method, or an instance initializer. To choose initialization conditionally, you typically pass a **conditional expression** as an argument to the leading call:

```java
class Choice {
    private final int value;

    Choice(boolean enabled) {
        this(enabled ? 10 : 0);
    }

    Choice(int value) {
        this.value = value;
    }

    int getValue() {
        return value;
    }
}
```

For example, `new Choice(true).getValue()` returns `10`; `new Choice(false).getValue()` returns `0`. The condition is evaluated when **evaluating the argument** of `this(...)`, rather than placing an `if` statement before the constructor invocation.

## 6. Can a Single Constructor Include Both `this(...)` and `super(...)`?

**No.** In a Java 21 constructor, you cannot write both explicit constructor invocations. Because each call must be the first statement, two statements cannot both be first in a single constructor.

Intentionally invalid example:

```java
// class Parent {
//     Parent() { }
// }
//
// class Child extends Parent {
//     Child() {
//         this(1);
//         super(); // Invalid: cannot have a second invocation.
//     }
//
//     Child(int value) {
//     }
// }
```

However, **both keywords can still appear in different constructors of the same class**:

```java
class Base {
    Base(String code) {
        System.out.println("Base:" + code);
    }
}

class Derived extends Base {
    Derived() {
        this("A");
    }

    Derived(String code) {
        super(code);
        System.out.println("Derived:" + code);
    }
}
```

`Derived()` begins with `this("A")`. The target constructor `Derived(String)` begins with `super(code)`. This is a **valid chain** and does not violate the rule: each constructor has only **one** explicit constructor invocation at the beginning of its body.

If you create `new Derived()`, the two lines printed are `Base:A` and `Derived:A`. No second `Base` constructor is called.

### Why Does Delegating with `this(...)` Still Call the Superclass?

An instance's constructor chain must ultimately reach proper superclass initialization. If `Derived()` calls `this("A")`, and then `Derived(String)` calls `super("A")`, the superclass is initialized **through the final target constructor of the chain in `Derived`**.

You must not manually add `super()` to `Derived()` after `this("A")`. That would cause a conflict and semantically amounts to requesting duplicate superclass initialization.

## 7. What Happens If Neither `this(...)` Nor `super(...)` Is Written?

In a constructor of a normal class other than `Object`, if no explicit constructor invocation is written, Java 21 essentially treats it as having an **implicit `super()`** call at the beginning of the constructor (if the conditions are valid).

```java
class Parent {
    Parent() {
        System.out.println("Parent()");
    }
}

class Child extends Parent {
    Child() {
        System.out.println("Child()");
    }
}
```

In this example, `Child()` does not write `super()`, yet the compiler still calls the no-argument constructor of `Parent` before executing the print statement in the `Child()` body.

Same normal execution semantics:

```java
class Child extends Parent {
    Child() {
        super();
        System.out.println("Child()");
    }
}
```

The two `Child` declarations above are **two separate versions for comparison**, not placed simultaneously in the same program. When calling `new Child()`, the output is:

```text
Parent()
Child()
```

### Relationship to the Default Constructor

If **the entire subclass declares no constructors**, the compiler implicitly declares a no-argument **default constructor** and calls `super()` accordingly:

```java
class Parent {
    Parent() {
        System.out.println("Parent()");
    }
}

class Child extends Parent {
    // No constructor declared by the author.
}
```

`Child` is given a default constructor according to the rules for normal classes. However, if `Parent()` does not exist or is not accessible, the compiler's attempt to generate a default constructor for `Child` **does not guarantee that the class will compile**. The absence of a constructor declaration in the subclass **does not cause the compiler to invent a matching superclass constructor**.

### `java.lang.Object` Is the Root Case

Every normal class ultimately has `java.lang.Object` at the top of its inheritance chain. The constructor of `Object` itself cannot continue calling a nonexistent superclass. View the implicit `super()` rule as a rule for normal classes that have a superclass, **not something to apply mechanically to the constructor of `Object` itself**.

## 8. Missing a Matching `super()` Constructor: A Very Common Compile Error

Example:

```java
// class Base {
//     Base(int id) { }
// }
//
// class Derived extends Base {
//     Derived() {
//         System.out.println("Derived");
//     }
// }
```

This is an **intentionally invalid** snippet, commented out. `Base` only declares `Base(int)`; it **has no `Base()` constructor**. Because `Derived()` does not write `this(...)` or `super(...)`, the compiler will need to call `super()` implicitly. That call has no valid target constructor, so compilation fails.

Fix:

```java
class Base {
    private final int id;

    Base(int id) {
        this.id = id;
    }

    int id() {
        return id;
    }
}

class Derived extends Base {
    Derived() {
        super(7);
    }
}
```

In the fixed version, `super(7)` appears at the beginning of `Derived()` and matches the `Base(int)` constructor. This code compiles when the constructors are accessible in the corresponding context.

### Superclass Constructor Exists but Is Inaccessible

Not only a missing `Base()`, an **inaccessible** no-argument constructor also makes an implicit or explicit `super()` invalid:

```java
// class Base {
//     private Base() { }
// }
//
// class Child extends Base {
//     Child() { } // Implicit super() cannot call private Base().
// }
```

This example is intentionally invalid when the two classes are top-level, with no special relationship allowing private access. You must design the superclass constructor with an appropriate access level, or provide another permitted initialization path.

If the superclass requires arguments, you should **select an appropriate constructor using `super(args)`** from the subclass constructor; do not arbitrarily add an empty constructor to the superclass just to get past a compiler error when doing so could create an invalid state.

## 9. Overload Resolution Rules for `this(...)` and `super(...)`

Just like overloaded method calls, a class can have **multiple constructors with different parameter lists**, and the compiler must select a target constructor corresponding to **the number and static types of the argument expressions, as well as the permitted conversions**.

```java
class Base {
    Base(int number) {
        System.out.println("Base.int=" + number);
    }

    Base(String name) {
        System.out.println("Base.String=" + name);
    }
}

class Child extends Base {
    Child() {
        super(5);
    }

    Child(String name) {
        super(name);
    }
}
```

`new Child()` uses `super(5)` and calls `Base(int)`. `new Child("Lan")` uses `super(name)` and calls `Base(String)`. In Java 21, both constructors of `Child` are valid because `super(...)` comes first.

### Ambiguous Constructor Invocation with `null`

```java
class Choice {
    Choice(String value) {
    }

    Choice(Integer value) {
    }

    static void demonstrate() {
        // new Choice(null); // Ambiguous error: String or Integer?
        new Choice((String) null);
    }
}
```

Java does not use a runtime type of `null` to guess an overload. Both `String` and `Integer` are reference types with no subtyping relationship that determines a most specific overload; an explicit cast can select one constructor, though **the value is still `null`**.

### Passing Arguments to `this(...)` Does Not Mean Copying an Object

In `Child() { this(5); }`, the expression `5` is an argument to another constructor, and the compiler/JVM does not create an extra `Child` just because there is a `this(...)` call. One new instance is created by **the `new Child()` expression**, while the constructors in the chain participate together in constructing that instance.

## 10. Arguments to the First Call: What Can Be Used?

Because Java 21 requires `this(...)`/`super(...)` to appear first in a constructor, you **cannot prepare a local variable with a preceding statement**. However, the arguments can be **valid expressions** such as constructor parameters, literals, computations, or static helpers that do not depend on uninitialized instance state.

Example:

```java
class Document {
    private final String title;

    Document() {
        this(defaultTitle());
    }

    Document(String title) {
        this.title = title;
    }

    private static String defaultTitle() {
        return "Untitled";
    }

    String title() {
        return title;
    }
}
```

`defaultTitle()` is a **static method**, so it can be used to compute the argument for `this(...)` without needing a fully constructed object. `new Document().title()` returns `Untitled`.

### Using Constructor Parameters and Computed Expressions

```java
class CountBase {
    CountBase(int count) {
        System.out.println("count=" + count);
    }
}

class CountChild extends CountBase {
    CountChild(int requested) {
        super(Math.max(0, requested));
    }
}
```

`Math.max` is a static method; the constructor parameter `requested` already holds a value from the caller. `super(Math.max(0, requested))` is the first statement and has a valid argument expression. `new CountChild(-2)` causes the superclass to print `count=0`.

### Do Not Access the Incomplete Instance from an Explicit Constructor Invocation

In Java 21, an **explicit constructor invocation** is a context restricted from referencing the current instance (a *static context* according to the relevant JLS semantics). You may not use `this` or `super` as a receiver or directly reference instance fields or methods of the object under construction to compute arguments.

Intentionally invalid example:

```java
// class Bad {
//     private int amount = 10;
//
//     Bad() {
//         this(amount); // Error: using an instance field of the current object here.
//     }
//
//     Bad(int amount) {
//     }
// }
```

Fix this by using a parameter, literal, or static helper, or by moving logic that depends on instance fields to **after** the constructor invocation has completed, provided the design remains valid.

Do not confuse this with a statement like `this.name = name;` **after `super(...)`** in the constructor body; that field assignment is valid when the context and definite assignment rules are satisfied.

### Side Effects in Argument Expressions

An argument expression can call a static method that logs output or modifies static state. That can produce output **before** the target constructor body runs, even though the `this(...)`/`super(...)` statement is still at the beginning of the constructor in terms of **syntactic position**. “The constructor call must be first” does not mean “no expression is evaluated before the target constructor runs”.

File **`ConstructorArgumentDemo.java`**:

```java
class Root {
    Root(int id) {
        System.out.println("Root(" + id + ")");
    }
}

class Branch extends Root {
    private static int supply() {
        System.out.println("computing argument");
        return 9;
    }

    Branch() {
        super(supply());
        System.out.println("Branch()");
    }
}

public class ConstructorArgumentDemo {
    public static void main(String[] args) {
        new Branch();
    }
}
```

```bash
javac --release 21 ConstructorArgumentDemo.java
java ConstructorArgumentDemo
```

```text
computing argument
Root(9)
Branch()
```

`supply()` is called to compute the **argument** for `super(...)`. It runs before the `Root(int)` constructor begins printing; this does not violate the first-statement rule. Side effects in constructor arguments should not be overused because they make code hard to predict.

## 11. Initialization Order in a Multi-Class Chain

What learners confuse most often is not individual syntax, but **what runs first and what runs afterward** when there are:

- Superclass constructors.
- Instance field initializers and instance initializer blocks of the superclass/subclass.
- `this(...)` constructor chaining between overloads in the same class.
- Constructor bodies at each level.

In a normal class example, the process is described by the basic order:

1. The necessary classes are **class-initialized** according to their own rules when used (static initialization); this is a different mechanism from instance initialization.
2. When `new Child(...)` is executed, the object is allocated and instance fields are given their **default values**.
3. The constructor chain passes through `this(...)` if present, and then reaches the appropriate `super(...)` or `super()` call.
4. Superclass constructors and instance initialization execute in order from **root to child**.
5. After the superclass constructor completes normally, the **instance field initializers** and **instance initializer blocks** of the current class run in **the order they appear in the source code**.
6. The body of the target constructor in the current class runs; the constructors in that class that called `this(...)` resume running the portion **after the delegation call** when the target constructor returns.

The initializers of **a class** do not re-run multiple times simply because one constructor delegates via `this(...)` to another constructor of **the same object**.

### Consolidated Java 21 Program and Deterministic Stdout

Create the file **`ConstructionOrderDemo.java`**:

```java
class Parent {
    Parent(int id) {
        System.out.println("Parent constructor: " + id);
    }
}

class Child extends Parent {
    private int value = initializeValue();

    {
        System.out.println("Child instance block");
    }

    Child() {
        this(3);
        System.out.println("Child() body");
    }

    Child(int id) {
        this(id, "ready");
        System.out.println("Child(int) body");
    }

    Child(int id, String label) {
        super(id);
        value += 2;
        System.out.println("Child(int,String) body: " + label);
    }

    private int initializeValue() {
        System.out.println("Child field initializer");
        return 5;
    }

    int value() {
        return value;
    }
}

public class ConstructionOrderDemo {
    public static void main(String[] args) {
        System.out.println("begin");
        Child child = new Child();
        System.out.println("value=" + child.value());
    }
}
```

Commands:

```bash
javac --release 21 ConstructionOrderDemo.java
java ConstructionOrderDemo
```

Exact output:

```text
begin
Parent constructor: 3
Child field initializer
Child instance block
Child(int,String) body: ready
Child(int) body
Child() body
value=7
```

**Line-by-line explanation:**

1. `main` prints `begin` before calling `new Child()`.
2. `Child()` calls `this(3)`; `Child(int)` calls `this(3, "ready")`; `Child(int, String)` calls `super(3)`. Therefore, the `Parent(int)` constructor prints `Parent constructor: 3`.
3. After the superclass finishes, the field initializer `value = initializeValue()` runs **once** during construction of the `Child` object, printing `Child field initializer` and returning `5`.
4. The instance initializer block next prints `Child instance block`, also **only once**.
5. The body of `Child(int, String)` increments `value` from `5` to `7` and prints `Child(int,String) body: ready`.
6. The `Child(int)` constructor, which had been waiting for `this(...)` to complete, now runs the print line `Child(int) body`.
7. The `Child()` constructor also resumes after `this(3)` and prints `Child() body`.
8. `main` reads the field via the getter and prints `value=7`.

The program demonstrates three points: **the superclass is built before the subclass's instance part**, **`this(...)` does not create an additional object**, and **instance initializers do not repeat according to the number of overloads traversed**.

### Control Flow Diagram

```text
main: new Child()
   |
   v
Child()
   | this(3)
   v
Child(int)
   | this(3, "ready")
   v
Child(int, String)
   | super(3)
   v
Parent(int)                 -> Print Parent constructor: 3
   |
   v
Child field initializer     -> Print Child field initializer; value = 5
   |
   v
Child instance block        -> Print Child instance block
   |
   v
Child(int, String) body     -> value = 7; print Child(int,String) ...
   |
   v
Child(int) body             -> Print Child(int) body
   |
   v
Child() body                -> Print Child() body
   |
   v
main                        -> Print value=7
```

This is a diagram specific to this example; it does not fully represent all steps of allocation, class verification, class loading, or exception cases.

## 12. Do Not Create Circular Recursive `this(...)` Chains

A `this(...)` constructor call must eventually lead to a constructor that **does not delegate back in a cycle**. If two constructors call each other in a cycle, Java detects a **recursive constructor invocation**.

Intentionally non-compiling example:

```java
// class Loop {
//     Loop() {
//         this(1);
//     }
//
//     Loop(int n) {
//         this();
//     }
// }
```

The chain `Loop() → Loop(int) → Loop() → ...` has no stopping point that calls an appropriate superclass constructor. The compiler prevents this structure.

The fix is to have a final target constructor perform valid initialization:

```java
class NonRecursive {
    private final int number;

    NonRecursive() {
        this(1);
    }

    NonRecursive(int number) {
        this.number = number;
    }
}
```

In `NonRecursive(int)`, there is no explicit constructor invocation; the compiler performs the appropriate implicit `super()`. From there, initialization completes and returns to `NonRecursive()`.

### Why Does Java Prohibit Constructor Cycles?

Each constructor is a way to initialize the same instance. If constructors only delegate in circles and have no path to complete superclass initialization/instance initialization, there is no valid object construction progress. Prohibiting cycles at **compile time** helps prevent this error before the program runs.

## 13. `final` Fields and Constructor Chaining

A `final` field without an initializer at its declaration site (a *blank final instance field*) must be **assigned according to the rules of definite assignment** during initialization; constructors cannot be allowed to complete normally while the field remains unassigned.

Constructor chaining typically helps centralize the assignment in one place:

```java
class UserAccount {
    private final String username;
    private final int level;

    UserAccount(String username) {
        this(username, 1);
    }

    UserAccount(String username, int level) {
        if (username == null || username.isBlank()) {
            throw new IllegalArgumentException("username required");
        }
        if (level < 1) {
            throw new IllegalArgumentException("level must be positive");
        }
        this.username = username;
        this.level = level;
    }

    String summary() {
        return username + ":" + level;
    }
}
```

The two `final` fields are assigned once in the target constructor `UserAccount(String,int)`. `UserAccount(String)` calls `this(username, 1)` and does not need to reassign the fields. If you try `this.level = 2;` after `this(...)`, reassigning a `final` field that has already been definitely assigned can cause the compiler to report an error.

Placing validation in the target constructor helps overloads maintain consistent invariants; this is also a way to keep a single primary initialization path (*constructor delegation*).

### Distinguishing This from Field Assignment in the Superclass

A subclass **cannot arbitrarily assign a private final field of the superclass on its own**. If the superclass has required fields, the superclass constructor must receive sufficient data or initialize them itself according to its contract; the subclass passes valid data via `super(args)`.

You should not use `super(...)` merely to “get past the compiler” while the passed values violate the superclass's invariants.

## 14. `throws` and Exceptions in the Constructor Chain

A constructor can **throw checked exceptions**. If the target superclass constructor or target same-class constructor declares a checked exception that must be handled according to language rules, the calling constructor must typically **declare an appropriate `throws` clause**. In Java 21, you cannot wrap an explicit `super(...)`/`this(...)` with a `try` placed before it, because the invocation must be the first statement.

Valid example:

```java
class DataSource {
    DataSource(String path) throws java.io.IOException {
        if (path.isBlank()) {
            throw new java.io.IOException("empty path");
        }
    }
}

class FileSource extends DataSource {
    FileSource(String path) throws java.io.IOException {
        super(path);
    }
}
```

`FileSource(String)` declares `throws IOException` to match the called superclass constructor.

### Runnable Program Catching the Exception at Object Creation

File **`CheckedConstructorDemo.java`**:

```java
class ReaderBase {
    ReaderBase(String file) throws java.io.IOException {
        if (file.isEmpty()) {
            throw new java.io.IOException("filename missing");
        }
        System.out.println("reader opened");
    }
}

class TextReader extends ReaderBase {
    TextReader(String file) throws java.io.IOException {
        super(file);
        System.out.println("text reader ready");
    }
}

public class CheckedConstructorDemo {
    public static void main(String[] args) {
        try {
            new TextReader("");
        } catch (java.io.IOException ex) {
            System.out.println("error: " + ex.getMessage());
        }

        try {
            new TextReader("data.txt");
        } catch (java.io.IOException ex) {
            System.out.println("unexpected");
        }
    }
}
```

Commands:

```bash
javac --release 21 CheckedConstructorDemo.java
java CheckedConstructorDemo
```

Output:

```text
error: filename missing
reader opened
text reader ready
```

In the first creation, the `ReaderBase` constructor throws `IOException`, so the `TextReader` body **does not** run; the exception is caught in `main`. In the second creation, the superclass completes, and then the subclass prints the line `text reader ready`. The example illustrates exception flow and does not actually open the file `data.txt`; the filename is just a string used to check the condition.

One detail worth remembering: if the superclass only has a no-argument constructor with `throws IOException` and the subclass intends to use a default constructor/implicit `super()`, the checked exception rules must still be satisfied. You usually need to declare an appropriate subclass constructor with `throws IOException` rather than assuming the compiler will automatically add a `throws` declaration.

## 15. Constructors and Overridden Methods: Avoid Calling Overridden Methods Too Early

The superclass constructor executes before the subclass's field initializers and constructor body finish. If the superclass constructor calls an **overridable instance method**, dynamic dispatch may run the subclass's method **before the subclass state has finished initializing**.

Create the file **`EarlyDispatchDemo.java`**:

```java
class Parent {
    Parent() {
        display();
    }

    void display() {
        System.out.println("Parent.display");
    }
}

class Child extends Parent {
    private int level = 7;

    @Override
    void display() {
        System.out.println("level=" + level);
    }
}

public class EarlyDispatchDemo {
    public static void main(String[] args) {
        Child child = new Child();
        child.display();
    }
}
```

Compile and run:

```bash
javac --release 21 EarlyDispatchDemo.java
java EarlyDispatchDemo
```

```text
level=0
level=7
```

**Why is it 0 the first time?**

1. `new Child()` begins constructing `Child`, then goes through the superclass constructor `Parent()`.
2. `Parent()` calls `display()`. Because the runtime receiver is the `Child` object itself, Java **dispatches** to `Child.display()` even though object creation has not finished.
3. At that point, the `level` field of `Child` still holds **the default value `0`**, because the field initializer `level = 7` has not run yet.
4. Only after `Parent()` returns does `Child`'s initializer assign `7`. The call `child.display()` after the constructor completes prints `level=7`.

This is not a syntax error of `this(...)` or `super(...)`, but a consequence of **runtime polymorphism during object construction**. Avoid calling an overridable method from a constructor when a subclass implementation might depend on uninitialized fields.

## 16. Special Cases to Know So You Do Not Misapply the Rules

### 16.1. Constructors Are Neither Inherited Nor Overridden

A subclass **does not inherit** superclass constructors. `super(...)` is a call to an appropriate target constructor, not overriding. Two constructors in two classes that both accept `String` are **not** “constructor overriding”.

A constructor is also not a method; it cannot be declared `static`, `final`, or `abstract`, and it has no return type.

### 16.2. The Default Constructor Differs from `this()`

If a normal class **declares no constructors**, the compiler can implicitly generate a no-argument **default constructor**, with an implicit `super()` according to the rules.

Inside a constructor **that you write**, `this()` is instead a call to **the no-argument constructor of the same class**; the target constructor must exist. If the class only has a constructor taking `int` and you write `this()`, the compiler does not generate an extra no-arg constructor to satisfy it.

```java
// class X {
//     X(int n) { }
//
//     X(String s) {
//         this(); // Error: there is no X() to call.
//     }
// }
```

### 16.3. Inner Classes and Qualified Superclass Invocation

With a non-static inner class, the inner object may require an **enclosing instance**. Some constructors in an inner-class hierarchy can use a qualified superclass constructor invocation form such as `enclosingExpression.super(...)` under specific language conditions, in addition to the two basic forms `this(...)` and `super(...)`.

At an introductory level, remember the enclosing-instance requirement and do not automatically apply top-level class `super()` syntax to every complex inner-class situation. These cases are still subject to the corresponding constraints on explicit constructor invocations in Java 21.

### 16.4. Enums and Records Have Their Own Constructor Rules

- **Enums** have their instance set managed by Java according to enum constants; you do not create them with `new EnumName()` from application code, and enum constructors have their own restrictions.
- **Records** (supported in Java 21) have a **canonical constructor** tied to their record components; additional constructors have special delegation rules. You cannot assume a record like `record Point(int x, int y) {}` automatically has a no-arg constructor like an empty class.
- **Anonymous classes** also have their own implicit constructor rules; they have no source-level class name for you to call `this(...)`/`super(...)` like a normal named class.

This lesson focuses on **constructor chaining in normal Java classes**. When working with enum/record/inner/anonymous classes, apply the proper rules according to the declaration kind.

### 16.5. When Java 21 Compatibility Is Required

If the project compiles with Java 21, the following example is **invalid**, even if someone points to another language or Java version that allows it:

```java
// class Example {
//     Example() {
//         System.out.println("before");
//         super(); // Not allowed: in Java 21, super() must come first.
//     }
// }
```

To test Java 21 syntax when an appropriate JDK is available, you can compile with `javac --release 21 FileName.java`. If you are using JDK 21 itself, the command `javac FileName.java` also uses that version's language rules under the default configuration. Do not confuse the `--release` flag with automatically being able to run on a lower JDK runtime merely by choosing the syntax.

## 17. Checklist for Analyzing a Java 21 Constructor Chain

When reading a constructor, answer these questions in order:

1. **What is the current class?** What direct superclass does it have, what constructors does the superclass have, and what are their access levels?
2. **What is the first statement of the constructor?** If it is `this(...)`, follow it to the constructor in the same class; if it is `super(...)`, follow it to the superclass constructor; if there is no explicit invocation, consider the appropriate implicit `super()`.
3. **Which target constructor do the arguments match?** Check the argument count, types, overload resolution, accessibility, and checked exceptions.
4. **Are there any statements before the explicit constructor invocation?** In **Java 21**, that is invalid.
5. **Is there a `this(...)` call cycle?** Every delegation chain within the same class must have a valid terminating path.
6. **How is the superclass initialized?** Follow the chain from the root superclass down to the current subclass, without creating a separate superclass object.
7. **When do each class's field initializers and instance initializers run?** In source-code order after superclass initialization, and **without repeating** due to `this(...)` delegation.
8. **Which constructor body prints/logs/modifies fields first?** Note clearly when entering and when returning from the target constructor.
9. **Is any `final` field unassigned or assigned twice?** Check definite assignment across every constructor that completes normally.
10. **Is any overridable method called inside a superclass constructor?** It may observe subclass fields that have not yet been completely initialized.
11. **Is there an exception in a super constructor?** If so, the rest of the chain does not complete normally; checked exceptions must be validly declared or handled.
12. **Does it depend on the syntax of another Java version?** If the task requires Java 21, always verify against that version's rules.

## 18. Compile Errors and Quick Fixes

| Situation | Why Is It Invalid in Java 21? | Fix |
| --- | --- | --- |
| `println(...); this(...);` | `this(...)` is not the first statement | Place `this(...)` first; print afterward |
| `int x = 1; super(x);` | `super(...)` is not the first statement | Pass the expression `super(1)` or a parameter/static helper |
| `if (flag) this();` | Explicit constructor invocation is not directly in the valid first position | Use a single `this(flag ? a : b)` with a suitable target constructor |
| `this(...); super(...);` | Two constructor invocations in the same constructor; the second call is not allowed | Let the target `this(...)` constructor handle the super chain |
| `A() { this(1); }` and `A(int) { this(); }` | Recursive constructor invocation | Design a target constructor that does not delegate in a cycle |
| `Child() { }` when `Parent` only has `Parent(int)` | Implicit `super()` cannot find a target | Write `super(validInt)` first or change the superclass design |
| `this(instanceField)` | Cannot use the current instance to evaluate explicit constructor invocation arguments in Java 21 | Use a parameter, literal, or static method |
| `this()` when there is no no-argument constructor in the same class | No target constructor exists | Add a valid explicit no-arg constructor or call an existing overload |
| `super()` to an inaccessible private constructor | Access-permission error | Provide a suitably accessible superclass constructor |
| `super(args)` calls a constructor with a checked exception without the subclass declaring it | Does not satisfy checked exception checking | Declare an appropriate `throws` clause or adjust the design |

The error snippets in the table are presented for **identification and diagnosis**, not as standalone code to be compiled verbatim.

## 19. Self-Practice Exercises with Answers

**Question 1.** What is the core difference between `this(...)` and `super(...)`?

*Answer:* `this(...)` calls another constructor of **the same class**; `super(...)` calls a constructor of **the direct superclass**. Both participate in constructing **the same object**, without creating an extra object.

**Question 2.** Can you place `System.out.println("start");` before `super(1);` in a Java 21 constructor?

*Answer:* No. An explicit `super(1)` must be the first statement. You can place `println` after it.

**Question 3.** If `A() { this(1); }`, `A(int n) { this("x"); }`, and `A(String s) { super(); }`, how many `A` objects are created when calling `new A()`?

*Answer:* One object. The chain passes through three constructors on the same instance and then initializes the superclass. The condition that the superclass has an accessible `super()` constructor must still be satisfied.

**Question 4.** Does `new Child()` execute a superclass constructor if `Child()` only writes `this(7)`?

*Answer:* Yes. The delegated `Child(int)` constructor continues the chain to the appropriate superclass constructor (explicit or implicit), as long as the chain is valid.

**Question 5.** If the superclass only has `Parent(String)`, does a subclass written as `Child() { }` compile?

*Answer:* No, because the implicit `super()` call cannot find a no-argument superclass constructor. Write `Child() { super("default"); }` if that is a valid state.

**Question 6.** How many times does the instance initializer of `Child` run when `Child()` calls `this(1)` and then `Child(int)` calls `super()`?

*Answer:* Once for each `Child` object created. `this(...)` does not reinitialize the same class.

**Question 7.** Why is `Child() { this(instanceField); }` invalid in Java 21, even if the field is given an initializer at its declaration?

*Answer:* The argument of an explicit constructor invocation cannot use the current instance in this context; `Child`'s field initializers also cannot yet be relied upon as completed state. Use a parameter, literal, or appropriate static helper.

**Question 8.** In `ConstructionOrderDemo`, why does `Child(int,String) body` print before `Child(int) body`?

*Answer:* `Child(int)` called `this(id, "ready")` and had to wait for the target constructor to complete. Only after the target constructor returns does the remainder of `Child(int)`'s body run.

**Question 9.** Must `super.method()` follow the rule requiring it to be the first statement in a constructor?

*Answer:* No. It is a **method invocation**, not a `super(...)` constructor invocation. However, that call must still appear in a valid context and at a valid point in time.

**Question 10.** Do the two constructors `C() { this(1); }` and `C(int x) { this(); }` form a valid chain?

*Answer:* No. That is a recursive constructor invocation, with no path to appropriate superclass initialization.

**Question 11.** If a superclass constructor throws `IOException`, what must the subclass keep in mind?

*Answer:* The subclass constructor calling it must satisfy the checked exception rules, typically declaring `throws IOException` and letting the caller handle it. You cannot simply place `try` before `super(...)` in Java 21.

**Question 12.** Why can calling an overridable method from a superclass constructor print the default value of a subclass field?

*Answer:* Runtime dispatch can invoke the subclass implementation when the subclass's field initializers have not run yet, so those fields still hold their default values at this stage.

---

**Remember:** In **Java 21**, an explicit constructor invocation **`this(...)` or `super(...)` must be the first statement** in a constructor. `this(...)` delegates within the same class; `super(...)` calls a constructor of the direct superclass. If no explicit invocation is declared, Java normally uses an implicit `super()`; therefore, the superclass must have a matching and accessible constructor. A `this(...)` chain must not recurse in a cycle, does not repeatedly initialize instance fields, and does not create additional objects. When tracing output, follow the constructor chain up to the superclass, then come back through the initializers and constructor bodies in completion order.
