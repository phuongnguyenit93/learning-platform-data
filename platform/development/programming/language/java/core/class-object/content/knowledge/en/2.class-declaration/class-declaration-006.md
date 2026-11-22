# Distinguishing Class Members, Constructors, and Initializer Blocks in Java

## 1. Three Concepts Inside the `class` Body with Different Roles

When reading a `class` declaration in Java, you may encounter fields, methods, nested classes, constructors, and unnamed blocks of statements. All of them are written inside the class's `{ ... }` braces, yet they are **not the same kind of declaration**, do not share the same invocation mechanism, and do not execute at the same time.

- **Class members** are fields, methods, and nested member types (member class/interface) according to Java semantics. They define the state, behavior, and related types associated with a class. Fields and methods can be **instance** or **`static`**.
- A **constructor** defines how to create and initialize an instance when an appropriate object-creation call is made. A constructor has the same name as the class, **has no return type**, and is not called like a regular method. According to the Java Language Specification (JLS), constructors are **not members** of the class and are not inherited.
- An **initializer block** is a block of statements without a name or method signature: `static { ... }` to initialize the class, or `{ ... }` to initialize an instance. According to the JLS, initializer blocks are also **not members** of the class. They are executed by the initialization mechanism at the appropriate time; the program does not call them directly by name.

There is also the **field initializer**, which is the expression right at a field declaration such as `int count = 1;`. It performs initialization work, but it is **not an initializer block**. Distinguishing these four constructs helps you explain accurately where data is assigned values, when statements execute, and which parts may be accessed from external code.

### A Quick Look Through a Sample Class

```java
class Product {
    static int nextId = 1;          // Static field + field initializer
    private final int id;           // Instance field (blank final)
    private String name = "New";    // Instance field + field initializer

    static {                         // Static initializer block
        System.out.println("Product class initialized");
    }

    {                                // Instance initializer block
        id = nextId++;
    }

    Product(String name) {           // Constructor
        this.name = name;
    }

    String getName() {               // Instance method
        return name;
    }

    static int getNextId() {         // Static method
        return nextId;
    }

    static class Label {             // Static member class (nested type)
    }
}
```

This is a **compilable class declaration snippet**, not a standalone runnable program because it has no `main`. `id` is a `final` field assigned exactly once in the instance initializer. The constructor assigns `name`. The first class initialization executes the static initializer; each instance creation executes the instance initializer.

## 2. Core Comparison Table

| Criterion | Class member | Constructor | Initializer block |
| --- | --- | --- | --- |
| Form | Field, method, nested member type | `ClassName(...) { ... }` | `static { ... }` or `{ ... }` |
| Is a *member* per the JLS? | Yes | No | No |
| Has a name to reference? | Has a field/method/type name | Shares the class name, but is not called like a method | No |
| Has parameters? | Methods may have them; fields and types do not in the sense of call parameters | May have them | No |
| Has a return type? | Methods do, including `void`; fields have a data type | **None**, not even `void` | No |
| `static` or instance? | Fields/methods can be either; nested member classes can be `static` | Always tied to instance construction; cannot be declared `static` | Two forms: static and instance |
| When does it execute? | Field initializers during the appropriate initialization; methods when called; nested types do not run automatically merely by being declared | When a corresponding instance-creation call or constructor chain occurs | Static: during class initialization; instance: during the creation of each instance |
| Can it be called directly? | Fields are read/written and methods are called according to access permissions; types are used in type expressions | Via `new` or `this(...)`/`super(...)` chaining according to syntax rules | No |
| Inherited? | Certain members are inherited according to access/inheritance rules | No | No |
| Purpose | Describe API, state, behavior, and type organization | Accept input data and establish a valid instance | Initialize shared logic before constructor bodies or initialize class state |

The term **"class member"** needs to be understood precisely. In casual usage, some materials use "class components" in a very broad sense that includes constructors and initializers as well. However, when classifying according to Java syntax/semantics, **member** is a technical term and is not synonymous with "everything written inside the class body."

