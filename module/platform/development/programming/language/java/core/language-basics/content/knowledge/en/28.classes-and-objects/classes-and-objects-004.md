# Constructors Set Initial Values in Java

## 1. What Is a Constructor?

A **constructor** is the mechanism for initializing an object when using a `new` expression. A constructor has the **same name as the class**, **declares no return type** (not even `void`), and is used to establish a valid initial state for each instance.

```java
class Student {
    String name;
    int age;

    Student(String name, int age) {
        this.name = name;
        this.age = age;
    }
}

// Placed inside a method:
// Student s = new Student("Lan", 18);
// s.name == "Lan" and s.age == 18
```

The expression `new Student("Lan", 18)` creates a `Student` object and runs the initialization process, including the constructor selected by the argument list. `this.name` and `this.age` are the **fields of the current object**; `name` and `age` without `this` inside the constructor are **parameters**. Writing `name = name;` only assigns the parameter to itself, without storing the value into the field.

Constructors are primarily used to establish an **object's invariant**: conditions that must hold immediately after creation, such as a non-empty name or a non-negative age. Depending on requirements, not every field has to be set via a constructor; a field may have a default value or an initializer at declaration.

## 2. Default Values and Field Initialization

As soon as object memory is allocated, **instance fields** receive their type's default values, before any field initializers and constructor body perform the relevant assignments.

| Field type | Default value before explicit assignment |
| --- | --- |
| `byte`, `short`, `int`, `long` | Type-appropriate `0` |
| `float`, `double` | Type-appropriate `0.0` |
| `char` | `'\u0000'` |
| `boolean` | `false` |
| Any reference type, including `String`, arrays, and objects | `null` |

```java
class Settings {
    int retries;               // Initially 0
    boolean enabled;           // Initially false
    String mode = "standard";   // Field initializer: sets an explicit value

    Settings(int retries) {
        this.retries = retries;
        this.enabled = true;
    }
}
```

After `new Settings(3)` finishes, the object has `retries == 3`, `enabled == true`, `mode.equals("standard")`.

**Difference from local variables:** Java does not allow reading a local variable unless it is **definitely assigned** before the point of use; local variables do not automatically have a readable default value like object fields.

```java
void example() {
    int count;
    // System.out.println(count); // Compile ERROR: count is not assigned
    count = 2;
    System.out.println(count); // Valid
}
```

The `example()` snippet is an illustrative method that needs to be placed inside a class.

## 3. Syntax and How Constructors Differ from Regular Methods

```java
class Rectangle {
    private final int width;
    private final int height;

    public Rectangle(int width, int height) {
        this.width = width;
        this.height = height;
    }

    public int area() {
        return width * height;
    }
}
```

- `Rectangle(...)` is a **constructor**, with no return type.
- `area()` is a **method** with return type `int`; methods can be called on an object multiple times.
- Constructors run during instance creation. Calling a constructor again like a normal method, such as `object.Rectangle(2, 3)`, is **invalid**.
- Constructors can have access levels `public`, `protected`, package-private (no modifier), or `private`. Access level determines whether external code is allowed to use `new` with that constructor.
- Constructors are **not inherited** and cannot be overridden. Constructors do not declare `static`, `abstract`, or `final`.
- `return;` can be used to exit a constructor early in some cases, but a constructor **cannot return a value** with `return expression;`. In good design, ensure input validation and complete initialization before normal completion.

The constructor name must match the class name, case-sensitively. If you write `void Rectangle(...)`, that is a **method named `Rectangle`**, not a constructor, and the compiler does not treat it as a declared constructor.

## 4. Default, No-Argument, and Parameterized Constructors

Distinguish the **compiler-generated default constructor** from a **programmer-written no-argument constructor**:

```java
class Empty {
    // No constructor declared.
    // The compiler provides a default no-argument constructor.
}

class Custom {
    Custom() {
        System.out.println("Custom()");
    }
}
```

