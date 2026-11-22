# Constructor Chaining and Instance Initialization Block Execution Count in Java

When creating a Java object with `new`, **multiple constructors** can participate in a single object creation: a subclass constructor calls `super(...)`, or a constructor in the same class calls `this(...)`. At the same time, a class can declare **instance field initializers** and **instance initialization blocks** — code segments executed during the initialization of each object.

The key question is: **If three constructors are chained together using `this(...)`, does the instance initialization block run three times?**

**No.** For a single successful object creation via a normal constructor call:

- Each class along the inheritance chain executes **that class's own instance field initializers and instance initialization blocks in one pass**, in the order they appear in the class declaration.
- Constructors chained with `this(...)` can cause **multiple constructor bodies** of the same class to run, but they do **not** repeat that class's instance initializers.
- Initialization of the **parent** classes completes before running the instance initializers and appropriate constructor body of the **subclass**.
- **Static initialization** is a separate mechanism: it initializes the class when required by the JVM, typically once per `Class` object in the corresponding class loader, and does **not** run again on every `new`.

Here is the simplified diagram:

```text
new Child(...)
    |
    v
Child constructor (may call this(...) to another Child constructor)
    |
    v
End of the this(...) chain calls super(...)
    |
    v
Superclass initialization: parent constructor chain
    |
    v
Instance field initializers + instance blocks of Child: ONE PASS
    |
    v
Body of the target Child constructor (which called super)
    |
    v
Bodies of the Child constructors that called this(...), in unwinding order
    |
    v
Object is returned to the caller
```

This diagram applies to the normal initialization case of a class. Below, we will analyze in depth: why chained constructor calls do not create additional objects, how to accurately count how many times initialization blocks run, the ordering with superclasses, and exceptions caused by runtime errors.

## 1. Three Commonly Confused Mechanisms

### 1.1. Constructor

A constructor has the **same name as the class**, has no return type, and is invoked during instance creation or from another constructor via `this(...)` / `super(...)`.

```java
class User {
    User() {
        System.out.println("Constructor User()");
    }

    User(String name) {
        System.out.println("Constructor User(String)");
    }
}
```

Constructors have **their own bodies**. If one constructor calls another constructor, multiple constructor bodies can be executed during the same object creation.

### 1.2. Instance field initializer

An expression in an instance field declaration:

```java
class User {
    int level = 10;
    String name = computeName();

    String computeName() {
        return "guest";
    }
}
```

The two initializers `10` and `computeName()` are part of the **instance initialization process**, not statements that run once when the class is loaded.

### 1.3. Instance initialization block

A `{ ... }` block **without `static`** declared directly in the class body:

```java
class User {
    int level;

    {
        level = 10;
        System.out.println("Instance block");
    }
}
```

This block is executed during the initialization of **each object** according to Java's rules. It is not a separate constructor, has no name or parameter list, and is **not** invoked using `new UserBlock()` or `this(...)`.

### 1.4. Static initialization block

The block:

```java
static {
    System.out.println("Static block");
}
```

is a **static initializer**, belonging to the **class initialization process**, not an instance initializer. It must be separated out when counting execution counts.

| Component | Associated with | When does it run in the normal case? |
| --- | --- | --- |
| Instance field initializer | Each instance | When initializing the instance part of that class |
| Instance block `{ ... }` | Each instance | In the same phase as instance field initializers, in textual order |
| Constructor body | Constructor invoked in the chain | When control returns to the corresponding constructor body |
| Static field initializer | Class | During class initialization when needed |
| Static block `static { ... }` | Class | During class initialization when needed |

## 2. Shortest Example: Instance Block Runs Before Constructor Body

Save as **`BasicInitDemo.java`**:

```java
class Box {
    int number = printNumber();

    {
        System.out.println("Instance block");
    }

    Box() {
        System.out.println("Constructor body");
    }

    private int printNumber() {
        System.out.println("Field initializer");
        return 7;
    }
}

public class BasicInitDemo {
    public static void main(String[] args) {
        Box box = new Box();
        System.out.println("number = " + box.number);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 BasicInitDemo.java
java BasicInitDemo
```

**Exact stdout:**

```text
Field initializer
Instance block
Constructor body
number = 7
```

Sequence:

1. The JVM creates the `Box` object and sets the appropriate default values for its fields.
2. The superclass constructor (`Object` in this case) is processed along the constructor call chain.
3. The instance field initializer `number = printNumber()` runs; the method prints one line and returns `7`.
4. The subsequent instance block prints `Instance block`.
5. The `Box()` constructor body prints `Constructor body`.
6. The caller reads the value of `number` as `7`.

In this `Box` class, **the field initializer and block run before the body of the `Box()` constructor**. They do **not** run after the constructor has finished.

## 3. `this(...)` Is Same-Class Constructor Chaining

A constructor can call another constructor of the **same class** through an **explicit constructor invocation** `this(arguments)`:

```java
class Product {
    Product() {
        this("unknown");
        System.out.println("Product()");
    }

    Product(String name) {
        System.out.println("Product(String): " + name);
    }
}
```

The call:

```java
new Product();
```

does not create two objects. The `Product()` constructor delegates to `Product(String)` **to initialize the same object**. After the `Product(String)` constructor completes, control returns to `Product()` and executes the part of the body **after** `this("unknown")`.

**Common point of confusion:** `this(...)` is not the same as `new Product(...)`:
- `this(...)` chains constructors **on the object currently being constructed**.
- `new Product(...)` creates **a new object**.
- Simply calling `this(...)` does not cause the JVM to allocate an additional instance.

### In Java 17, `this(...)` Comes First in the Constructor

```java
Product() {
    this("default");
    System.out.println("done");
}
```

Invalid in Java 17:

```java
// Product() {
//     System.out.println("before");
//     this("default"); // WRONG: explicit constructor invocation must be first.
// }
```

Why the version matters so much: **Java 17** requires an explicit constructor invocation `this(...)` or `super(...)` to be the first statement of the constructor body. Do not use the flexible syntax of newer Java releases when the exercise is testing Java 17.

## 4. Core Example: Two Constructors, Instance Block Still Runs Once

Save as **`ThisChainDemo.java`**:

```java
class Device {
    private final String name;

    {
        System.out.println("Device instance block");
    }

    Device() {
        this("default");
        System.out.println("Device()");
    }

    Device(String name) {
        this.name = name;
        System.out.println("Device(String): " + name);
    }

    String name() {
        return name;
    }
}

public class ThisChainDemo {
    public static void main(String[] args) {
        Device device = new Device();
        System.out.println("Result: " + device.name());
    }
}
```

Run:

```bash
javac -encoding UTF-8 ThisChainDemo.java
java ThisChainDemo
```

**Stdout:**

```text
Device instance block
Device(String): default
Device()
Result: default
```

**Step-by-step analysis:**