## 3. Class Members: Fields, Methods, and Nested Types

### 3.1. Fields Are Data Belonging to an Instance or a Class

A field is a variable declared directly inside the class body. Java divides fields into:

- **Instance field**: each object has its own state. For example, `private int balance;`; when two accounts are created, each account has its own `balance`.
- **Static field**: belongs to the class and is shared among instances. For example, `private static int createdCount;`; typically accessed via the class name `Account.createdCount` if access permissions allow.

```java
class Account {
    private static int nextNumber = 1;
    private final int number;
    private int balance;

    Account(int initialBalance) {
        this.number = nextNumber++;
        this.balance = initialBalance;
    }

    int getNumber() {
        return number;
    }

    int getBalance() {
        return balance;
    }
}
```

This is an **illustrative class snippet**, without a `main`. `nextNumber` is a shared static field, while `number` and `balance` are instance fields. Two consecutively created instances receive different numbers. In concurrent systems, incrementing a static field with `++` does not automatically guarantee thread safety; the example above only illustrates field classification in a single thread.

A field declared without an explicit value assignment receives a **default value** when Java allocates the object or initializes the class: `int` is `0`, `boolean` is `false`, and reference types are `null`. This differs from local variables inside methods/constructors: local variables must be assigned before being read.

### 3.2. Methods Are Behavior That Can Be Called by Name

```java
class Counter {
    private int value;

    void increment() {  // Instance method
        value++;
    }

    int getValue() {    // Instance method
        return value;
    }

    static int doubleOf(int n) {  // Static method
        return n * 2;
    }
}
```

- `counter.increment()` requires a reference to a valid `Counter` object because it operates on that object's `value`.
- `Counter.doubleOf(5)` calls a `static` method and does not require creating an instance.
- A method has a return type (for example, `int`, `void`), a name, and a parameter list; it can be **overloaded** with different parameter lists.
- A static method has no `this`. It cannot directly access instance fields or call instance methods without a reference to an appropriate object.

A method executes **when called**; it does not run automatically simply because the class is initialized or an object is created. Exceptions to this involve a specific method being called from a constructor or initializer according to the programmer's code; declaring a method by itself does not cause it to run.

### 3.3. Member Types Organize Related Types

```java
class Container {
    static class Entry {
        final String key;

        Entry(String key) {
            this.key = key;
        }
    }

    interface Validator {
        boolean isValid(String key);
    }
}
```

`Entry` is a **static member class**, and `Validator` is a **member interface**. They are types declared inside `Container`; you can use the names `Container.Entry` and `Container.Validator` from any location with access permission. Writing a nested type declaration does not cause `Entry`'s constructor to run automatically. Only `new Container.Entry("code")` creates an instance of `Entry`.

A **non-static member class** (*inner class*), by contrast, requires an association with an enclosing class instance, for example `outer.new Inner()`. Both forms are member types, but their instance-ownership rules differ.

### 3.4. "Member" Does Not Mean "Static"

The term **class member** does not mean that all members are declared `static`. In technical communication, two easily confused phrasings commonly appear:

- *Member of a class*: a field/method/member type declared in a class, which can be instance-level or `static`.
- *Class member* in the sense of "static member": some people use this phrase to refer to a `static field`/`static method`, as opposed to an *instance member*.

When reading Java documentation, look at the context and use the specific terms **`static field`, `instance field`, `static method`, `instance method`** so as not to confuse "located in the class" with "shared by the class."

## 4. Constructor: Where an Instance Is Set Up

A constructor is not an ordinary method, even though its body contains statements.

```java
class Ticket {
    private final String code;
    private int usedCount;

    Ticket(String code) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code is required");
        }
        this.code = code;
    }

    Ticket() {
        this("DEFAULT"); // Calls another constructor of the same class.
    }

    void use() {
        usedCount++;
    }

    String describe() {
        return code + ":" + usedCount;
    }
}
```

