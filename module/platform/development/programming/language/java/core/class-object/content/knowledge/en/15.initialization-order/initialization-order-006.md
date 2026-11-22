# Initialization Order of Superclass, Instance Fields, Initializer Blocks, and Constructor Body in Java

## 1. Goal: Reading the Order When Writing `new Child()`

An object in Java is not created by simply "running the constructor body from the first line to the last line" as many beginners imagine. When one class inherits from another, the process also involves:

- **Class initialization**: static field initializers and static initializer blocks need to run according to the rules before the class is actively used.
- **Default values of instance fields**: memory for the object is allocated, and the fields start at the default values of their types.
- **Superclass constructor**: instance initialization of the superclass takes place before the subclass's instance initializers run.
- **Subclass instance field initializers**: expressions that assign initial values to instance fields.
- **Subclass instance initialization blocks**: `{ ... }` blocks directly inside the class body, without the `static` keyword.
- **Subclass constructor body**: the statements after `super(...)` or `this(...)` in the selected constructor.

Example:

```java
class Parent {
    Parent() {
        System.out.println("Parent constructor");
    }
}

class Child extends Parent {
    int age = 10;

    {
        System.out.println("Child instance block");
    }

    Child() {
        System.out.println("Child constructor");
    }
}
```

When running `new Child()`, the order is not "Child constructor first because Child is called". Before the body of `Child()` runs, the `Parent` constructor and the initializers of `Child` must execute according to the rules.

**Key takeaway to grasp right away:** In the normal case, **the superclass constructor completes → the subclass's field initializers and instance blocks run in source order → the subclass constructor body runs**. If there are multiple levels of inheritance, this rule applies repeatedly along the constructor chain.

Exceptions and details such as `this(...)`, `super(...)` arguments, static initialization, calls to overridden methods from a superclass constructor, and exceptions during object creation will be explained in turn.

## 2. Distinguishing Two Processes: Class Initialization and Object Initialization

You cannot predict the output if you mix up *class initialization* with *instance initialization*.

| Component | Belongs to | When does it run? |
| --- | --- | --- |
| `static int count = init();` | Class | During class initialization, once for each runtime class that is successfully initialized |
| `static { ... }` | Class | During class initialization, in source order |
| `int id = initId();` | Each object | Every time the corresponding instance is initialized |
| `{ ... }` (without `static`) | Each object | Every time an instance is initialized, in source order together with instance field initializers |
| `Parent(...)` constructor | Superclass subobject | In the constructor chain when creating a subclass instance |
| `Child(...)` constructor body | Subclass | After superclass construction and Child's instance initializers in a valid invocation chain |

A class may already have been initialized earlier due to calling a static method, reading a non-constant static field, or certain other operations. Therefore, at the time of `new Child()`, **there may be no static initializers left to run**.

In an example run in a fresh process, we usually see static initialization before the first instance initialization. However, **static blocks do not run again** on each object creation.

### Diagram for the Case Child extends Parent

```text
First active use of Child:
    Class initialization of Parent (if needed)
        └── static field initializers / static blocks of Parent
    Class initialization of Child (if needed)
        └── static field initializers / static blocks of Child

Then create a Child object:
    Instance fields start at default values
        ↓
    Invoke Parent's constructor chain
        ├── instance field initializers of Parent
        ├── instance initialization blocks of Parent
        └── Parent constructor body
        ↓
    Instance field initializers and blocks of Child
       (in order of appearance in source)
        ↓
    Child constructor body
        ↓
    Object can be used after the constructor returns successfully
```

This diagram illustrates a **simple constructor chain** without `this(...)` forwarding across multiple overloads, without exceptions, and without side effects from argument evaluation. The following sections will add those details.

## 3. First Program: Printing the Order from Superclass to Subclass

Create the file **`ParentChildOrderDemo.java`**:

```java
class Parent {
    static {
        System.out.println("P.static");
    }

    private int parentValue = print("P.field", 10);

    {
        System.out.println("P.instanceBlock");
    }

    Parent() {
        System.out.println("P.constructor");
    }

    static int print(String label, int value) {
        System.out.println(label);
        return value;
    }
}

class Child extends Parent {
    static {
        System.out.println("C.static");
    }

    private int childValue = print("C.field", 20);

    {
        System.out.println("C.instanceBlock");
    }

    Child() {
        System.out.println("C.constructor");
    }
}

public class ParentChildOrderDemo {
    public static void main(String[] args) {
        System.out.println("main.before");
        new Child();
        System.out.println("main.after");
    }
}
```

Compile and run on **JDK 17+**:

```bash
javac ParentChildOrderDemo.java
java ParentChildOrderDemo
```

**Standard output:**

```text
main.before
P.static
C.static
P.field
P.instanceBlock
P.constructor
C.field
C.instanceBlock
C.constructor
main.after
```

**Reading the output stage by stage:**

1. `main.before` appears before creating Child.
2. The statement `new Child()` triggers initialization of `Parent` and then `Child` if neither has been initialized yet: printing `P.static`, `C.static`.
3. During instance construction, the `Parent` field initializer prints `P.field`.
4. The Parent instance block prints `P.instanceBlock`.
5. The constructor body of Parent prints `P.constructor`.
6. After the Parent part completes, Child's field initializer prints `C.field`.
7. The Child instance block prints `C.instanceBlock`.
8. The constructor body of Child prints `C.constructor`.
9. When `new Child()` completes, main prints `main.after`.

`parentValue` and `childValue` are kept to illustrate instance fields; Java allows them to go unused in the rest of the example. The call to `print` does not alter the order, because the helper only prints the message and returns the value.

## 4. Why Does the Superclass Constructor Run First?

A `Child` object also carries the state and behavior inherited from `Parent`. Before Child's constructor body runs, Java must perform the appropriate initialization process for the superclass.

For a constructor that does not write an initial invocation in Java 17:

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

The compiler treats the `Child()` constructor as having an implicit call to **`super()`** at the beginning:

```java
Child() {
    super(); // Illustrates the implicitly inserted call.
    System.out.println("Child()");
}
```

This is a **semantically equivalent illustrative version**, not a declaration of two constructors with the same signature in the same class.

If the parent constructor can be invoked without arguments, omitting `super()` is usually valid. If the superclass does not have an accessible no-argument constructor, the subclass must call an appropriate constructor with `super(args)`; otherwise, compilation fails.

**Note:** A constructor is not an ordinary method; `super(...)` calls **a constructor** belonging to the superclass, not `super.someMethod(...)`.