1. `new Device()` selects the no-argument constructor.
2. `Device()` starts with `this("default")` and transfers to `Device(String)` for **the same object**.
3. `Device(String)` does not write `this(...)` / `super(...)`, so Java 17 provides an implicit `super()` call, leading to `Object()`.
4. The instance initialization process for `Device` runs: the block prints **exactly once**.
5. The `Device(String)` body runs, assigns `this.name`, and prints the corresponding line.
6. Control returns to `Device()` and prints `Device()`.
7. The caller receives the constructed object, and `name()` returns `default`.

If you mistakenly think the instance block runs at the start of **every constructor body**, you would wrongly predict two `Device instance block` lines. In reality, instance initializers **belong to the class's instance initialization cycle** and are not duplicated and re-executed when control returns to a constructor delegating via `this(...)`.

## 5. Three Constructors Chained with `this(...)`: Counting Executions

Extending the chain:

```java
class Chain {
    Chain() {
        this(1);
        System.out.println("Chain()");
    }

    Chain(int value) {
        this(value, "X");
        System.out.println("Chain(int)");
    }

    Chain(int value, String label) {
        System.out.println("Chain(int,String)");
    }
}
```

When creating `new Chain()`, the constructor call chain is:

```text
Chain()
  -> this(1)
     -> Chain(int)
        -> this(1, "X")
           -> Chain(int, String)
              -> super() / Object()
              -> instance initializers of Chain: ONE PASS
              -> body of Chain(int, String)
        <- body of Chain(int)
  <- body of Chain()
```

**Execution counts:**
- Constructor bodies: **3** (once for each overload in the chain).
- Instance blocks of `Chain`: **once per block**, not three times.
- Instance field initializers of `Chain`: **once per initializer** during `Chain`'s initialization phase.
- Number of `Chain` objects created by **one** `new Chain()`: **1**.

### Runnable Three-Constructor Program

Save **`ThreeConstructorChainDemo.java`**:

```java
class Chain {
    int marker = log("Field initializer");

    {
        log("Instance block");
    }

    Chain() {
        this(1);
        log("Chain()");
    }

    Chain(int value) {
        this(value, "X");
        log("Chain(int): " + value);
    }

    Chain(int value, String label) {
        log("Chain(int,String): " + value + "," + label);
    }

    private int log(String text) {
        System.out.println(text);
        return 1;
    }
}

public class ThreeConstructorChainDemo {
    public static void main(String[] args) {
        new Chain();
    }
}
```

```bash
javac -encoding UTF-8 ThreeConstructorChainDemo.java
java ThreeConstructorChainDemo
```

**Stdout:**

```text
Field initializer
Instance block
Chain(int,String): 1,X
Chain(int): 1
Chain()
```

The field initializer calls `log` and receives the value `1` to store in `marker`. The instance block also calls `log` but discards the return value. Both run in **one pass**. Only the constructor bodies appear in order from the **deepest target constructor** back to the delegating constructor.

## 6. `super(...)` Chains Constructors from Subclass to Superclass

Every regular class (except `Object`) has a direct superclass. On the object creation path, a constructor that does not delegate via `this(...)` must call a valid superclass constructor, **explicitly or implicitly**:

```java
class Parent {
    Parent() {
        System.out.println("Parent()");
    }
}

class Child extends Parent {
    Child() {
        super();
        System.out.println("Child()");
    }
}
```

`super()` in `Child()` calls the superclass constructor `Parent()` to initialize **the Parent part of the same Child object**, without creating an independent `Parent` object.

Result when running `new Child()`:

```text
Parent()
Child()
```

If `super();` is omitted in this example, Java 17 inserts `super();` implicitly. However, if the superclass **does not have an accessible no-arg constructor**, the subclass must call an appropriate `super(arguments)` or have another constructor chaining path that leads to the right superclass call.

### `super(...)` Is Not `new Parent(...)`

```java
super(5);           // Initializes the superclass part of the current object.
new Parent(5);      // Creates a NEW and independent Parent object.
```

The two operations have different meanings. Creating a new Parent object with `new` can additionally trigger instance initializers/constructors for **that new object**; a `super(...)` call does not.

## 7. Inheritance: Superclass Initializer Runs Before Subclass Initializer

Given two classes:

```java
class Parent {
    int a = initializeA();

    {
        System.out.println("Parent block");
    }

    Parent() {
        System.out.println("Parent constructor");
    }

    private int initializeA() {
        System.out.println("Parent field");
        return 1;
    }
}

class Child extends Parent {
    int b = initializeB();

    {
        System.out.println("Child block");
    }

    Child() {
        System.out.println("Child constructor");
    }

    private int initializeB() {
        System.out.println("Child field");
        return 2;
    }
}
```

During `new Child()`, after the superclass `Object` is processed, the order we observe is:

```text
Parent field
Parent block
Parent constructor
Child field
Child block
Child constructor
```

**Key point:** not all instance field initializers of all classes run together before all constructor bodies. Java initializes **the superclass part first**, including the superclass's field initializers, instance blocks, and constructor body; only after that does subclass initialization follow.

## 8. Complete Multi-Class Example: superclass → subclass

Save **`InheritanceInitializationDemo.java`**:

```java
class Parent {
    private int parentNumber = initParentNumber();

    {
        System.out.println("Parent block");
    }

    Parent() {
        System.out.println("Parent constructor: " + parentNumber);
    }

    private int initParentNumber() {
        System.out.println("Parent field");
        return 10;
    }
}

class Child extends Parent {
    private int childNumber = initChildNumber();

    {
        System.out.println("Child block");
    }

    Child() {
        System.out.println("Child constructor: " + childNumber);
    }

    private int initChildNumber() {
        System.out.println("Child field");
        return 20;
    }
}

public class InheritanceInitializationDemo {
    public static void main(String[] args) {
        new Child();
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 InheritanceInitializationDemo.java
java InheritanceInitializationDemo
```

**Exact stdout:**

```text
Parent field
Parent block
Parent constructor: 10
Child field
Child block
Child constructor: 20
```

The order is not “reading both classes from top to bottom as a whole”. It depends on the **parent/child constructor call chain**, where each superclass part completes before continuing with the subclass's instance initialization.

### Does It Create a Parent Object and Then a Child Object?

**No.** `new Child()` allocates a single object whose object structure includes the state defined by the classes in the hierarchy. The `Parent()` constructor handles the superclass part **within the same Child object**.

Therefore, when we say “each class runs its initializer once”, we are referring to **each corresponding initialization part of a single object**, not the number of separate objects.

## 9. Combining `super(...)` and `this(...)` in the Same Chain

Suppose `Child()` calls `this("A")` and `Child(String)` calls `super(5)`. The correct flow is:

```text
new Child()
  Child() starts
    -> this("A")
       Child(String) starts
         -> super(5)
            Parent(int) runs (including Parent's initializers)
         <- Parent(int) finishes
       instance initializers of Child: one pass
       body of Child(String)
    <- Child(String) finishes
  body of Child()
Object construction complete
```

Importantly, **it is not the case that both Child constructors run Child's instance initializers**. They chain together within **a single Child initialization**.

### Java 17 Demonstration Program

Save **`CombinedChainDemo.java`**:

```java
class Parent {
    {
        System.out.println("P: block");
    }

    Parent(int number) {
        System.out.println("P: constructor " + number);
    }
}

class Child extends Parent {
    private String name = initName();

    {
        System.out.println("C: block");
    }

    Child() {
        this("An");
        System.out.println("C: no-arg body");
    }

    Child(String name) {
        super(5);
        this.name = name;
        System.out.println("C: String body " + this.name);
    }

    private String initName() {
        System.out.println("C: field");
        return "default";
    }
}

public class CombinedChainDemo {
    public static void main(String[] args) {
        new Child();
    }
}
```

```bash
javac -encoding UTF-8 CombinedChainDemo.java
java CombinedChainDemo
```

**Stdout:**

```text
P: block
P: constructor 5
C: field
C: block
C: String body An
C: no-arg body
```

`Parent` does not have a zero-argument constructor; `Child(String)` calls `super(5)` explicitly. `Child()` calls `this("An")`, and `super()` cannot also be added inside the `Child()` constructor itself.

## 10. Each Class in the Hierarchy Initializes Its Instance Part in One Pass

Suppose:

```text
Object
  |
  v
Grandparent
  |
  v
Parent
  |
  v
Child
```

With a `new Child()` call and valid constructor chaining, a normally completing chain goes through:

1. The constructor phase of `Object`.
2. The instance field initializers/instance blocks of `Grandparent`, followed by the selected constructor body and other constructor bodies in `Grandparent`'s `this(...)` chain.
3. Similarly for `Parent`.
4. Similarly for `Child`.

Count by class:

| Class in the chain | Runs per instance initializer when creating one `Child` |
| --- | --- |
| `Grandparent` | 1 |
| `Parent` | 1 |
| `Child` | 1 |
| `Object` | Follows the superclass initialization mechanism; `Object` has no user-written instance blocks in the example |

If each class has **two** instance blocks, then **each block** runs in one pass, meaning two separate block executions **within that class**, not “both blocks combined into a single line”. If there are **three classes**, each with one block, that gives a total of **three block executions** for one `new Child()`.

### General Calculation

For the successful creation of an object of class `T` via a normal constructor, if each class `K` along the superclass path from `Object` to `T` declares `b(K)` instance initialization blocks, then the number of executions of those corresponding blocks during that process is:

\[
\sum_{K \in \mathrm{hierarchy}(T)} b(K).
\]

This is the number of **block executions** in one normally completed initialization, **not** the number of times Java invokes constructors, and assumes the blocks are traversed without being cut short by an exception.

## 11. Example with Three Inheritance Levels and Multiple Constructors

Save **`ThreeLevelsDemo.java`**:

```java
class Grandparent {
    {
        System.out.println("G: block");
    }

    Grandparent() {
        this(1);
        System.out.println("G: no-arg");
    }

    Grandparent(int number) {
        System.out.println("G: int " + number);
    }
}

class Parent extends Grandparent {
    {
        System.out.println("P: block");
    }

    Parent() {
        super();
        System.out.println("P: no-arg");
    }
}

class Child extends Parent {
    {
        System.out.println("C: block");
    }

    Child() {
        this("X");
        System.out.println("C: no-arg");
    }

    Child(String name) {
        super();
        System.out.println("C: String " + name);
    }
}

public class ThreeLevelsDemo {
    public static void main(String[] args) {
        new Child();
    }
}
```

Commands:

```bash
javac -encoding UTF-8 ThreeLevelsDemo.java
java ThreeLevelsDemo
```

**Stdout:**

```text
G: block
G: int 1
G: no-arg
P: block
P: no-arg
C: block
C: String X
C: no-arg
```

Quantitative analysis:

- **One** `Child` object is created.
- `Grandparent` has **two constructor bodies** run because `Grandparent()` calls `this(1)`; block `G` prints **only once**.
- `Parent` has one constructor body and block `P` runs once.
- `Child` has **two constructor bodies** because `Child()` calls `this("X")`; block `C` prints **only once**.
- The total number of lines starting with `G: block`, `P: block`, `C: block` is **3**. The total number of constructor body logs is **5**.

This example proves through its output that **the number of constructor bodies in the chain does not determine how many times instance blocks run**.

## 12. Ordering Between Field Initializers and Instance Blocks of the Same Class

Within the same class, **instance field initializers** and **instance initialization blocks** are executed **in the order they appear in the source code**, as long as they belong to that class's instance initialization phase.

Example:

```java
class Sequence {
    private int a = print("field a", 1);

    {
        print("block 1", 0);
    }

    private int b = print("field b", 2);

    {
        print("block 2", 0);
    }

    Sequence() {
        print("constructor", 0);
    }

    private int print(String label, int result) {
        System.out.println(label);
        return result;
    }
}
```

With `new Sequence()`:

```text
field a
block 1
field b
block 2
constructor
```

**There is no rule saying “all field initializers finish running first and then all instance blocks run”.** They are processed interleaved in textual order within the same class.

### Do Not Confuse with Ordering in the Hierarchy

Textual order applies **within each class**. If `Parent` has an instance initializer at the end of `Parent.java` while `Child` has an instance initializer at the top of `Child.java`, the `Parent` part is still initialized before the `Child` part according to the constructor chain.

## 13. Interleaved Order Example with Stdout

Save **`InterleavedInitializersDemo.java`**:

```java
class Sequence {
    int first = trace("field first", 1);

    {
        trace("block A", 0);
    }

    int second = trace("field second", 2);

    {
        trace("block B", 0);
    }

    Sequence() {
        System.out.println("constructor: " + first + "," + second);
    }

    private int trace(String text, int result) {
        System.out.println(text);
        return result;
    }
}

public class InterleavedInitializersDemo {
    public static void main(String[] args) {
        new Sequence();
    }
}
```

```bash
javac -encoding UTF-8 InterleavedInitializersDemo.java
java InterleavedInitializersDemo
```

**Stdout:**

```text
field first
block A
field second
block B
constructor: 1,2
```

The benefit of this representation is that it **clearly expresses where initialization effects are declared**. However, if an initializer is too complex, makes exceptions hard to trace, or depends on extensive state, consider moving the logic into a constructor or helper method for easier testing.

## 14. Default Field Values Appear Before Initializers

When an object is allocated, instance fields have **type-specific default values** before initializers or constructor bodies assign concrete values:

| Field type | Default value |
| --- | --- |
| `boolean` | `false` |
| `byte`, `short`, `int`, `long` | `0` of the corresponding type |
| `float`, `double` | `0.0` of the corresponding type |
| `char` | the `\u0000` character |
| Reference types | `null` |

By rule, an object's fields are set to their default state **before** the execution phase of constructors and instance initializers.

Example:

```java
class Demo {
    int value;

    Demo() {
        System.out.println(value); // 0 if there is no initializer or other assignment.
        value = 10;
    }
}
```

**Avoid confusing this with local variables:** local variables are not automatically given a default value by Java to be read before initialization. A local variable that is not definitely assigned cannot be validly read.

### A Parent Constructor Can Observe the Default State of the Subclass Part

This is especially dangerous when a superclass constructor invokes a method overridden by a subclass; the subclass's initializers **have not finished running** at the time the superclass constructor executes.