This snippet compiles as a class, though it **has no `main` entry point**. There are two constructors: `Ticket()` and `Ticket(String)`. `this("DEFAULT")` delegates initialization responsibility to the other constructor on the **same instance**; it does not create an additional object.

Essential rules:

1. **The constructor name must match the class name exactly**, including letter case; no return type is specified. `void Ticket()` is a **method**, not a constructor.
2. You can **overload constructors** by parameter count, types, or order. Constructors cannot be distinguished solely by access modifiers.
3. A constructor can have `public`, `protected`, `private`, or package-private access, but cannot be `static`, `final`, or `abstract`.
4. Constructors are **not inherited**: a subclass must declare its own constructor(s), or receive a default constructor if the conditions are met.
5. If a class declares no constructors at all, the compiler provides a default no-argument constructor with matching access. As soon as the class explicitly declares **any constructor**, the compiler does not automatically add a no-argument constructor.
6. In **Java 17**, an explicit `this(...)` or `super(...)` call must be the first statement in the constructor body; you cannot use both to call directly within the same constructor. If no explicit call is written, the compiler automatically inserts an appropriate no-argument superclass constructor call when the rules allow.
7. A `final` instance field not assigned at declaration (*blank final*) must be assigned during initialization such that every constructor that completes normally satisfies **definite assignment**, and it must not be reassigned against the rules.

In the `Ticket` example, `code` is assigned in the two-parameter constructor; the no-argument constructor delegates through `this(...)`, thereby still ensuring `code` is initialized.

### How a Constructor Differs from a Method Call

```java
class Sample {
    Sample() {                       // Constructor
        System.out.println("construct");
    }

    void Sample() {                  // Method named Sample
        System.out.println("method");
    }
}
```

If you run `Sample s = new Sample();`, the constructor prints `construct`. Only when you subsequently call `s.Sample();` does the method print `method`. Adding `void` completely changes the meaning of the declaration. Therefore, when looking at a construct resembling the class name, check **whether it has a return type or not**.

### Constructors and Object Invariants

A constructor is often the enforcement point for conditions such as "non-negative price," "non-empty name," or "valid coordinate pair." Placing these checks inside the constructor prevents creating invalid instances. If multiple constructors establish the same invariants, use constructor chaining to avoid duplicating validation checks.

A constructor can call instance methods, but caution is required: calling an **overridable method** during object construction can dispatch down to a subclass before the subclass state has finished initializing. This is a hard-to-spot source of bugs; you should prefer handling the class's fields directly in the constructor or calling a non-overridable helper when appropriate.

## 5. Static Initializer Blocks: `static { ... }`

A static initializer resides inside the class body and has the syntax:

```java
class Configuration {
    private static final int PORT;

    static {
        PORT = 8080;
    }

    static int port() {
        return PORT;
    }
}
```

This snippet is valid; `PORT` is a static blank final field, assigned once inside the static initializer block. Java executes **static field initializers** and **static initializer blocks** in textual order when **the class is initialized**.

A class is typically initialized before its first *active use*, such as creating an instance with `new`, calling a static method, or reading/writing a static field that is not a compile-time constant governed by special rules. The fact that the JVM has *loaded* a class's metadata **does not necessarily** mean its static initializer has run. The expression `SomeType.class` by itself generally does not trigger class initialization, and reading a static final primitive/String *compile-time constant* may be inlined without triggering initialization of the declaring class.

Key rules:

- A static initializer **has no name, parameters, or return type**; it cannot be called directly using syntax such as `Configuration.static()` or `new Configuration.static()`.
- A static initializer **has no `this`** and cannot directly reference instance fields or methods as if an object already existed.
- A class can have multiple static initializers; they run interleaved with static field initializers in declaration order.
- During initialization, Java guarantees class-initialization synchronization; this **does not make all subsequent operations on static fields thread-safe**.
- An exception thrown during static initialization can cause class initialization to fail, affecting subsequent uses. You should avoid placing I/O or error-prone operations inside a static initializer unless there is a clear design reason.