## 5. Java 17 Rule: `this(...)` or `super(...)` Is the First Constructor Call

In Java 17, an explicit constructor invocation `this(...)` or `super(...)`, if present, must be the **first statement in the constructor body** according to the applicable syntax.

Valid example:

```java
class Parent {
    Parent(int id) {
        System.out.println("Parent: " + id);
    }
}

class Child extends Parent {
    Child(int id) {
        super(id);
        System.out.println("Child: " + id);
    }
}
```

Intentionally invalid snippet:

```java
// Child(int id) {
//     System.out.println("before super");
//     super(id); // Invalid in Java 17: not the first statement.
// }
```

**Do not place instance statements before `super(...)`** in Java 17 examples. Some newer Java versions have language changes related to *flexible constructor bodies*, so when learning by version, you must check the exact version. This document uses **Java 17** to avoid mixing up version rules.

Inside a constructor, you can choose **one** initial explicit constructor invocation:

- `super(args)` to call a constructor of the direct superclass.
- `this(args)` to forward to another constructor **in the same class**.

You cannot call both `this(...)` and `super(...)` as two calls standing side by side in the same constructor body. With `this(...)`, the target constructor will continue the chain to the superclass according to the rules.

## 6. Instance Field Initializers and Instance Blocks Run in Source Order

Within the **same class**, instance field initializers and instance initialization blocks are processed in their **order of appearance in the source**.

File **`InstanceSourceOrderDemo.java`**:

```java
public class InstanceSourceOrderDemo {
    private int first = mark("field-first", 1);

    {
        System.out.println("block-A");
    }

    private int second = mark("field-second", 2);

    {
        System.out.println("block-B");
    }

    InstanceSourceOrderDemo() {
        System.out.println("constructor");
    }

    private static int mark(String label, int value) {
        System.out.println(label);
        return value;
    }

    public static void main(String[] args) {
        new InstanceSourceOrderDemo();
    }
}
```

```bash
javac InstanceSourceOrderDemo.java
java InstanceSourceOrderDemo
```

```text
field-first
block-A
field-second
block-B
constructor
```

Even though `mark` is a static method declared at the end of the file, initializers can call it. Where the method body is defined does not cause it to automatically run earlier.

**How to remember:** Java does not "run all field initializers first and then all instance blocks". They are **interleaved in textual/source order** within a class.

### Changing the Declaration Order Can Change the Output

If you move the block `{ System.out.println("block-B"); }` before the declaration of `second`, the output also changes accordingly. This matters when an initializer reads state that was just assigned or creates interdependent resources.

## 7. Default Values Come Before Values Assigned by Initializers

When an object is allocated, instance fields start with **default values**:

| Field type | Default value |
| --- | --- |
| `byte`, `short`, `int`, `long` | `0` |
| `float`, `double` | `0.0` |
| `char` | The character `'\u0000'` |
| `boolean` | `false` |
| Reference type | `null` |

These values appear **before** instance field initializers and the constructor body assign custom values. The compiler/JVM ensures that fields have an appropriate default state semantically, rather than allowing code to use uninitialized local variables.

**Difference:** local variables are **not automatically default-initialized** like instance fields. A local `int n;` must be definitely assigned before it is read.

### Do Not Assume That Declaring a Field with an Initializer Means the Field Always Has That Value at Every Stage

Example:

```java
class Child {
    int score = 10;
}
```

After the constructor chain and field initializer complete normally, `score` is 10. However, **while the superclass constructor is running**, the subclass's initializer part **has not executed yet**. If a subclass method is called too early from the superclass constructor, it may observe `score=0`.

This is an important pitfall that will be illustrated with a program in a later section.

## 8. Superclass Calling an Overridden Method: The Subclass May Still Have Default State

One situation to flag when mapping out the initialization order is when a superclass constructor calls an overridable method:

```java
class Parent {
    Parent() { show(); }
    void show() { }
}
class Child extends Parent {
    private String text = "ready";
    @Override void show() { System.out.println(text); }
}
```

This **snippet** shows: in `new Child()`, `Parent()` runs before the Child field initializer; `show()` is dispatched to Child's override, so it can print `null`. Only after the superclass constructor does the initializer setting `text="ready"` and the Child constructor body run. Calling the method directly or through an intermediate helper does not automatically make the subclass ready earlier.

When working out the initialization order, mark this as a **callback running in the middle of the constructor chain**, and do not write "all subclass fields have been initialized" at the moment the superclass constructor starts. For an in-depth analysis of risks, exceptions, `final`/`private` dispatch, and fixes using lifecycle/factory patterns, see the dedicated article on calling overridden methods when an object is not yet fully initialized. In this article, the goal is to recognize **the position of the call** in the `super(...)` → field initializer → instance block → constructor body diagram.

## 9. Superclass and Subclass Having a Field with the Same Name: There Is No "Field Overriding"

Instance fields do not override like methods. A subclass can declare a field with the same name as one in the superclass, but this is **field hiding**, not dynamic dispatch.

File **`FieldHidingInitializationDemo.java`**:

```java
class Parent {
    int count = init("Parent.count", 1);

    Parent() {
        System.out.println("Parent constructor: " + count);
    }

    static int init(String label, int value) {
        System.out.println(label);
        return value;
    }
}

class Child extends Parent {
    int count = init("Child.count", 2);

    Child() {
        System.out.println("Child constructor: " + count);
        System.out.println("Parent field: " + super.count);
    }
}

public class FieldHidingInitializationDemo {
    public static void main(String[] args) {
        Child child = new Child();
        Parent parentRef = child;

        System.out.println("child.count=" + child.count);
        System.out.println("parentRef.count=" + parentRef.count);
    }
}
```

```bash
javac FieldHidingInitializationDemo.java
java FieldHidingInitializationDemo
```

```text
Parent.count
Parent constructor: 1
Child.count
Child constructor: 2
Parent field: 1
child.count=2
parentRef.count=1
```

Both fields `Parent.count` and `Child.count` exist separately inside the Child object. The Parent initializer assigns the Parent field, and then the Child initializer assigns the Child field. On ordinary field access, the field is selected based on the **type/expression at compile time**, unlike virtual method dispatch.

Therefore, in the final output:

- `child.count` has static type Child and reads the Child field, which is 2.
- `parentRef.count` has static type Parent and reads the Parent field, which is 1.

**Do not confuse field hiding with "the Child initializer modifies the Parent field"**. The two fields have the same name but are different declarations.