## 15. Common Pitfall: Calling an Overridable Method in a Parent Constructor

In a constructor chain involving `super(...)` and `this(...)`, a **virtual call** from a superclass constructor can occur **before** the subclass's instance fields/blocks run:

```java
class Parent {
    Parent() { report(); }
    void report() { }
}
class Child extends Parent {
    String message = "READY";
    @Override void report() { System.out.println(message); }
}
```

This is a **snippet**, not a standalone program. When creating `new Child()`, `report()` in Parent may print `null` because it dispatches to Child's override while `message` is still at its default value. This **does not cause Child's instance initializers to run any extra times**: after the Parent constructor finishes, Child's initializers run in **one pass** for that object, followed by Child's constructor bodies along the chain.

Therefore, when doing exercises that **count initialization passes**, separate **how many times a callback is invoked in a constructor** from **how many times each class's fields/instance blocks run**. Avoid overridden callbacks in constructors; runnable examples and alternative designs are analyzed in depth in the lesson on calling an overridden method before object initialization completes.

## 16. `this(...)` and `super(...)` Cannot Be Called Together in a Java 17 Constructor

This form is **invalid**:

```java
class Base {
    Base() {
    }
}

class Derived extends Base {
    Derived() {
        // this(1);
        // super();
        // WRONG if both explicit constructor invocations are used.
    }

    Derived(int value) {
        super();
    }
}
```

In Java 17, a constructor can have **at most one explicit constructor invocation at the beginning**:

- `this(arguments);`: delegates to another constructor of the **same class**.
- `super(arguments);`: delegates to an appropriate superclass constructor.
- Or write neither, in which case the compiler inserts `super();` when required by the rules.

If a constructor chooses `this(...)`, the delegated constructor continues the chain until reaching a constructor in the same class that no longer uses `this(...)`, and then the superclass part is initialized.

### A `this(...)` Constructor Does Not Create a Second Branch to Run Initializers

A constructor body does not automatically run `super()` **after** `this(...)` finishes. Doing so would initialize the superclass twice, which contradicts the correct model. Chained constructor calls go through only **one initialization path** for the same object.

## 17. A `this(...)` Chain Cannot Form a Cycle

**Invalid** example:

```java
class InvalidChain {
    InvalidChain() {
        this(1);
    }

    InvalidChain(int number) {
        this();
    }
}
```

The compiler detects a recursive constructor invocation chain:

```text
InvalidChain() -> InvalidChain(int) -> InvalidChain() -> ...
```

Java does not allow a `this(...)` cycle that prevents the constructor chain from ever reaching a constructor with a valid superclass call path.

### Proper Design

Have one overload serve as the primary initialization point:

```java
class ValidChain {
    private final int number;

    ValidChain() {
        this(1);
    }

    ValidChain(int number) {
        this.number = number;
    }
}
```

The `ValidChain(int)` constructor does not call `this(...)`; Java 17 inserts `super()` if the default superclass call is valid. After the superclass completes, `ValidChain`'s instance initializers execute in one pass, and then the `ValidChain(int)` body assigns the `number` field.

This is the **constructor delegation** pattern: simpler overloads forward to the constructor that has the full set of parameters.

## 18. Constructor Overloads Do Not Equate to Instance Initialization Count

When a class has four overloads:

```java
class Request {
    Request() { this("GET"); }
    Request(String method) { this(method, "/"); }
    Request(String method, String path) { this(method, path, 0); }
    Request(String method, String path, int version) { }
}
```

If all are valid, `new Request()` causes **four constructor bodies** to execute in unwinding order, yet `Request`'s instance initializers still run in only one pass.

If `new Request("POST", "/orders", 1)` is called directly, only the body of the three-parameter overload runs, yet the instance initializers still run in **one pass**.

**The number of constructor overloads declared** in a class **does not determine** how many times instance blocks run at all.

### Prediction Table

| Call | Constructor bodies executed (in `Request`) | Execution passes of an instance block in `Request` |
| --- | --- | --- |
| `new Request()` | 4 | 1 |
| `new Request("GET")` | 3 | 1 |
| `new Request("GET", "/")` | 2 | 1 |
| `new Request("GET", "/", 2)` | 1 | 1 |

The table assumes that the constructors in the snippet all complete normally, the superclass constructor is valid, and no code creates additional `Request` objects inside the initializer.

## 19. Testing Overloads and Counting Accurately

Save **`ConstructorCountDemo.java`**:

```java
class Request {
    static int blockExecutions;

    {
        blockExecutions++;
        System.out.println("block #" + blockExecutions);
    }

    Request() {
        this("GET");
        System.out.println("body Request()");
    }

    Request(String method) {
        this(method, "/");
        System.out.println("body Request(String)");
    }

    Request(String method, String path) {
        System.out.println("body Request(String,String)");
    }
}

public class ConstructorCountDemo {
    public static void main(String[] args) {
        new Request();
        new Request("POST", "/save");
        System.out.println("total blocks = " + Request.blockExecutions);
    }
}
```

```bash
javac -encoding UTF-8 ConstructorCountDemo.java
java ConstructorCountDemo
```

**Stdout:**

```text
block #1
body Request(String,String)
body Request(String)
body Request()
block #2
body Request(String,String)
total blocks = 2
```

Why is the total `2`?

- The `new Request()` call runs three constructor bodies, but the instance block runs in only **one pass**.
- The `new Request("POST", "/save")` call runs one constructor body, and the instance block also runs in **one pass**.
- Across the two instance creations, the block runs twice in total. The static counter is used only to **observe the execution count** and is not independent per-Request data.

**Be careful when counting:** if an instance block calls `new Request(...)` again, that creates **another object**, and therefore will trigger additional initializer passes. The table above does not apply when the code has the side effect of creating additional instances.

## 20. Static Initializers Differ from Instance Initializers in Execution Count

Save **`StaticVsInstanceDemo.java`**:

```java
class Widget {
    static {
        System.out.println("static block");
    }

    {
        System.out.println("instance block");
    }

    Widget() {
        System.out.println("constructor");
    }
}

public class StaticVsInstanceDemo {
    public static void main(String[] args) {
        System.out.println("before first new");
        new Widget();

        System.out.println("before second new");
        new Widget();
    }
}
```

```bash
javac -encoding UTF-8 StaticVsInstanceDemo.java
java StaticVsInstanceDemo
```

**Stdout:**

```text
before first new
static block
instance block
constructor
before second new
instance block
constructor
```

- `Widget` is initialized as a class before the first active use that creates an instance in the example.
- The static block prints **once** during the class initialization of `Widget`.
- Each time `new Widget()` creates an object, the instance block prints **once** and then the constructor body prints once.
- The second `new` does not make the static block run again while using the same class initialization state.

**To be precise:** static initialization occurs according to the JVM's class/interface initialization rules, not “running again on every static method call”. Different class loaders can define separate runtime classes; the same class name does not necessarily have a single global initialization across all class loaders.

## 21. Static Initialization and Instance Initialization Across a Hierarchy