### Common Mistake with Static Initializers

```java
class WrongStatic {
    private int value = 7;

    static {
        // System.out.println(value);
        // The line above, if uncommented, will cause a compilation error:
        // cannot reference the instance field value from a static context.
    }
}
```

This is a valid class declaration **because the invalid statement has been commented out**. Reading `value` requires a specific `WrongStatic` object; a `static` context does not provide `this`.

## 6. Instance Initializer Blocks: `{ ... }`

An instance initializer is a block without `static` placed directly inside the class body:

```java
class Session {
    private int retries;

    {
        retries = 3;
    }

    Session() {
    }

    int retries() {
        return retries;
    }
}
```

The `{ retries = 3; }` block executes during **the initialization of each instance**, before the corresponding class's constructor body and after superclass initialization work completes in the normal order. It can reference `this` and instance fields according to Java's access and forward-reference rules.

Characteristics:

- Has no name, parameters, `throws` clause, or return type.
- Cannot be called directly; the JVM/bytecode executes the work compiled from the initializer during the instance construction process.
- A class can have multiple instance initializers interleaved with **instance field initializers**; they execute in source declaration order.
- If a class has multiple constructors, the class's instance initializers execute once per corresponding object initialization, and **do not run again when a constructor delegates via `this(...)`**.
- An instance initializer can throw exceptions, causing object creation to fail. Checked exceptions are subject to strict compilation restrictions; for failure-prone work, constructors usually express exception handling or declaration more clearly.

### How Do a Field Initializer and an Instance Initializer Differ?

```java
class State {
    private int first = 10; // Field initializer
    private int second;     // Not explicitly assigned: defaults to 0

    {                        // Instance initializer block
        second = first + 5;
    }

    State() {                // Constructor body
        first++;
    }

    String report() {
        return first + "," + second;
    }
}
```

With `new State().report()`, the result is `11,15`. Specifically:

1. Instance fields initially have the default value `0`.
2. The declaration `first = 10` assigns `10`.
3. The instance initializer reads `first` and assigns `second = 15`.
4. The constructor increments `first` to `11`.
5. `report()` reads the state after construction.

**Conclusion:** both assignment expressions in field declarations and instance blocks participate in initialization, but their syntax and expressiveness differ. A field initializer is suited for a simple value or expression, an instance initializer is used for a shared group of statements, and a constructor is suited for parameterized initialization and invariant checks.

## 7. Complete Runnable Example: Initialization Order Across Inheritance and `this(...)`

Create the file **`InitializationFlowDemo.java`** with the following code (compatible with **Java 17+**):

```java
class Parent {
    static {
        System.out.println("Parent.static");
    }

    {
        System.out.println("Parent.instance");
    }

    Parent() {
        System.out.println("Parent.constructor");
    }
}

class Gadget extends Parent {
    private static int limit = initLimit();

    static {
        System.out.println("Gadget.static block");
    }

    private final String name;
    private int stock = initStock();

    {
        System.out.println("Gadget.instance block");
    }

    Gadget() {
        this("Default");
        System.out.println("Gadget.noarg body");
    }

    Gadget(String name) {
        this.name = name;
        System.out.println("Gadget.constructor " + name);
    }

    private static int initLimit() {
        System.out.println("Gadget.static field");
        return 10;
    }

    private int initStock() {
        System.out.println("Gadget.instance field");
        return 1;
    }

    String describe() {
        return name + "/" + stock + "/" + limit;
    }
}

public class InitializationFlowDemo {
    public static void main(String[] args) {
        System.out.println("Start");
        Gadget first = new Gadget("A");
        Gadget second = new Gadget();

        System.out.println(first.describe());
        System.out.println(second.describe());
    }
}
```

Run in the directory containing the file:

```bash
javac InitializationFlowDemo.java
java InitializationFlowDemo
```

**Standard output in exact order:**