When a class **declares no constructors**, the compiler provides a default no-argument constructor. This constructor calls the superclass constructor according to language rules and does not infer special input values. The access level of the default constructor depends on the class's access level per Java rules; do not assume the auto-generated constructor is always `public`.

If **any constructor** is already declared, the compiler **no longer automatically adds a default no-argument constructor**:

```java
class User {
    String name;

    User(String name) {
        this.name = name;
    }
}

// new User("Mai"); // Valid
// new User();      // Compile ERROR: no User() constructor
```

If you want both ways of creating the object, you must declare the no-argument overload yourself. If no constructor is declared in a subclass, the compiler generates a default constructor that tries to call `super()`; if the superclass lacks an accessible no-argument constructor, compilation fails. In that case, the subclass must declare its own constructor and call the appropriate `super(arguments)`.

## 5. Constructor Overloading and `this(...)`

**Overloading** allows multiple constructors with different parameter lists; use it to provide flexible ways to create objects while maintaining common initialization rules.

```java
class Ticket {
    private final String title;
    private final int quantity;

    Ticket(String title) {
        this(title, 1); // Delegates to another constructor in the same class
    }

    Ticket(String title, int quantity) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title is required");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        this.title = title;
        this.quantity = quantity;
    }
}
```

In **Java 17**, a call to another constructor `this(...)` or to a superclass constructor `super(...)`, if present, must be the **first statement** of the constructor body. Therefore:

- `this(title, 1);` delegates to the two-argument constructor in the same class.
- The target constructor performs validation and assigns state, avoiding duplicating logic in multiple places.
- You cannot call both `this(...)` and `super(...)` in the same constructor body: every initialization path must eventually initialize the superclass exactly once.
- Do not create mutual `this()` cycles; the compiler rejects recursive constructor calls.
- `this(...)` calls a constructor; `this.field` accesses an instance field: the two forms of `this` serve different purposes.
- If both `this(...)` and `super(...)` are omitted, the compiler implicitly calls `super()` when valid.

Version boundary note: some newer Java versions change details to allow statements before an explicit constructor invocation; examples in this lesson follow **Java 17** rules and are compatible with `javac` 17.

## 6. The Superclass Is Initialized Before the Subclass Constructor Body

Java executes the object initialization sequence according to defined rules. For ordinary classes in these examples:

1. Fields are set to default values when the object is allocated.
2. Parent constructors are invoked up the inheritance chain to `Object`.
3. As the classes in the chain complete, each class's **field initializers** and **instance initializer blocks** run in their order of appearance in that class before its corresponding constructor body (with a constructor delegating via `this(...)`, the class's instance initializers run only once).
4. The superclass constructor body finishes before the subclass constructor body.

Standalone illustration of this idea when placed inside classes:

```java
class Parent {
    Parent() {
        System.out.println("Parent constructor");
    }
}

class Child extends Parent {
    private int id = 7;

    Child() {
        super(); // Implicit if omitted, when Parent() is accessible
        System.out.println("Child constructor: " + id);
    }
}
```

Creating `new Child()` prints `Parent constructor` before `Child constructor: 7`. Avoid calling overridable instance methods from a superclass constructor: when the override runs in the subclass, the subclass's fields may not have finished initializing yet.

## 7. Standalone Java 17+ Example

Create the file **`ConstructorDemo.java`**:

```java
public class ConstructorDemo {
    static class Order {
        private final String item;
        private final int quantity;

        Order(String item) {
            this(item, 1); // Constructor overload
        }

        Order(String item, int quantity) {
            if (item == null || item.isBlank()) {
                throw new IllegalArgumentException("Invalid item");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("Invalid quantity");
            }
            this.item = item;
            this.quantity = quantity;
        }

        void print() {
            System.out.println(item + ": " + quantity);
        }
    }

    static class Defaults {
        int count;
        String description;

        Defaults() {
            System.out.println("Before: " + count + ", " + description);
            count = 5;
            description = "ready";
        }

        void print() {
            System.out.println("After: " + count + ", " + description);
        }
    }

    static class Parent {
        Parent() {
            System.out.println("Parent()");
        }
    }

    static class Child extends Parent {
        private final int id = 42;

        Child() {
            super();
            System.out.println("Child(): " + id);
        }
    }

    public static void main(String[] args) {
        Order first = new Order("Pen");
        Order second = new Order("Book", 3);
        first.print();
        second.print();

        try {
            new Order("Paper", 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }

        Defaults defaults = new Defaults();
        defaults.print();

        new Child();
    }
}
```