## 10. Constructor with `super(args)`: Arguments Are Evaluated Before the Superclass Constructor Body Runs

An important detail: if the Child constructor has an explicit `super(expression)`, Java must **evaluate the appropriate argument expressions** before the Parent constructor call executes its body.

File **`SuperArgumentOrderDemo.java`**:

```java
class Parent {
    Parent(int value) {
        System.out.println("Parent constructor: " + value);
    }
}

class Child extends Parent {
    private int amount = log("Child.field", 20);

    {
        System.out.println("Child.block");
    }

    Child() {
        super(log("super.argument", 7));
        System.out.println("Child.constructor");
    }

    private static int log(String text, int result) {
        System.out.println(text);
        return result;
    }
}

public class SuperArgumentOrderDemo {
    public static void main(String[] args) {
        new Child();
    }
}
```

```bash
javac SuperArgumentOrderDemo.java
java SuperArgumentOrderDemo
```

```text
super.argument
Parent constructor: 7
Child.field
Child.block
Child.constructor
```

Reading the order:

1. The expression `log("super.argument", 7)` is evaluated to produce the argument passed into `Parent(int)`.
2. Next, the body of `Parent(int)` runs.
3. Once the superclass constructor has completed normally, the Child field initializer and Child instance block run in source order.
4. Finally, the Child constructor body runs.

**Do not rigidly interpret this as "any statement in Parent always runs before every operation appearing in the Child constructor"**. Expressions that supply arguments to `super(...)` are an important part of the evaluation order.

In Java 17, do not use `this` or instance members of Child in disallowed positions of a constructor invocation. Use valid static helpers/arguments such as `log(...)` in the example above.

## 11. Passing Parameters to the Superclass Constructor Does Not Change Instance Field Initialization Order

Consider:

```java
class Person {
    private final String name;

    Person(String name) {
        this.name = name;
        System.out.println("Person: " + name);
    }
}

class Employee extends Person {
    private int level = initLevel();

    Employee(String name, int level) {
        super(name);
        this.level = level;
        System.out.println("Employee: " + this.level);
    }

    private int initLevel() {
        System.out.println("Employee.field initialized");
        return 1;
    }
}
```

These are **valid class declarations**, without `main`.

If we create `new Employee("An", 3)`:

1. The Person constructor assigns `name` and then prints.
2. The instance initializer of the field `Employee.level` runs, temporarily setting `level=1`.
3. The Employee constructor body runs, assigns `level=3`, and then prints.

This order leads to the fact that a field with an initializer **can be reassigned by the constructor**. This is valid when the field is non-final; however, you should avoid expensive initialization in a field initializer if the constructor always immediately replaces it with another value.

For a `final` field, you must ensure that the assignment obeys the definite assignment rules and is not written again after already being assigned by an initializer.

## 12. `this(...)`: Multiple Constructors in the Same Class, Yet Instance Initializers Run Only Once

When one constructor forwards to another constructor via `this(...)`, **not every constructor body causes all instance field initializers to run again**.

File **`ThisConstructorChainDemo.java`**:

```java
class Parent {
    Parent() {
        System.out.println("Parent()");
    }
}

class Child extends Parent {
    private int value = initializeValue();

    {
        System.out.println("Child.block");
    }

    Child() {
        this(5);
        System.out.println("Child()");
    }

    Child(int number) {
        super();
        this.value = number;
        System.out.println("Child(int): " + number);
    }

    private static int initializeValue() {
        System.out.println("Child.field");
        return 1;
    }
}

public class ThisConstructorChainDemo {
    public static void main(String[] args) {
        Child child = new Child();
    }
}
```

```bash
javac ThisConstructorChainDemo.java
java ThisConstructorChainDemo
```

```text
Parent()
Child.field
Child.block
Child(int): 5
Child()
```

Mechanism:

1. `new Child()` selects the no-argument constructor.
2. This constructor starts with `this(5)`, so it forwards to `Child(int)`.
3. `Child(int)` calls `super()`; the Parent constructor runs.
4. Child's instance field initializer and instance block run **once**.
5. The body of `Child(int)` assigns the field and prints `Child(int): 5`.
6. Returning after `this(5)`, the remaining body of `Child()` prints `Child()`.

There are two **constructor bodies** of Child in the invocation chain, but only **one Child object** is being created; Child's instance initializers **are not run twice**.

### Constructor Chaining Cannot Form a Cycle

Intentionally invalid example:

```java
// class Broken {
//     Broken() { this(1); }
//     Broken(int x) { this(); }
// }
```

The two constructors call each other endlessly in the `this(...)` graph, so the compiler rejects the **recursive constructor invocation**. Java does not allow creating a constructor delegation cycle like this.

## 13. The Constructor Overload Is Selected by the Call, Not by Declaration Order

A class with multiple overloaded constructors:

```java
class Order {
    Order() {
        this("UNKNOWN");
    }

    Order(String code) {
        System.out.println("Order: " + code);
    }
}
```

This is a valid declaration snippet. Calling `new Order()` goes through both `Order()` and `Order(String)` because of `this(...)`. Calling `new Order("A1")` goes directly into `Order(String)`.

The declaration order of the two constructors in the source **does not change constructor overload resolution**. The types and number of arguments determine the selected constructor signature according to Java rules.

Similarly, the order of field initializers does not depend on **which constructor is selected**: they run for each instance initialized normally, after superclass construction and before the appropriate constructor body, except for paths that failed earlier.

## 14. Multiple Inheritance Levels: Grandparent → Parent → Child

With the chain `Grandparent → Parent → Child`, the rule runs level by level:

- Class initialization (if not yet performed): from the required superclass down to the subclass.
- Instance construction: each superclass level completes its constructor chain and its instance initializers before moving to the child level.
- The subclass constructor body comes after the subclass's own initializers.

File **`ThreeLevelInitializationDemo.java`**:

```java
class Grandparent {
    int a = print("G.field", 1);

    {
        System.out.println("G.block");
    }

    Grandparent() {
        System.out.println("G.constructor");
    }

    static int print(String text, int value) {
        System.out.println(text);
        return value;
    }
}

class Parent extends Grandparent {
    int b = print("P.field", 2);

    {
        System.out.println("P.block");
    }

    Parent() {
        System.out.println("P.constructor");
    }
}

class Child extends Parent {
    int c = print("C.field", 3);

    {
        System.out.println("C.block");
    }

    Child() {
        System.out.println("C.constructor");
    }
}

public class ThreeLevelInitializationDemo {
    public static void main(String[] args) {
        new Child();
    }
}
```