```text
Start
Parent.static
Gadget.static field
Gadget.static block
Parent.instance
Parent.constructor
Gadget.instance field
Gadget.instance block
Gadget.constructor A
Parent.instance
Parent.constructor
Gadget.instance field
Gadget.instance block
Gadget.constructor Default
Gadget.noarg body
A/1/10
Default/1/10
```

### Analyzing the First Object Creation

The statement `new Gadget("A")` is the first active use of `Gadget` in the program. Because `Gadget` inherits from `Parent`, **the superclass is initialized before the subclass**:

```text
Initialize Parent (once):
    Parent.static
Initialize Gadget (once):
    Gadget.static field  -> limit = 10
    Gadget.static block

Create Gadget("A"):
    Default instance values are set
    Initialize the Parent part:
        Parent.instance
        Parent.constructor
    Initialize the Gadget part:
        Gadget.instance field  -> stock = 1
        Gadget.instance block
        Gadget.constructor A  -> name = "A"
```

In this demo, `initLimit()` and `initStock()` are **methods** called by **field initializers**. The log lines "Gadget.static field" and "Gadget.instance field" appear because the initializers call those methods, not because every field initializer always prints something on its own.

### Analyzing the Second Object Creation

`new Gadget()` enters the no-argument constructor. The line `this("Default")` delegates to the `Gadget(String)` constructor; this execution path constructs only **one** instance:

```text
Create Gadget():
    (Static initialization is not repeated)
    Parent.instance
    Parent.constructor
    Gadget.instance field
    Gadget.instance block
    Gadget.constructor Default
    Gadget.noarg body
```

Only after `Gadget(String)` finishes does the program execute the remaining `println` statement in the `Gadget()` body. This demonstrates that constructor chaining **does not create a second object** and does not run the instance block twice either.

The two objects each have their own `stock == 1`, while sharing the same static value `limit == 10`. Therefore, the last two lines are `A/1/10` and `Default/1/10`.

> In Java 17, placing a statement before `this(...)` or `super(...)` in a constructor is a compilation error. Follow the rules of the version you are learning; language updates regarding "flexible constructor bodies" in newer Java versions do not apply when compiling with `--release 17`.

## 8. Overall Diagram of the Initialization Lifecycle

```text
Compiled class declaration
          |
          v
JVM loads/links the class when needed (does not necessarily run static initializers)
          |
          v
Class initialization when required (once per initialization of the corresponding Class)
          |
          +--> Initialize appropriate superclasses first
          |
          +--> static field initializers + static { } in source order
          |
          v
The new statement creates an instance
          |
          +--> Allocate memory and set default values for instance fields
          |
          +--> Call superclass constructor (and superclass constructor chain)
          |
          +--> Current class's instance field initializers + { }
          |    in source order
          |
          +--> Current constructor body
          |
          v
Instance is fully constructed; methods can now be called
```

The diagram aims to clarify the typical order and does not cover every detailed case of class loaders, initialization failures, initialization via reflection, or multi-level constructor chaining. With `this(...)`, within-class initialization is performed through the target constructor and then returns to the delegating constructor body; field initializers and instance initializers **do not repeat**.

One easily confused point: **a field's default value** is set during allocation/initialization, whereas **an initializer with an expression** such as `int x = compute();` executes according to the ordering rules described above. If an initializer reads another field at an invalid time, Java may forbid a direct reference by simple name before that field is declared; indirect access paths can still observe the default value. Avoid having field initializers depend cyclically on one another.

### Textual Order Can Change the Result

The following is a compilable class:

```java
class Ordered {
    static int number = 1;

    static {
        number = number * 2;
    }

    static int snapshot = number + 5;
}
```

When `Ordered` is initialized, `number` becomes `1` and then `2`; `snapshot` becomes `7`. If you move the `snapshot` declaration **before** the `static` block, snapshot will be `6` because `number == 1` at that point. The result reflects the execution order of **static field initializers and static blocks** within the same class.