When a subclass `Child` is initialized for the first time, the JVM ensures that any required class initialization of the superclass occurs according to the rules before the subclass completes its class initialization. After that, object creations run **instance initialization** per object.

Example:

```java
class Parent {
    static { System.out.println("P static"); }
    { System.out.println("P instance"); }
    Parent() { System.out.println("P ctor"); }
}

class Child extends Parent {
    static { System.out.println("C static"); }
    { System.out.println("C instance"); }
    Child() { System.out.println("C ctor"); }
}
```

If `Child` has not previously been initialized during execution, the first `new Child()` yields the order:

```text
P static
C static
P instance
P ctor
C instance
C ctor
```

The next `new Child()` yields only the instance/ctor lines:

```text
P instance
P ctor
C instance
C ctor
```

### Runnable Program

Save **`HierarchyStaticInstanceDemo.java`**:

```java
class Parent {
    static {
        System.out.println("P static");
    }

    {
        System.out.println("P instance");
    }

    Parent() {
        System.out.println("P ctor");
    }
}

class Child extends Parent {
    static {
        System.out.println("C static");
    }

    {
        System.out.println("C instance");
    }

    Child() {
        System.out.println("C ctor");
    }
}

public class HierarchyStaticInstanceDemo {
    public static void main(String[] args) {
        System.out.println("first");
        new Child();

        System.out.println("second");
        new Child();
    }
}
```

```bash
javac -encoding UTF-8 HierarchyStaticInstanceDemo.java
java HierarchyStaticInstanceDemo
```

**Stdout:**

```text
first
P static
C static
P instance
P ctor
C instance
C ctor
second
P instance
P ctor
C instance
C ctor
```

The example intentionally prints the initializer type names so that learners do not mistakenly add static block execution counts into the count of instance blocks.

## 22. A Class with Multiple Instance Blocks: Count **Per Block**

Example:

```java
class MultiBlock {
    {
        System.out.println("A");
    }

    {
        System.out.println("B");
    }

    MultiBlock() {
        this(1);
        System.out.println("zero");
    }

    MultiBlock(int number) {
        System.out.println("int");
    }
}
```

With `new MultiBlock()`:

```text
A
B
int
zero
```

There are:
- **2 block executions**, because the class declares **2 blocks**, and each block runs once.
- **2 constructor body executions**, because `MultiBlock()` calls `this(1)`.
- **1 object instance**, because there is only one `new MultiBlock()`.

If `new MultiBlock()` runs twice, we get **4 block executions** in total (A twice, B twice), but it is not that each of A/B runs twice during *a single* object creation.

### Conditional Formula

For a single class with `b` blocks, creating `n` instances using constructors that complete normally, with no auxiliary code creating other instances, the total number of instance block executions of that class itself is:

\[
n \times b.
\]

Having one, two, or more constructors in a `this(...)` chain introduces no additional factor.

## 23. Distinguishing “Once per Object” from “Only Once in the Program's Lifetime”

An **instance initializer** is not a singleton initializer.

```java
new Sample();
new Sample();
new Sample();
```

If each call successfully creates an independent `Sample`, every instance block of `Sample` runs **three times** in total.

However:

```java
Sample sample = new Sample();
Sample alias = sample;
```

the two variables `sample` and `alias` can point to **the same object**. The assignment `alias = sample` does **not** create an instance and therefore does **not** run the instance block again.

Similarly, passing an object as an argument:

```java
process(sample);
```

only copies the reference value and does not create a new object to make the instance initializer run again.

**Count the objects actually initialized, not the number of reference variables or the number of times an object is accessed.**

## 24. `new` Inside a Constructor or Initializer Can Create Multiple Objects

The rule “one `new Outer()` → one pass for each initializer of Outer” does not mean **the program creates only one object in total**.

Example:

```java
class Engine {
    Engine() {
        System.out.println("Engine ctor");
    }
}

class Car {
    Engine engine = new Engine();

    Car() {
        System.out.println("Car ctor");
    }
}
```

`new Car()` performs:
1. Creates a `Car`.
2. Inside `Car`'s field initializer, executes `new Engine()`, creating **another Engine object**.
3. Initializes and runs `Engine`'s constructor for the Engine object.
4. Runs `Car`'s constructor body.

Output:

```text
Engine ctor
Car ctor
```

The appearance of two constructors here is because **two objects are actually created**, not because `this(...)` created an extra object.

### Distinguishing Superclass Objects

`new Child()` does **not** use `new Parent()` to create a second Parent object. It calls the Parent constructor on **the same Child object**. This is the key difference when tallying allocations and initialization passes.

## 25. Initialization Blocks Do Not Replace Constructor Parameters

An instance initialization block does not have its own parameter list:

```java
class Order {
    int total;

    {
        total = 0;
    }

    Order(int initial) {
        total = initial;
    }
}
```

The block can initialize a common value such as `0`, but `initial` is a constructor parameter. Inside a normal instance initializer of a class, you cannot assume access to a parameter declared only by a specific constructor overload.

If each overload needs a different value, it should be handled through a primary constructor and `this(...)` delegation.

### Pattern with a Primary Constructor

```java
class Order {
    private final String id;
    private final int total;

    {
        System.out.println("Order block");
    }

    Order() {
        this("UNKNOWN", 0);
    }

    Order(String id, int total) {
        this.id = id;
        this.total = total;
    }
}
```

The block prints once regardless of which overload is called; the two final fields are initialized in the primary constructor. This is a clean design when overloads differ only in **default values**.

**Avoid writing logic that depends on specific parameters inside an instance block**: code in a block is not called like a method with a parameter list.

## 26. Blank Final Fields in Constructor Chaining

A `final instance field` without an initializer at its declaration (*blank final*) must be initialized according to the **definite assignment** rules.

Example:

```java
class Session {
    private final String id;

    Session() {
        this("default");
    }

    Session(String id) {
        this.id = id;
    }
}
```

`new Session()` calls `Session()`, delegating via `this("default")`. The `id` field is assigned in the primary constructor **once** for that object.

Invalid:

```java
class InvalidSession {
    private final String id;

    InvalidSession() {
        this("default");
        // id = "changed"; // WRONG: field has already been assigned in the chain.
    }

    InvalidSession(String id) {
        this.id = id;
    }
}
```

**Meaning:** constructor delegation is often used to centralize the initialization of final fields in **a single constructor with the full set of parameters**, reducing the risk of a branch missing an assignment or assigning multiple times.

### Note on Instance Initializers with Blank Finals

A blank final field can also be assigned by a valid instance initializer:

```java
class Ticket {
    private final String type;

    {
        type = "STANDARD";
    }

    Ticket() {
        // type = "OTHER"; // WRONG: cannot assign a second time.
    }
}
```

The block runs **once per object** and assigns `type` exactly once. Even if `Ticket()` calls another overload via `this(...)`, the block does not run again to assign it a second time.

## 27. If a Constructor Has `return;`, Do Initializers Still Run?

A Java constructor can use **`return;` without an expression** to exit the constructor body early in valid situations, but it **does not skip** the superclass initialization and instance initializers, which have already run **before the body**.