```bash
javac ThreeLevelInitializationDemo.java
java ThreeLevelInitializationDemo
```

```text
G.field
G.block
G.constructor
P.field
P.block
P.constructor
C.field
C.block
C.constructor
```

Static blocks are not declared in the example in order to focus on the **instance sequence**. If static blocks are added in uninitialized classes, they will be processed according to the rule of **class initialization before instance initialization**.

**General diagram:**

```text
new Child()
   ├── Grandparent instance fields / blocks
   ├── Grandparent constructor body
   ├── Parent instance fields / blocks
   ├── Parent constructor body
   ├── Child instance fields / blocks
   └── Child constructor body
```

The word "Grandparent" here is a class named by the example, not a Java keyword. Java always has `Object` as the ultimate root class when the superclass chain applies; `Object` also participates in the constructor chain, though it has no output in the example.

## 15. Order When Creating Two Objects Consecutively

Static initialization of a class normally occurs successfully only once for that runtime class, whereas instance construction is performed **every time an object is created**.

File **`TwoObjectsOrderDemo.java`**:

```java
class Device {
    static {
        System.out.println("Device.static");
    }

    private int serial = initialize();

    {
        System.out.println("Device.block");
    }

    Device() {
        System.out.println("Device.constructor");
    }

    private static int initialize() {
        System.out.println("Device.field");
        return 1;
    }
}

public class TwoObjectsOrderDemo {
    public static void main(String[] args) {
        System.out.println("first");
        new Device();

        System.out.println("second");
        new Device();
    }
}
```

```bash
javac TwoObjectsOrderDemo.java
java TwoObjectsOrderDemo
```

```text
first
Device.static
Device.field
Device.block
Device.constructor
second
Device.field
Device.block
Device.constructor
```

**Why is the output like this?**

- `Device.static` is printed only on the first initialization.
- `Device.field`, `Device.block`, and `Device.constructor` are printed for each Device object.
- The name `serial` is an instance field; the two Device objects have separate fields, even though both use the initializer `initialize()`.

You should not see two `new` calls and think the static block will run twice; they belong to two different initialization levels.

## 16. Static Field Initializers and Static Blocks: In Their Own Source Order

Within a class, static field initializers and static blocks run in their order of appearance in the source **when the class is initialized**. They do not wait for instance construction.

File **`StaticAndInstanceSeparationDemo.java`**:

```java
class Sample {
    static int config = log("S.staticField", 10);

    static {
        System.out.println("S.staticBlock");
    }

    int value = log("S.instanceField", 20);

    {
        System.out.println("S.instanceBlock");
    }

    Sample() {
        System.out.println("S.constructor");
    }

    static int log(String label, int number) {
        System.out.println(label);
        return number;
    }
}

public class StaticAndInstanceSeparationDemo {
    public static void main(String[] args) {
        System.out.println("before class use");
        System.out.println("config=" + Sample.config);
        System.out.println("before object");
        new Sample();
    }
}
```

```bash
javac StaticAndInstanceSeparationDemo.java
java StaticAndInstanceSeparationDemo
```

```text
before class use
S.staticField
S.staticBlock
config=10
before object
S.instanceField
S.instanceBlock
S.constructor
```

Reading `Sample.config` is an active use of a non-constant static field, which triggers Sample class initialization. When `new Sample()` appears afterward, Sample has already initialized successfully, so the program only needs to enter the **instance creation** steps.

**Do not confuse** `static int config = ...` with `int value = ...`; they belong to two different processes even though both are field initializers.

## 17. A Field Without an Initializer Still Has a Default Value

If we declare:

```java
class Product {
    private int count;
    private boolean ready;
    private String note;
}
```

When creating `new Product()`, the fields `count`, `ready`, and `note` receive default values `0`, `false`, and `null`. There is no requirement to write an initializer for every field.

A constructor or method can change them later. However, do not confuse having a default value with a **valid business-domain state**. If `note` is not allowed to be null, the constructor should validate/assign it before the object is published.

## 18. A Constructor Call Can Fail Before the Subclass's Instance Initializers Run

If the superclass constructor throws an exception, creation of the subclass object does not complete normally. The subclass's instance initializers **never get their turn to run**, except for side effects that already occurred while evaluating arguments or along another execution path permitted before that point.

File **`SuperclassFailureDemo.java`**:

```java
class Parent {
    Parent() {
        System.out.println("Parent.constructor");
        throw new IllegalStateException("parent failed");
    }
}

class Child extends Parent {
    private int value = printValue();

    {
        System.out.println("Child.block");
    }

    Child() {
        System.out.println("Child.constructor");
    }

    static int printValue() {
        System.out.println("Child.field");
        return 1;
    }
}

public class SuperclassFailureDemo {
    public static void main(String[] args) {
        try {
            new Child();
        } catch (IllegalStateException ex) {
            System.out.println("caught: " + ex.getMessage());
        }
    }
}
```

```bash
javac SuperclassFailureDemo.java
java SuperclassFailureDemo
```

```text
Parent.constructor
caught: parent failed
```

There is no `Child.field`, `Child.block`, or `Child.constructor` in the output: the Parent constructor throws an error before those steps run.

**Distinction:** class initialization of Child (if it has static blocks) may still have already occurred before instance construction. This example has no static blocks, so the output only reflects the **instance constructor chain**.

## 19. Exception in an Instance Field Initializer or Instance Block

If an instance initializer throws an exception, the initializers **after it** and the constructor body of that class **do not run**, unless the exception is handled inside the initializer and does not escape.

File **`InstanceInitializerFailureDemo.java`**:

```java
class Parent {
    Parent() {
        System.out.println("Parent.constructor");
    }
}

class Child extends Parent {
    private int first = log("Child.first", 1);

    {
        System.out.println("Child.block");
        if (shouldFail()) {
            throw new IllegalStateException("block failed");
        }
    }

    private int second = log("Child.second", 2);

    Child() {
        System.out.println("Child.constructor");
    }

    static boolean shouldFail() {
        return true;
    }

    static int log(String text, int value) {
        System.out.println(text);
        return value;
    }
}

public class InstanceInitializerFailureDemo {
    public static void main(String[] args) {
        try {
            new Child();
        } catch (IllegalStateException ex) {
            System.out.println("caught: " + ex.getMessage());
        }
    }
}
```

```bash
javac InstanceInitializerFailureDemo.java
java InstanceInitializerFailureDemo
```