The same rule exists between instance field initializers and instance blocks. Because order dependencies are often hard to read, prefer simple initialization declarations with minimal side effects and clear constructors.

## 9. How Should Data Be Initialized?

There is no single choice for every situation. A practical way to decide:

| Need | Appropriate location | Example |
| --- | --- | --- |
| Fixed initial value, simple per-instance expression | Instance field initializer | `private int retryCount = 3;` |
| Fixed class-level initial value | Static field initializer | `private static final int LIMIT = 100;` |
| A shared group of static initialization statements with order dependencies | `static { ... }` when truly needed | Initializing a static data structure in several steps |
| Mandatory shared work executed for each instance before the constructor body | Instance initializer `{ ... }` when there is a specific reason | A consistent block shared across multiple constructors |
| Depends on object-creation parameters, requires validation, has multiple variants | Constructor | `Account(String owner, long openingBalance)` |
| Operation to execute on demand after object creation | Instance method | `account.deposit(amount)` |
| Functionality that does not use an instance, called on the class | Static method | `Math.max(a, b)` or a factory method |

In everyday application code, prefer **field initializers** for simple defaults and **constructors** for checking and enforcing invariants. Instance initializer blocks are less common because they are easy to overlook when reading code and their logic can usually be moved into constructors or constructor delegation. Do not use static initializers to run network connections, DB accesses, or hard-to-control environment conditions at class-initialization time.

### Distinguishing a Constructor from a Static Factory Method

```java
class Money {
    private final long cents;

    private Money(long cents) {
        this.cents = cents;
    }

    static Money ofCents(long cents) {
        if (cents < 0) {
            throw new IllegalArgumentException("cents must not be negative");
        }
        return new Money(cents);
    }

    long cents() {
        return cents;
    }
}
```

`Money(long cents)` is a **private constructor**; `ofCents(long cents)` is a **static method** returning a `Money` object. Callers of the class can invoke `Money.ofCents(150)` (if access permissions allow), but cannot call the private constructor from outside its permitted scope. This is an example of distinguishing by syntax: the method has the return type `Money`, whereas the constructor has no return type.

## 10. Common Mistakes

| Misconception | Consequence and correction |
| --- | --- |
| "Everything inside the `class` body is an inherited member" | Constructors and initializers are not members per the JLS and are not inherited; methods, fields, and member types have their own inheritance rules. |
| "A constructor is a method with the same name as the class" | A constructor has no return type and is not a method; `void Foo()` is a separate method. |
| "`static { ... }` runs whenever each object is created" | It is tied to **class initialization**, typically running once for the initialized Class, not once per object. |
| "`{ ... }` is always just an ordinary scope" | A bare block placed directly inside the class body is an **instance initializer**; the same brace syntax inside a method is a block statement. |
| "Instance initializers run after the constructor" | For the current class, instance initializers execute before the corresponding constructor body, after the superclass has been initialized. |
| "`this(...)` makes all initializers run an extra time" | Constructor delegation operates on a single instance; initializers do not repeat simply because one constructor calls another. |
| "A static field means a constant" | `static` only means the field belongs to the class; to prevent reassignment it is usually combined with `final`, though `final` also does not make the referenced object immutable. |
| "A static method can access `this`" | A static context has no `this`; to use an instance field, you need an explicit object reference. |
| "Omitting all constructors makes it impossible to create objects" | If a class has no explicitly declared constructors, the compiler usually provides a default no-argument constructor, depending on superclass conditions. |
| "Even with a parameterized constructor, an empty constructor is still generated automatically" | Once you explicitly declare a constructor, the compiler does not add a no-argument constructor. |
| "Reordering any initializers is harmless" | Static/instance initializers and field initializers within the same group execute in textual order; swapping them can alter state. |
| "The subclass constructor finishes running before calling the superclass" | Superclass initialization occurs before the subclass's instance logic in the normal constructor chain. |
| "A static block can throw an error without affecting subsequent uses" | An error during class initialization can leave the class unusable in normal operation within the corresponding class loader. |