Open a terminal in the directory containing the file, using **JDK 17 or later** on Windows PowerShell/CMD or Linux/macOS:

```bash
javac -encoding UTF-8 ConstructorDemo.java
java ConstructorDemo
```

**Exact stdout** result (a successful compile command prints nothing):

```text
Pen: 1
Book: 3
Rejected: Invalid quantity
Before: 0, null
After: 5, ready
Parent()
Child(): 42
```

Result explanation:

- `new Order("Pen")` invokes the one-parameter constructor and delegates via `this(item, 1)`; `quantity` is initialized to `1`.
- `new Order("Book", 3)` uses the two-parameter overload and initializes both `final` fields.
- The constructor rejects `quantity == 0` with `IllegalArgumentException`; no `Order` object is returned to the failed `new` call.
- In `Defaults()`, the two fields not explicitly assigned have default values `0` and `null`; after assignments in the constructor, they become `5` and `"ready"`.
- With `new Child()`, the parent constructor prints first, then the child constructor reads the `id` field already initialized to `42`.

## 8. `final` Initialization, Validation, and Mutable References

### `final` Fields Initialized Once

A **`final` instance field not initialized at declaration** (*blank final field*) must be assigned strictly according to *definite assignment* rules before the constructor completes normally:

```java
class Point {
    final int x;
    final int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }
}
```

If any constructor branch completes normally without assigning `x` or `y`, the code will not compile. If a `final` field was already assigned at declaration, it cannot be reassigned in the constructor.

The `final` keyword on a **reference** prevents reassigning the reference after initialization, but does not automatically make the referenced object's state immutable:

```java
class Holder {
    private final int[] values;

    Holder(int[] input) {
        this.values = input.clone();
    }
}
```

`input.clone()` avoids sharing the original `int[]` array when creating the object. If a getter returns `values` directly, external code can still modify its elements; when true immutability is needed, you must control both how state is exposed and how it is updated.

### Validating Data at Creation Time

A constructor is the right place to reject invalid arguments, such as `name == null`, blank strings, or negative quantities. Choose domain constraints deliberately; `quantity <= 0` makes sense for an order requiring at least one unit, but does not fit every problem (for example, a valid counter may start at 0).

Do not expose `this` while the constructor has not yet finished (for example, registering the object into a public structure or starting a thread that uses `this` too early): other code could observe partially initialized state.

## 9. Common Errors and How to Check

| Error | Consequence / Fix |
| --- | --- |
| Writing `name = name;` when parameter matches field name | Parameter assigns to itself; use `this.name = name;` |
| Adding `void` before the constructor name | Turns it into a regular method, no longer a constructor |
| Calling `new User()` after declaring only `User(String name)` | No auto-generated no-arg constructor; write a `User()` overload if needed |
| Using `this(...)` after another statement in Java 17 | Compile error: explicit constructor invocation must come first |
| A constructor assigns only some `final` fields and returns | *Definite assignment* error; every normal completion path must assign all of them |
| Assuming fields and local variables both have readable default values | Fields have default values; locals must be definitely assigned before reading |
| Calling an overridable method from a parent constructor | May execute subclass logic before subclass state finishes initializing |
| Storing a passed-in mutable array directly and treating the object as immutable | Data can be modified from outside via the same reference; consider defensive copying |

**Takeaway:** constructors define how to create an instance in a valid initial state. Use `this.field` to assign the right field, use `this(...)` to share logic among constructors, use `super(...)` when superclass initialization is needed, and validate arguments before exposing the object.