```text
Parent.constructor
Child.first
Child.block
caught: block failed
```

**Explanation:** The initializer block uses `shouldFail()` to decide at runtime. The compiler cannot prove that the exception-throwing branch is always executed, so the instance initializer is able to complete normally according to Java rules. With `shouldFail()` returning `true` in this program, at runtime, the block prints `Child.block` and then throws `IllegalStateException`; the program catches the exception in `main` and prints the exact stdout shown above. The initialization of `Child.second` and the body of the `Child()` constructor do not run.

## 20. When Are Instance Initialization Blocks Appropriate?

Instance blocks are blocks placed directly inside the class body, with no name and without `static`:

```java
class Example {
    {
        System.out.println("instance block");
    }
}
```

They are useful when shared initialization logic must run before the bodies of constructors regardless of which constructor overload is selected, or when a local/anonymous class has certain design constraints.

However, for typical application code, clearer alternatives are usually:

- **Field initializer** for simple values: `private final List<String> items = new ArrayList<>();`.
- **Constructor** for validation and argument-dependent initialization.
- **Private helper method** called by the constructor when the logic is long and has a distinct meaning.
- **Static factory** when you need control over construction, subtypes, or complex validation.

An instance block is not "mandatory" in a class. Do not try to move all initialization logic into blocks just to avoid writing a constructor.

### Example of a Block That Can Be Shared Across Multiple Overloads

```java
class Session {
    private final java.util.List<String> events =
            new java.util.ArrayList<>();

    {
        events.add("created");
    }

    Session() {
    }

    Session(String name) {
        events.add("name=" + name);
    }
}
```

This is a valid declaration. Each Session object is initialized with a new list, and then the block adds `created`. The constructor accepting `name` adds data after the block. For this case, adding `created` could also be placed directly in a helper/constructor, so the choice depends on readability.

## 21. The Order Between an Initializer and the Constructor Body Can Affect Invariants

Suppose:

```java
class User {
    private String name = "anonymous";

    User(String name) {
        this.name = name;
    }
}
```

When creating `new User("An")`, the field initializer assigns `"anonymous"`, and then the constructor body assigns `"An"`. If the constructor does not validate `name`, the caller can pass null and violate the field's intended validity.

A clearer design:

```java
class User {
    private final String name;

    User(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name required");
        }
        this.name = name;
    }
}
```

Here, the field `name` is a blank final instance field, assigned exactly once by the constructor after validation. You do not need to assign a default value just so "the class has a field initializer".

**Lesson:** identifying the **final data source** of each field (field declaration or constructor arguments) helps avoid unnecessary double assignment and reduces the risk of side effects.

## 22. `final` Instance Field: Must Complete Valid Initialization Before the Constructor Returns

With a blank final field:

```java
class Ticket {
    private final String code;

    Ticket(String code) {
        this.code = code;
    }
}
```

Java requires a final instance field to be definitely assigned according to the rules before the constructor completes normally. You cannot rewrite `code` from an instance method like a normal field.

Invalid:

```java
// class Ticket {
//     private final String code = "A";
//     Ticket() {
//         code = "B"; // Error: final field has already been assigned.
//     }
// }
```

**Relation to order:** if a final field already has an initializer at its declaration, it is assigned during the field initialization step before the constructor body; it cannot be reassigned inside the constructor body.

### Being a final Field Does Not Mean It Has Its Final Value When the Superclass Constructor Runs

Even when Child declares `private final int count = 42;`, when the superclass constructor calls an overridable method of Child, that initializer has not run yet. During that premature call, the override may observe the default value `0` under the relevant rules. Final does not allow bypassing the construction order.

**Do not make a superclass constructor depend on subclass fields**, including final fields.

## 23. Anonymous Classes and Instance Initialization Blocks

An anonymous class does not have a constructor declaration bearing a class name that you can write yourself, but it can contain an instance initializer block.

Example:

File **`AnonymousInitializationDemo.java`**:

```java
interface Action {
    void run();
}

public class AnonymousInitializationDemo {
    public static void main(String[] args) {
        Action action = new Action() {
            private final String label = initialize();

            {
                System.out.println("anonymous.block");
            }

            private String initialize() {
                System.out.println("anonymous.field");
                return "ready";
            }

            @Override
            public void run() {
                System.out.println("run=" + label);
            }
        };

        action.run();
    }
}
```

```bash
javac AnonymousInitializationDemo.java
java AnonymousInitializationDemo
```

```text
anonymous.field
anonymous.block
run=ready
```

In an anonymous class:

- It is a separate class created from an expression.
- Its field initializers and instance blocks run when the anonymous object is created.
- There is no constructor source declaration with a class name, so an initialization block is one way to write setup logic for an anonymous class.
- The method `run()` only runs when invoked via `action.run()`, not when creating the object, unless a constructor/initializer calls it itself.

**Note:** prefer lambdas over anonymous classes for functional interfaces when no specific object state/initializer is needed. The two syntaxes have different class/`this` semantics, so a lambda should not be viewed as a "shorthand anonymous class".

## 24. Default Behavior When a Class Declares No Constructor

If a class has no constructor declarations, the compiler can generate an appropriate **default constructor**, with a call to the superclass no-arg constructor according to the rules.

File **`DefaultConstructorOrderDemo.java`**:

```java
class Parent {
    Parent() {
        System.out.println("Parent()");
    }
}

class Child extends Parent {
    private int number = print();

    {
        System.out.println("Child.block");
    }

    static int print() {
        System.out.println("Child.field");
        return 5;
    }
}

public class DefaultConstructorOrderDemo {
    public static void main(String[] args) {
        new Child();
    }
}
```

```bash
javac DefaultConstructorOrderDemo.java
java DefaultConstructorOrderDemo
```

```text
Parent()
Child.field
Child.block
```

`Child` does not write an explicit constructor. The compiler provides a default constructor; the Parent no-arg constructor runs, and then the Child field initializer and block run. There is no user-written constructor body, so there is no line printed from the Child constructor body.

If Parent only has `Parent(int)` without an accessible no-arg constructor, Child's default constructor cannot validly call `super()` on its own; the compiler will report an error, and you need to declare a Child constructor with `super(argument)`.

## 25. When Has Static Initialization of Parent/Child Already Completed Earlier?

Not every `new Child()` produces output containing static blocks. Consider:

File **`AlreadyInitializedDemo.java`**:

```java
class Parent {
    static {
        System.out.println("Parent.static");
    }

    Parent() {
        System.out.println("Parent.constructor");
    }

    static void touch() {
        System.out.println("Parent.touch");
    }
}

class Child extends Parent {
    static {
        System.out.println("Child.static");
    }

    Child() {
        System.out.println("Child.constructor");
    }
}

public class AlreadyInitializedDemo {
    public static void main(String[] args) {
        Parent.touch();
        System.out.println("before child");
        new Child();
        System.out.println("again");
        new Child();
    }
}
```

```bash
javac AlreadyInitializedDemo.java
java AlreadyInitializedDemo
```

```text
Parent.static
Parent.touch
before child
Child.static
Parent.constructor
Child.constructor
again
Parent.constructor
Child.constructor
```

Analysis:

- `Parent.touch()` triggers Parent initialization and then runs the method.
- The first `new Child()` initializes Child; Parent is already initialized, so `Parent.static` is not repeated. After that, the Parent/Child constructors run.
- The second `new Child()` only runs the constructors; both classes are already initialized.

**Remember:** to predict whether a static block will run, you must know **whether the class was already initialized before the current operation**. You cannot just look at a `new` at the end of a method and assume the static blocks will definitely appear right there.

## 26. A Field Initializer Containing a Method Call Can Cause Side Effects

A field initializer does not have to be just a literal:

```java
class ConnectionSettings {
    private final String host = readHost();

    private static String readHost() {
        System.out.println("read settings");
        return "localhost";
    }
}
```

Every time a `ConnectionSettings` instance is created, the initializer `readHost()` runs (unless the constructor chain throws an error early) and can have side effects. This is a consequence of **field initializers running on every instance**, not an automatically cached optimization.

If an initializer opens a file, makes a network call, or registers a callback, it can fail **before the constructor body** and make the logic difficult to control. You should choose the placement of initialization based on:

- Who needs to know about the error?
- Are there any dependencies that need to be passed through constructor arguments?
- Is there a validation condition needed before performing the side effect?
- Does a resource need to be closed/rolled back when a later step fails?
- Does the implementation need to be swapped in tests?

For operations that can fail, a factory or service with a clear error contract can be easier to maintain than a complex initializer hidden inside a field declaration.

## 27. Each Instance Gets Its Own Objects from Field Initializers, Unless static Is Intentionally Used

If a field initializer contains `new ArrayList<>()`:

```java
class Bucket {
    final java.util.List<String> items =
            new java.util.ArrayList<>();
}
```

Each `new Bucket()` normally creates a new list object for that instance. Two Bucket objects do not automatically share `items` just because the field declaration is in the same place in the source.

Conversely:

```java
class Bucket {
    static final java.util.List<String> ITEMS =
            new java.util.ArrayList<>();
}
```

This is a static field referencing a shared list at the runtime-class level, and it is not automatically recreated when `new Bucket()` is called again.

**Note:** `final` on a reference field does not automatically make the list immutable, whether the field is instance final or static final.

## 28. Evaluation Timing of `new Child(argumentExpression)`

To predict output in Java, you must consider **evaluation of the caller's expressions** before the constructor runs.

Example:

```java
Child child = new Child(makeValue());
```

If `makeValue()` has a side effect, it can print a message **before parts of the constructor bodies**. However, class initialization rules, evaluation order of receiver/arguments, and side effects occurring in class dependencies also affect the actual output.

You should not state an absolute rule that "the first line of Parent's static block is always the first output line whenever the source contains `new Child(...)`", because the caller may print or execute other expressions beforehand.

In the examples for this topic, clearly mark the output caused by:

1. Statements in `main`.
2. Class initializers.
3. Argument expressions for `new`/`super`/`this`.
4. The superclass constructor chain.
5. Field initializers/instance blocks.
6. The subclass constructor body.
7. Statements after `new` completes.

Execution order in Java is determined by specific rules, not merely by whether a snippet is located in the parent or child class.

## 29. Interfaces Have No Instance Constructor

A class can `implements Interface`, but **an interface does not have a constructor that runs in the instance construction chain**.

Example:

```java
interface Named {
    String name();
}

class Person implements Named {
    private final String name;

    Person(String name) {
        this.name = name;
    }

    @Override
    public String name() {
        return name;
    }
}
```

When creating Person, the constructor chain is based on the **class superclass hierarchy** (ultimately up to `Object`), and does not run a "Named constructor" because interfaces have no instance constructors.

**Static fields of an interface** and certain initialization rules involving superinterfaces/default methods can affect **class initialization**, but that is a separate topic from the **instance constructor chain**.

**Do not treat `implements` as an `extends` edge that carries a constructor.**

## 30. No Objects Are Created When Creating Only a Reference Array

Creating an array:

```java
Child[] children = new Child[3];
```

only creates an **array object** containing three reference slots defaulting to `null`; it **does not call three Child constructors** and does not run Child's instance field initializers for each slot.

File **`ArrayVsObjectDemo.java`**:

```java
class Child {
    int value = log();

    Child() {
        System.out.println("Child.constructor");
    }

    static int log() {
        System.out.println("Child.field");
        return 1;
    }
}

public class ArrayVsObjectDemo {
    public static void main(String[] args) {
        System.out.println("make array");
        Child[] items = new Child[2];

        System.out.println(items[0] == null);
        items[0] = new Child();
        System.out.println(items[1] == null);
    }
}
```

```bash
javac ArrayVsObjectDemo.java
java ArrayVsObjectDemo
```

```text
make array
true
Child.field
Child.constructor
true
```

Only `new Child()` for slot 0 begins construction of a Child instance. `items[1]` remains null, and no second object has been created yet.

## 31. Distinguishing Constructors, Same-Named Methods, and Initialization Blocks

A constructor declaration has the **same name as the class** and **no return type**:

```java
class Sample {
    Sample() {
        System.out.println("constructor");
    }
}
```

If you write:

```java
class Sample {
    void Sample() {
        System.out.println("ordinary method");
    }
}
```

then `void Sample()` is an **ordinary method**, not a constructor. The compiler can provide a default constructor because the class has no constructor declaration yet.

An instance initialization block is:

```java
class Sample {
    {
        System.out.println("instance block");
    }
}
```

A static block is:

```java
class Sample {
    static {
        System.out.println("static block");
    }
}
```

The four `Sample` declarations in this section are **independent illustrations**, not placed simultaneously with the same name in a single source set. They run at very different times. Correct syntactic classification is the first step before predicting order.

## 32. Application Pattern: Initializing an Immutable Object via Constructor Parameters