The snippets below illustrate **intentional errors, not meant to be compiled**:

```java
class Broken {
    int value;

    static {
        // value = 1;       // Error: accessing an instance field in a static context.
        // this.value = 1;  // Error: static context has no this.
    }

    // Broken(int n) {
    //     System.out.println(n);
    //     this();          // Error in Java 17: this(...) must be first in the constructor.
    // }

    // static Broken() { } // Error: a constructor cannot be declared static.
}
```

The comments in the example merely mark places that would cause errors; the `Broken` block as displayed compiles cleanly. Do not confuse compilation errors with runtime errors: accessing an instance field improperly from a static context is an error caught by the compiler, whereas initialization logic throwing an exception can be a runtime error.

## 11. Self-Check Questions and Answers

**Question 1.** Which of the following elements are members according to the JLS: `private int total;`, `Order() { }`, `void pay() { }`, `static { ... }`, `class Details { }` nested inside `Order`?

**Answer:** Field `total`, method `pay`, and member class `Details` are members; constructor `Order()` and the static initializer are not members.

**Question 2.** If a class has two constructors and each constructor is used to create a different object with `new`, how many times in total does an instance initializer run?

**Answer:** It runs **twice**, once per object. If the first constructor delegates via `this(...)` to the second constructor during **a single object creation**, the initializer runs only once for that object.

**Question 3.** Why can a `static` method not call an instance method without an object?

**Answer:** A static method belongs to the class context and carries no `this`. An instance method requires a specific instance to determine its instance fields and behavior.

**Question 4.** In the `InitializationFlowDemo` example, why does `Parent.static` appear before `Gadget.static field` and `Gadget.static block`?

**Answer:** When `Gadget` begins initialization, its superclass `Parent` is initialized first. Afterward, `Gadget`'s static field initializers and static blocks execute in source order.

**Question 5.** Why does the second example print `Gadget.constructor Default` before `Gadget.noarg body`?

**Answer:** `Gadget()` calls `this("Default")`, so the `Gadget(String)` constructor executes first; only once it returns does the rest of the `Gadget()` body run.

**Question 6.** Where is the appropriate place to validate `openingBalance >= 0` on `Account` if the condition must hold as soon as the object is created?

**Answer:** The constructor that accepts the balance parameter. If there are multiple constructors, they can be routed to a single constructor performing the shared validation. Later on, instance methods that modify the balance must also preserve the related condition.

**Question 7.** Which runs first: `int level = 3;` or `{ level++; }` if both are part of instance initialization in the same class and are declared in that order?

**Answer:** The field initializer assigns `3` first, and the instance initializer increments it to `4`. If the constructor subsequently modifies `level`, the final state depends on the constructor body.

## 12. Checklist When Reading Real-World Java Code

To avoid drawing wrong conclusions about object state, inspect in the following order:

1. **Classify the declaration:** is it a member field/method/nested type, constructor, static initializer, or instance initializer?
2. **Identify the scope:** is the field/method `static` or instance, what is its access level, and is it `final`?
3. **Trace the object creation path:** which constructor is selected based on the parameter list, is there `this(...)`/`super(...)`, and does the superclass have an appropriate constructor?
4. **Map the initialization order:** when are superclass/subclass static initializers, superclass/subclass instance initializers, and constructor bodies executed?
5. **Check invariants and side effects:** can the constructor/initializer throw exceptions or call an overridable method; do multiple objects share mutable static state?
6. **Cross-check output:** a line is only printed when a statement actually executes; do not infer output merely from member declarations.

**Key takeaway:** **Members** declare state, behavior, or nested types; **constructors** set up an instance during object construction; **initializer blocks** are statements executed automatically during class or instance initialization. Identifying the right kind of construct and the right execution order helps explain both simple code and interactions among `static`, inheritance, field initializers, and constructor chaining.