Example:

```java
class Example {
    {
        System.out.println("block");
    }

    Example(boolean stop) {
        if (stop) {
            return;
        }
        System.out.println("body after check");
    }
}
```

`new Example(true)` still prints:

```text
block
```

The constructor body checks `stop` and returns early, and does **not** print `body after check`.

### Java 17 Program

Save **`ConstructorReturnDemo.java`**:

```java
class Example {
    {
        System.out.println("block");
    }

    Example(boolean stop) {
        if (stop) {
            return;
        }
        System.out.println("continued");
    }
}

public class ConstructorReturnDemo {
    public static void main(String[] args) {
        new Example(true);
        new Example(false);
    }
}
```

```bash
javac -encoding UTF-8 ConstructorReturnDemo.java
java ConstructorReturnDemo
```

Stdout:

```text
block
block
continued
```

**You must not** write `return someObject;` in a constructor to “return another object”; a constructor has no return type and does not return an expression.

## 28. Exceptions in Initializers: No Guarantee That the Entire Chain Completes

The “each initializer runs once” tables above describe an **initialization chain that executes normally**. If an initializer or constructor throws an exception, the code after it may **not be executed**.

Example:

```java
class Fragile {
    {
        System.out.println("before error");
        if (true) {
            throw new IllegalStateException("failed");
        }
    }

    Fragile() {
        System.out.println("constructor body");
    }
}
```

This snippet intentionally demonstrates a runtime error. Java starts the instance block, prints the line before the exception, and then throws `IllegalStateException`; the constructor body does not print because it is never reached. No complete object is returned from that `new Fragile()` call.

### Runnable Example and Catching the Error

Save **`InitializationExceptionDemo.java`**:

```java
class Fragile {
    {
        System.out.println("block begins");
        if (System.nanoTime() >= 0) {
            throw new IllegalStateException("failed");
        }
    }

    Fragile() {
        System.out.println("constructor body");
    }
}

public class InitializationExceptionDemo {
    public static void main(String[] args) {
        try {
            new Fragile();
        } catch (IllegalStateException error) {
            System.out.println("caught: " + error.getMessage());
        }
    }
}
```

In the example above, the condition `System.nanoTime() >= 0` depends on the JVM's relative monotonic clock and **should not be used to trigger an error reliably**. For a precise example, replace it with a method that throws an exception unconditionally:

```java
class Fragile {
    {
        System.out.println("block begins");
        fail();
    }

    static void fail() {
        throw new IllegalStateException("failed");
    }

    Fragile() {
        System.out.println("constructor body");
    }
}

public class InitializationExceptionDemo {
    public static void main(String[] args) {
        try {
            new Fragile();
        } catch (IllegalStateException error) {
            System.out.println("caught: " + error.getMessage());
        }
    }
}
```

Use **the second version** when saving the file `InitializationExceptionDemo.java`; the two snippets are **alternative versions** and must not be placed together in the same package.

```bash
javac -encoding UTF-8 InitializationExceptionDemo.java
java InitializationExceptionDemo
```

**Stdout of the second version:**

```text
block begins
caught: failed
```

The condition for a constructor body to run is that the preceding phases **complete normally**. If a superclass constructor throws an exception, subclass initializers are also not executed because control never returns to the subclass initialization part.

### Exceptions in Static Initialization Are Different

An error from `static { ... }` is a **class initialization** error, which may be wrapped or manifested through class initialization error types such as `ExceptionInInitializerError`. Do not equate it with an `IllegalStateException` thrown from a normal instance block.

## 29. If the Parent Constructor Throws an Error, Does the Subclass Block Run?

**No, if the superclass constructor does not complete normally before subclass initialization begins.**

Example:

```java
class Parent {
    Parent() {
        System.out.println("Parent ctor");
        throw new IllegalArgumentException("stop");
    }
}

class Child extends Parent {
    {
        System.out.println("Child block");
    }

    Child() {
        System.out.println("Child ctor");
    }
}
```

With `new Child()`:
- `Parent ctor` is printed.
- The superclass constructor throws an exception.
- `Child block` is **not** printed.
- `Child ctor` is **not** printed.

This is a direct consequence of the parent-before-child ordering.

**Do not interpret this exception as the block being “randomly skipped”.** The initialization process has not yet reached `Child`'s instance initializer phase.

### Be Careful with Side Effects Before an Error

If the superclass constructor has already registered `this` somewhere else before throwing an exception, an **incomplete** object can be observed. Avoid exposing `this` prematurely and avoid hard-to-undo side effects in constructors.

## 30. `this` Escape: Do Not Let an Incomplete Object Be Used

A constructor or instance block might call:

```java
registry.add(this);
```

If `this` is passed outside prematurely, other code can use the object while subclass fields or other initializers **have not yet completed**.

Risks include:
- An observer/callback sees default values `0`/`null` instead of the final state.
- Another thread accesses a field that has not been safely published.
- An overridden method runs on the subclass object before the subclass initializer has run.
- The object's invariant has not been established yet, yet is treated as valid.

**How to reduce risk:** create the complete object first and then register callbacks or start threads; consider a static factory or builder to separate construction from registration.

Do not put complex logic that “calls out to the outside world” inside an instance block merely because you want code to run before the constructor body.

## 31. Constructor Chaining and Accessing `this`/`super` in Java 17

To understand Java 17 clearly:

```java
class Base {
    Base(int id) {
    }
}

class Derived extends Base {
    Derived() {
        this(1);  // Valid: explicit invocation at the start of the constructor.
    }

    Derived(int id) {
        super(id); // Valid: explicit invocation at the start of the constructor.
    }
}
```

However:

```java
class InvalidDerived extends Base {
    InvalidDerived() {
        // super(this.hashCode()); // WRONG: cannot use
        // the receiver this in that way before the superclass constructor.
    }
}
```

These are illustrative snippets, and `InvalidDerived` **as written above does not compile** because it does not call an appropriate superclass constructor (class `Base` has no no-arg constructor), even when the line with `super(...)` is commented out.

The key takeaway: **before the constructor chain completes the superclass invocation, instance state cannot be used freely as in a regular instance method**. Java 17 restricts accessing `this`/`super` inside an explicit constructor invocation; keep chaining calls clear and pass arguments that can be validly evaluated.

### Constructor Overloading and Argument Evaluation

`this(1 + 2)` selects an overload based on the types of the argument expressions. The argument expressions are evaluated according to Java's rules when executing the corresponding call, but `this(...)` itself does **not** mean “there is already a new object”.

Avoid putting hard-to-predict side effects into constructor argument expressions if understanding the initialization order is already complex.

## 32. Counting Problem: Two Objects, Three Classes, Two Blocks per Class

Suppose:
- `A` has one instance block.
- `B extends A` has two instance blocks.
- `C extends B` has one instance block.
- Each class has valid constructor chaining (any number of overloads).
- `new C()` is executed **twice**, both succeeding.
- No initializer creates additional `A/B/C` objects.

Each `new C()` triggers:
- `A`'s block: 1 time.
- `B`'s two blocks: 2 times in total.
- `C`'s block: 1 time.