A practical case: a class has a superclass checking a common ID, and the subclass adds its own parameters.

File **`ValidatedObjectDemo.java`**:

```java
class Entity {
    private final String id;

    Entity(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id required");
        }
        this.id = id;
    }

    String id() {
        return id;
    }
}

final class Product extends Entity {
    private final int price;

    Product(String id, int price) {
        super(id);
        if (price < 0) {
            throw new IllegalArgumentException("negative price");
        }
        this.price = price;
    }

    int price() {
        return price;
    }
}

public class ValidatedObjectDemo {
    public static void main(String[] args) {
        Product product = new Product("P-1", 250);

        System.out.println(product.id());
        System.out.println(product.price());

        try {
            new Product("", 50);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid id");
        }
    }
}
```

```bash
javac ValidatedObjectDemo.java
java ValidatedObjectDemo
```

```text
P-1
250
invalid id
```

This design:

- The `Entity` constructor protects the ID invariant before Product initialization completes.
- The `Product` constructor checks the price after the superclass constructor returns normally.
- `Product.price` is a blank final field, assigned once in the appropriate constructor.
- The Product class is `final` to represent a concrete value/entity type that does not support subclassing in the example.
- If `id` is empty, the superclass constructor throws an exception, and creating Product does not return an instance successfully.

**An important limitation:** If validation of Product.price must be performed **before any side effects of the Entity constructor**, design an appropriate factory/pre-validation or separation of responsibilities. In Java 17, you cannot place arbitrary statements before `super(id)` inside the same constructor body.

## 33. A Design to Avoid: Letting `this` Escape During a Constructor

Even before the subclass constructor finishes, code can accidentally **publish the `this` reference** to somewhere else.

Dangerous example:

```java
class Base {
    static java.util.List<Base> registry =
            new java.util.ArrayList<>();

    Base() {
        registry.add(this);
    }
}

class Child extends Base {
    private String ready = "yes";
}
```

If `Base()` stores `this` into the registry, the object is registered **before** the initializer `Child.ready="yes"` runs. Other code accessing the registry right at that moment can observe an incomplete object, or even worse in a multithreaded environment.

Safer design approach:

- Avoid callbacks, registration, or starting threads in a constructor when there is a risk of using an incomplete object.
- Complete construction and validation first, and then let an external service/factory register the object.
- Do not call overridable methods from a superclass constructor.
- If the object needs to be published across multiple threads, you also need **safe publication** conforming to the Java Memory Model.

**Encapsulation cannot rely solely on `private` fields** if the constructor itself exposes `this` to external code before invariants are established.

## 34. Common Misconceptions About Initialization Order

| Misconception | What Is True |
| --- | --- |
| "The subclass constructor runs first because `new Child` is called" | The superclass constructor chain is executed before the Child constructor body |
| "All code in class Parent runs before all code in Child" | You must separate static vs. instance, argument evaluation, and active uses |
| "The static initializer runs on every `new`" | Successful class initialization does not repeat on every instance |
| "Child's field initializer runs before the Parent constructor" | No; Parent initialization precedes Child's instance initializers |
| "All field initializers always finish running before blocks" | Field initializers and instance blocks interleave in source order |
| "An instance block only runs if there is no constructor" | It runs during appropriate instance construction, regardless of overloaded constructors |
| "`this(...)` makes field initializers run again" | Delegation does not repeat instance initializers for the same object |
| "`super(...)` can be placed at the end of a constructor in Java 17" | Explicit constructor invocation must come first in Java 17 |
| "Omitting `super()` skips the Parent constructor" | The compiler inserts an implicit superclass constructor invocation if valid |
| "A subclass can always call the parent's no-arg constructor" | A no-arg constructor may be missing/inaccessible; a valid constructor must be chosen |
| "When the superclass calls an override, Child's fields are already assigned" | The override may see default values when Child is not yet initialized |
| "A `final` field in Child definitely has its final value inside the Parent constructor" | No, the instance initialization order still applies |
| "Two fields with the same name in Parent/Child are one field" | Field hiding creates distinct declarations |
| "An exception in the Parent constructor still lets the Child block run" | If the parent constructor does not complete, Child's initializers never get their turn |
| "Array `new Child[3]` creates three Child objects" | It only creates an array; slots default to null |
| "`static` and instance blocks are the same" | They differ in timing and number of executions |
| "A method with the class name and return type void is a constructor" | That is a method, not a constructor |
| "A class using `implements` calls the interface's constructor" | An interface has no instance constructor |
| "Every method called in a constructor is safe" | An overridable method call may observe unready subclass state |
| "Changing the declaration order of constructors changes field initialization order" | No; the source order of fields/blocks determines it |
| "Not using a field initializer means the JVM assigns no value" | Fields start at default values |
| "A `static final` field and an instance `final` field share the same lifecycle" | A static field is tied to class initialization; an instance field is tied to each object |

## 35. Comprehensive Practice: Predicting Output Before Running

Create **`FullInitializationTraceDemo.java`**:

```java
class A {
    static {
        System.out.println("A.S");
    }

    int x = emit("A.F", 1);

    {
        System.out.println("A.B");
    }

    A(int n) {
        System.out.println("A.C=" + n);
    }

    static int emit(String label, int result) {
        System.out.println(label);
        return result;
    }
}

class B extends A {
    static {
        System.out.println("B.S");
    }

    int y = emit("B.F", 2);

    {
        System.out.println("B.B");
    }

    B() {
        this(5);
        System.out.println("B.C0");
    }

    B(int n) {
        super(emit("ARG", n));
        System.out.println("B.C1=" + n);
    }
}

public class FullInitializationTraceDemo {
    public static void main(String[] args) {
        System.out.println("START");
        new B();
        System.out.println("AGAIN");
        new B(9);
    }
}
```

```bash
javac FullInitializationTraceDemo.java
java FullInitializationTraceDemo
```

**Exact output:**

```text
START
A.S
B.S
ARG
A.F
A.B
A.C=5
B.F
B.B
B.C1=5
B.C0
AGAIN
ARG
A.F
A.B
A.C=9
B.F
B.B
B.C1=9
```

### Analysis of the First Pass

1. Main prints `START`.
2. `new B()` triggers initialization of A and then B: `A.S`, `B.S`.
3. `B()` calls `this(5)`.
4. `B(int)` prepares the call `super(emit("ARG", n))`: `ARG` is printed, and the result 5 is passed to A.
5. A's field initializer `x` prints `A.F`, A's instance block prints `A.B`, and A's constructor body prints `A.C=5`.
6. B's field initializer `y` prints `B.F`, and B's instance block prints `B.B`.
7. The B(int) constructor body prints `B.C1=5`.
8. Returning to the B() constructor body, it prints `B.C0`.