Thus each object has **4 block executions**, and creating **2 objects** gives **8 block executions**.

If constructor `C()` also calls `this(int)` and then `this(int,String)`, the number **8** remains unchanged. Constructor chaining only increases the number of **executed constructor bodies**, not the number of block executions per class.

### Systematic Approach

1. Count the **actual object creation expressions** that are executed and succeed.
2. For each object, draw the superclass chain.
3. Count the **instance blocks + instance field initializers** in each class; distinguish by kind if the question asks for it.
4. Mark **one instance initialization pass per class** along the chain.
5. Count constructor bodies chained via `this(...)` separately.
6. Count static blocks separately if the question involves class initialization.
7. Check for exceptions or code creating additional objects inside initializers before concluding.

## 33. Comprehensive Java 17 Practice Exercise

This is a trace exercise combining **static initialization, field initializers, instance blocks, constructor `this(...)`, `super(...)`, and multiple object instances**.

Save **`FullInitializationTraceDemo.java`**:

```java
class Base {
    static {
        System.out.println("Base.static");
    }

    int baseValue = trace("Base.field", 1);

    {
        System.out.println("Base.block");
    }

    Base() {
        this(10);
        System.out.println("Base()");
    }

    Base(int value) {
        System.out.println("Base(int): " + value);
    }

    private int trace(String event, int result) {
        System.out.println(event);
        return result;
    }
}

class Derived extends Base {
    static {
        System.out.println("Derived.static");
    }

    int derivedValue = traceDerived("Derived.field", 2);

    {
        System.out.println("Derived.block");
    }

    Derived() {
        this("X");
        System.out.println("Derived()");
    }

    Derived(String label) {
        super();
        System.out.println("Derived(String): " + label);
    }

    private int traceDerived(String event, int result) {
        System.out.println(event);
        return result;
    }
}

public class FullInitializationTraceDemo {
    public static void main(String[] args) {
        System.out.println("START");
        new Derived();
        System.out.println("NEXT");
        new Derived("Y");
        System.out.println("END");
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 FullInitializationTraceDemo.java
java FullInitializationTraceDemo
```

**Exact stdout:**

```text
START
Base.static
Derived.static
Base.field
Base.block
Base(int): 10
Base()
Derived.field
Derived.block
Derived(String): X
Derived()
NEXT
Base.field
Base.block
Base(int): 10
Base()
Derived.field
Derived.block
Derived(String): Y
END
```

### Each Phase of the First Object

1. `main` prints `START`.
2. The first `new Derived()` causes the JVM to initialize classes `Base` and `Derived` as needed: the static blocks print `Base.static`, `Derived.static`.
3. `Derived()` calls `this("X")` → constructor `Derived(String)`.
4. `Derived(String)` calls `super()` → `Base()`.
5. `Base()` calls `this(10)` → `Base(int)`.
6. `Base` runs its instance field initializer and block: `Base.field`, `Base.block`.
7. The `Base(int)` body prints `Base(int): 10`.
8. Control returns to the `Base()` body, which prints `Base()`.
9. `Derived` runs its field initializer and block: `Derived.field`, `Derived.block`.
10. The `Derived(String)` body prints `Derived(String): X`.
11. The `Derived()` body prints `Derived()`.

### The Second Object

On `new Derived("Y")`:
- Does not re-run the two static blocks because class initialization has already completed.
- Still runs **each instance field initializer/block of Base and Derived in one pass** for the new object.
- Does not run the `Derived()` body because the directly selected constructor is `Derived(String)`.
- Constructor `Base()` still delegates to `Base(int)`, so both bodies of `Base` run.

**Lesson learned:** logs like this are easy to misread unless you trace the constructor chaining from the constructor selected at `new` down to the final constructor that calls the superclass and then back up.

## 34. Common Mistakes and How to Fix Them

| Misconception / Error | What Actually Happens | Correct Way of Thinking |
| --- | --- | --- |
| `this(...)` creates a new object | It delegates to a constructor on the same object | Distinguish `this(...)` from `new` |
| Each constructor body runs an instance block | A class's initializers run in one pass during object initialization | Count per class/per object, not per constructor |
| Superclass constructor runs after subclass block | The superclass completes before the subclass's instance initialization | Draw the `super(...)` chain |
| All instance fields of every class are assigned before all constructor bodies | Only object-wide default values are set early; explicit initializers run per class | Distinguish default initialization from explicit initializers |
| All field initializers run before all blocks | Within the same class they run in interleaved textual order | Read in source order |
| Static block runs on every `new` | Static blocks belong to class initialization | Count static and instance separately |
| Two variables pointing to the same object make the block run twice | Assigning a reference does not create an object | Count executed `new` expressions |
| `super()` creates a separate parent object | Initializes the superclass part of the same object | Do not add an extra object allocation |
| Constructor `Child()` calls `this(...)` and also adds `super()` | Invalid in Java 17 | A `this(...)` chain has only one endpoint that calls the superclass |
| Using `this(...)` after a print statement | Invalid Java 17 syntax | Place the explicit invocation first |
| Circular constructor chaining | Recursive constructor invocation is rejected | Choose a target constructor that calls `super(...)` |
| Superclass lacks a no-arg constructor | Implicit `super()` cannot be resolved | Call an appropriate `super(arguments)` |
| Subclass fields are initialized when parent constructor calls an overridden method | Not guaranteed; they may still hold only default values | Avoid calling overridable methods in constructors |
| Constructor body sets values before the class's own instance initializer | Instance initializers run before the target body | Centralize field initialization clearly |
| Instance block receives constructor parameters | Blocks have no parameter list | Use a constructor, body, or helper |
| Instance block throws an error but constructor body still runs | An exception cuts off normal initialization | Analyze the actual control flow |
| `return;` in a constructor prevents the block from running | The block already ran before the body | Distinguish initializers from constructor bodies |
| Having a `final field` means it must be assigned in every overload | A delegating constructor can receive the assignment result from the target constructor | Check definite assignment across the whole chain |
| Counting one object with multiple constructors as multiple instances | Constructor bodies ≠ object allocations | One normal `new` creates one object |
| Instance initializer runs “only once for the whole program” | Each new instance has its own pass | Do not confuse with static initializers |

## 35. Self-Practice Exercises with Answers

### Exercise 1 — Two Constructors Chained via `this(...)`

```java
class A {
    { System.out.println("block"); }

    A() {
        this(1);
        System.out.println("zero");
    }

    A(int value) {
        System.out.println("int");
    }
}
```

**Question:** What does `new A()` print?

**Answer:**

```text
block
int
zero
```

The instance block runs once, and the two constructor bodies run in unwinding order.

### Exercise 2 — Calling an Overload Directly

Given class `A` from Exercise 1, what does `new A(5)` print?

**Answer:**

```text
block
int
```

The `A()` body does not run because the call selects `A(int)` directly.

### Exercise 3 — Two Independent Objects

```java
new A();
new A(2);
```

Given class `A` from Exercise 1, how many times is `block` printed?