### Analysis of the Second Pass

1. Main prints `AGAIN`.
2. A and B are **already initialized**, so static blocks do not print again.
3. `new B(9)` calls B(int) directly, evaluating the `super(...)` argument → `ARG`.
4. A's fields/block/constructor print `A.F`, `A.B`, `A.C=9`.
5. B's fields/block/constructor print `B.F`, `B.B`, `B.C1=9`.
6. There is no `B.C0` because execution does not go through the `B()` overload.

**Core skill:** clearly separate **class initialization (once)**, **constructor delegation**, **super arguments**, **parent instance sequence**, **child instance sequence**, and **constructor bodies**.

## 36. Quick Exercises with Answers

**Question 1.** Given `class Child extends Parent` and `new Child()`, which constructor body runs first?

**Answer:** The body of Parent's superclass constructor chain runs before the Child constructor body, though `super(...)` argument expressions may be evaluated before the Parent constructor body begins.

**Question 2.** In Child, `int a = f();` appears before `{ g(); }`. Which is called first?

**Answer:** `f()` from the field initializer runs before `g()` from the instance block, after superclass construction for Child has completed.

**Question 3.** What if the instance block is placed before the field initializer in the source?

**Answer:** The instance block runs before that field initializer, following textual order.

**Question 4.** Does a second `new Child()` run Child's static block again?

**Answer:** No, if the same runtime class has already been initialized successfully; instance initializers and constructors still run to create the new instance.

**Question 5.** Do all Child instance fields have their declared values when the Parent constructor calls an overridable Child method?

**Answer:** No. Child's initializers have not run yet, so the override may see default values.

**Question 6.** How many times does `Child() { this(1); ... }` make Child's field initializer run for a single object?

**Answer:** Once, in the appropriate constructor chain; it does not run again for each overload body.

**Question 7.** If the superclass only has `Parent(int)`, can a subclass that declares no constructor compile?

**Answer:** No, if the implicit `super()` is invalid because there is no accessible no-arg Parent constructor.

**Question 8.** Does Java 17 allow `System.out.println("x"); super();` inside a constructor?

**Answer:** No, an explicit constructor invocation must be the first statement.

**Question 9.** Are two fields with the same name in Parent and Child a method override?

**Answer:** No. Fields are hidden, each being a separate declaration; field access is based on the type/source declaration, not virtual dispatch.

**Question 10.** How many times does `new Child[2]` run the Child constructor?

**Answer:** Zero times; it only creates an array object containing two null slots.

**Question 11.** If the Parent constructor throws before returning, does the Child instance block run?

**Answer:** Not in that constructor chain; creating Child fails before reaching Child's initializers.

**Question 12.** What value does an instance field `int n;` without an initializer receive when an object is newly allocated?

**Answer:** Default `0`, which can later be modified by an initializer/constructor.

**Question 13.** Do all instance field initializers run once inside every constructor body of a `this(...)` chain?

**Answer:** No. They run once for the object, before the appropriate target constructor body after the superclass phase, without repeating in each body.

**Question 14.** Can a static class initializer be called from a constructor body by an arbitrary method name?

**Answer:** Static initialization is managed by the JVM according to active-use rules; there is no user-written `<clinit>` source method that can be called like an ordinary method.

**Question 15.** Can an instance initialization block use `this` to access the object being created?

**Answer:** Yes, in an appropriate instance context, but the object may not have completed its constructor body yet and is not yet safely published. Avoid calling code that could let `this` escape or that depends on fields that are not ready yet.

**Question 16.** What is the order between a superclass static block and a subclass static block when a subclass is normally initialized for the first time?

**Answer:** The superclass is initialized as a dependency before the subclass; static initializers within each class run in that class's source order.

**Question 17.** Does a class implementing an interface have to run an "interface constructor" when creating an object?

**Answer:** No. An interface has no instance constructor.

**Question 18.** Can constructor delegation call both `this(...)` and `super(...)` at the same time in the same constructor?

**Answer:** No. Each constructor has a single appropriate explicit constructor invocation at the beginning (or implicit `super()`); the delegation chain proceeds to the superclass through the target constructor.

## 37. Checklist for Verifying Initialization Order in Real Code

- [ ] Have you identified the class being created and the **entire superclass chain**?
- [ ] Have you distinguished static initializers from instance initializers?
- [ ] Have you determined which classes were **already initialized earlier** in the process?
- [ ] If there are static blocks, have you checked the source order within each class?
- [ ] Do the constructors use implicit `super()`, explicit `super(args)`, or `this(args)`?
- [ ] Do the `super(...)`/`this(...)` argument expressions have side effects?
- [ ] Does the called superclass constructor have the matching signature and is it accessible?
- [ ] Have you listed instance field initializers and blocks **in source order** within each class?
- [ ] Does any field initializer read a field that has not yet been assigned a custom value?
- [ ] Is there a field with the same name in superclass/subclass that could be confused with overriding?
- [ ] Does the superclass constructor call overridable methods?
- [ ] Does any constructor or initializer allow `this` to escape prematurely?
- [ ] With a `this(...)` chain, have you avoided counting instance initializers multiple times?
- [ ] If an exception occurs, have you identified which steps run and which do not?
- [ ] For `final` fields, have you checked definite assignment and ensured no repeated assignment?
- [ ] Have you separated the default values of instance fields from the values assigned by initializers?
- [ ] If only creating an array or obtaining a class literal, are you confusing it with creating an instance?
- [ ] Have you tried running a minimal example with `javac`/`java` and verified the output line by line?

---

**Final takeaway:** When creating a subclass object, Java separates **class initialization** from **instance initialization**. Class initializers of the superclass/subclass run when needed according to active-use rules and do not repeat per object. During the creation of an instance, **the superclass constructor chain is executed first**, then **the subclass's instance field initializers and instance blocks run interleaved in source order**, and finally **the subclass constructor body runs**. With `this(...)`, constructor bodies can chain together, but instance initializers do not run repeatedly for the same object. Always account for **`super(...)` argument evaluation**, **field defaults**, **exceptions**, and the risk of **calling an overridden method from a superclass constructor when subclass state is not yet ready**. Mastering these steps helps you predict stdout, handle constructor errors, and safely design inherited classes in Java.