**Answer:** **2 times**, because two instances are created. Constructor overloading/chaining does not multiply the number of block executions per instance.

### Exercise 4 — Superclass and Subclass

```java
class P {
    { System.out.println("P block"); }
    P() { System.out.println("P ctor"); }
}

class C extends P {
    { System.out.println("C block"); }
    C() { System.out.println("C ctor"); }
}
```

**Question:** What does `new C()` print?

**Answer:**

```text
P block
P ctor
C block
C ctor
```

Initializes the superclass part before the subclass part.

### Exercise 5 — Two Blocks in the Same Class

```java
class A {
    { System.out.println("one"); }
    { System.out.println("two"); }
    A() { this(1); }
    A(int value) { System.out.println("ctor"); }
}
```

**Answer:** `new A()` prints:

```text
one
two
ctor
```

Each separate block runs in one pass, even though two constructors are in the chain.

### Exercise 6 — Interleaved Fields and Blocks

```java
class A {
    int x = log("field x");
    { log("block"); }
    int y = log("field y");

    int log(String text) {
        System.out.println(text);
        return 1;
    }
}
```

**Answer:** `new A()` with a valid default constructor gives the order:

```text
field x
block
field y
```

Blocks and initializers are interleaved in source order.

### Exercise 7 — Static vs Instance

```java
class A {
    static { System.out.println("static"); }
    { System.out.println("instance"); }
    A() { System.out.println("ctor"); }
}
```

If `new A(); new A();` is executed in a single run, with the class not previously initialized, then:

**Answer:**

```text
static
instance
ctor
instance
ctor
```

The static block does not repeat for each additional new instance.

### Exercise 8 — Parent Class Calls an Overridable Method

```java
class P {
    P() { show(); }
    void show() { System.out.println("P"); }
}

class C extends P {
    int x = 10;

    @Override
    void show() {
        System.out.println(x);
    }
}
```

**Question:** What value does `new C()` print?

**Answer:** `0`. Dynamic dispatch from `P`'s constructor to `C.show()` occurs before the subclass initializer `x = 10`.

### Exercise 9 — Circular Constructor Chain

```java
class A {
    A() { this(1); }
    A(int x) { this(); }
}
```

**Answer:** Does not compile due to recursive constructor invocation. There is no endpoint to perform valid superclass initialization.

### Exercise 10 — Parent Constructor Without No-Arg

```java
class P {
    P(int value) { }
}

class C extends P {
    C() {
        // Needs super(1);
    }
}
```

**Answer:** Without calling `super(1)`, the compiler inserts `super()` and encounters an error because `P` does not have a no-arg constructor. Fix it to:

```java
class C extends P {
    C() {
        super(1);
    }
}
```

### Exercise 11 — Exception in the Superclass

```java
class P {
    P() { throw new IllegalStateException(); }
}

class C extends P {
    { System.out.println("C block"); }
}
```

**Answer:** When `new C()` runs, `C block` **is not printed**; the superclass constructor throws an exception before control reaches C's initializer part.

### Exercise 12 — Can `this(...)` Assign a Final Field Twice?

```java
class A {
    final int value;

    A() {
        this(1);
        // value = 2;
    }

    A(int v) {
        value = v;
    }
}
```

**Answer:** `A()` is valid while the line `value = 2` remains commented out. If uncommented, reassigning the final field is invalid. `this(1)` does not re-run instance initializers, and delegates assigning the final field to the target constructor.

### Exercise 13 — Counting Across Three Classes

`A` has one instance block, `B extends A` has two blocks, and `C extends B` has one block. `new C()` runs three times, with no exceptions and no additional nested objects created.

**Answer:** Each object triggers `1 + 2 + 1 = 4` block executions; three objects trigger a total of **12**. The number of constructor overloads does not affect the result.

### Exercise 14 — Creating Another Object in an Initializer

```java
class Helper {
    { System.out.println("Helper block"); }
}

class Owner {
    Helper helper = new Helper();
    { System.out.println("Owner block"); }
}
```

**Answer:** `new Owner()` prints:

```text
Helper block
Owner block
```

These two lines belong to **two objects of two different classes**: one Helper created inside the field initializer and one Owner.

## 36. Checklist When Analyzing Initialization Order

1. **Identify the `new` calls that actually execute.** How many objects are created directly or nested inside an initializer?
2. **Check class initialization:** have static blocks/fields already been initialized? Are there any superclass static initializers?
3. **Draw the superclass chain** from the created class up to `Object`.
4. **Identify the constructor overload selected** by `new ClassName(arguments)`.
5. **Follow the `this(...)` chain** until reaching a constructor that does not continue calling `this(...)`.
6. **Follow the `super(...)` chain** up to the superclass, including any implicit `super()` call.
7. **On the way back**, run each class's instance field initializers/blocks **in one pass**, in source order within that class, before the target constructor body.
8. **Run the constructor bodies in unwinding order** of `this(...)` within each class.
9. **Do not count `super(...)` as a new object allocation.**
10. **Do not multiply the instance block count** by the number of constructor overloads/bodies.
11. **Do not lump all subclass initializers before the parent constructor**; the superclass is initialized first.
12. **Distinguish default field values from explicit field initializers**; a parent constructor can see the subclass's defaults.
13. **Check for overridable methods called in a constructor**, especially when they read subclass fields.
14. **If there are multiple blocks in the same class**, each block runs once; count the total block executions accurately.
15. **If there are multiple `new` instances**, apply the rule repeatedly for each new object.
16. **If there is an exception**, stop the trace at the throw point; do not print bodies/blocks that were not executed.
17. **If there are final fields**, check definite assignment across the `this(...)` chain.
18. **Check Java 17 syntax**: explicit `this(...)`/`super(...)` must be at the beginning of the constructor body.
19. **Compare stdout line by line** rather than just vaguely noting “parent before child”.
20. **In practical design**, keep constructors/initializers readable, avoid side effects, and avoid exposing the object before construction is complete.

## Things to Remember

- **`this(...)` chains constructors within the same class and on the same object**, without creating an extra object and without re-running instance initializers.
- **`super(...)` initializes the superclass part of the same object**; it does not call `new Superclass(...)` to create another parent object.
- **Instance field initializers and instance initialization blocks** of a class run **in one pass for that class's instance part during each normal object creation**, not once per constructor body.
- **Within the same class**, field initializers and instance blocks run interleaved **in declaration order**, before the target constructor body.
- **Between classes**, the superclass is initialized before the subclass; the parent constructor completes before the child's instance initialization.
- **Static initialization** belongs to the class, typically executing once according to class initialization semantics; instance initialization runs again for each new object.
- **A chain with three constructor bodies** can still have only **one** instance block execution for that class when creating one object.
- **Dynamic dispatch from a parent constructor** can invoke a subclass override before subclass field initializers run; that is why an overridable method should not be called from a constructor.
- **An exception can cut the chain short**: only the initializers/bodies that were actually reached will run.
- When solving exercises, **count objects, draw the `this/super` chain, walk from superclass down to subclass, and separate static from instance**. This approach gives more reliable results than guessing from the number of constructors in the code.
