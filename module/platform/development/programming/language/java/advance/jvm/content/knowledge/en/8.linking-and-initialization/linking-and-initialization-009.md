# Initialization Order of Superclasses, Related Interfaces, and `static` Members in the JVM

When creating an instance of a subclass for the first time, the JVM does not immediately execute the subclass's `static` statements. It must ensure that the related types are initialized strictly according to the **rules of the Java Language Specification (JLS) and Java Virtual Machine Specification (JVMS)**. Normally, **a superclass initializes before its subclass**. However, there is an important detail that is easy to overlook: when initializing a **class**, the JVM also initializes its **direct or indirect superinterfaces that declare default methods** in a specified recursive order. Interfaces that do not declare default methods **are not automatically initialized merely because the class `implements` them**.

Within each class or interface, `static` member initializers and valid static initialization blocks are executed **in the order they appear in the source** when it is that type's turn. In addition, a `static final` that is a **compile-time constant** has its own `ConstantValue` mechanism, and reading a constant in source code usually **does not trigger initialization** of the declaring class/interface.

These rules explain surprising log ordering in plugin systems, singletons, static caches, inheritance, and code with default methods. This lesson builds an accurate model and then uses **standalone, runnable Java 17+ programs with deterministic stdout** to verify it.

## 1. Loading, linking, preparation, and initialization are not the same

The JVM manages the lifecycle of classes and interfaces according to distinct concepts:

| Activity | Purpose | Does it run the class's `static { ... }` statements? |
| --- | --- | --- |
| **Loading** | Find or create a representation of the class/interface via a class loader | **No**, not merely due to loading |
| **Verification** | Check structural and bytecode/type constraints | **No**, not merely due to verification |
| **Preparation** | Prepare static fields and default values according to JVM rules | **No**, does not run programmer-written initializer expressions |
| **Resolution** | Link symbolic references to actual classes/fields/methods | **Does not necessarily** trigger initializers of the related types |
| **Initialization** | Execute the initialization procedure, set appropriate constant values, and run `<clinit>` if present | **Yes**, at the proper point in the procedure |

Model:

```text
class bytes
    │
    ▼
Loading
    │
    ▼
Linking
    ├─ Verification
    ├─ Preparation: static fields have default values
    └─ Resolution (may occur on demand)
    │
    ▼
Initialization
    ├─ handle ConstantValue according to rules
    ├─ if it is a class: initialize superclass then qualifying superinterfaces
    ├─ run <clinit> code of the class/interface itself if present
    └─ record fully initialized state
    │
    ▼
Continue the operation that requested initialization
```

**Do not equate "already loaded" with "already ran static initializer".** A class can be loaded, verified, prepared, or have some references resolved without having undergone initialization.

### 1.1. Default values appear before initializer code

During preparation, a static field of type `int` has the default value `0`, `boolean` has `false`, and a reference has `null`. Later, when initializing the type, the initializer expressions set the values computed by the programmer.

```java
static int count = 7;
static Object cache = new Object();
```

You should not assume that `count` is already 7 and `cache` already points to a new object as soon as the class has just been loaded. Executing the `new Object()` expression is initialization behavior, not a default step in preparation.

**Exception to remember:** a `static final` field that is a compile-time constant may have a `ConstantValue` attribute. The JVMS handles constant values in a separate step of the initialization procedure, **before the superclass initialization step**. This does not mean every `static final` is assigned that way: `static final Integer BOXED = 42;`, for instance, is not a constant variable according to the JLS.

## 2. When does a class or interface actually initialize?

JLS `12.4.1 describes the situations that trigger initialization. Common cases:

1. **Creating an instance of class `C`**: `new C()` requires initializing `C` before creating the instance under the corresponding conditions.
2. **Calling a static method declared by `C`**: `C.work()` leads to initialization of the type **that declares the resolved method**, if not already initialized.
3. **Assigning a static field**: `C.value = 1` triggers initialization of the type that declares the corresponding field.
4. **Reading a static field that is not a constant variable**: `System.out.println(C.value)` triggers initialization of the type that declares the field.
5. **Certain reflection and method handle operations** may require initialization, depending on the specific API/reference kind.
6. **The program's initial class** is initialized before running its corresponding `main`.

At the JVM level, the commonly involved instructions are `new`, `getstatic`, `putstatic`, and `invokestatic`. However, to know **which type** must initialize, you must look at the **declaring class/interface of the field or method after resolution**, not just read the name written in source code.

### 2.1. Operations that are NOT enough to conclude initialization occurred

| Operation | Does it by itself force initialization of the mentioned class? |
| --- | --- |
| `C.class` | **No**, a class literal is not an active use forcing `<clinit>` to run |
| `new C[5]` | **No**, does not force initialization of component class `C` merely by creating an array |
| Declaring `C variable;` or a method signature using `C` | **No**, not merely by mentioning the type |
| `C.CONSTANT` with a constant variable per the JLS | **No**; the compiler may inline the constant |
| `Class.forName("pkg.C", false, loader)` | **Does not require** initializing `C` |
| `Class.forName("pkg.C")` | **Yes**, this common overload requires initialization (with the loader per API rules) |
| `loader.loadClass("pkg.C")` | Should not be treated as an operation that forces initializer execution |
| `obj instanceof C` | Does not by itself force initialization of `C` merely from this check |

**Note:** a class might have already been initialized earlier by another operation, or resolution/loading may occur early. The table states that an operation **does not by itself require initialization**, not a promise that the class is definitely still uninitialized across the entire process.

### 2.2. Inherited static field: the subclass name does not decide which type initializes

```java
class Parent {
    static int size = 5;
}
class Child extends Parent {}
```

With `Child.size`, the field is actually **declared by Parent**. According to static field access rules, reading `Child.size` triggers initialization of **Parent**, and **does not by itself force Child to initialize** just because the source writes the `Child` prefix. This result goes against the intuition "touching Child runs Child's static".

The same applies to a static field inherited from an interface/superinterface: you must observe where **the field is declared** after resolution.

## 3. The superclass-before-subclass rule

For a class `Sub extends Base`, when the JVM must initialize `Sub`, it ensures `Base` has been initialized before running `Sub`'s initializer expressions and static blocks. If `Base` also has an uninitialized superclass, the chain continues upward.

Simple example:

```java
class Grandparent {
    static { System.out.println("Grandparent"); }
}
class Parent extends Grandparent {
    static { System.out.println("Parent"); }
}
class Child extends Parent {
    static { System.out.println("Child"); }
}
```

If in a standalone program these classes are uninitialized and `new Child()` is executed for the first time, the expected log order is:

```text
Grandparent
Parent
Child
```

This is a **condensed example of initialization relationships**, not a program with a `main` method. Constructor and instance field initialization are a different step that occurs **after the related class initialization is complete**.

### 3.1. Not "wait until Base's constructor is called to run static"

Java object creation involves `super(...)` constructor chaining, but **static initialization** and **instance initialization** are two different processes.

```text
new Child()
  ├─ class initialization (if needed)
  │    ├─ Grandparent <clinit>
  │    ├─ Parent <clinit>
  │    └─ Child <clinit>
  └─ instance creation/initialization
       ├─ run constructor chain and instance field initializers per JLS
       └─ return reference to completed instance
```

Do not confuse `<clinit>` (class/interface initialization) with `<init>` (instance constructor). A class can initialize successfully exactly once per class identity and class loader while creating **multiple object instances** via constructors.

### 3.2. An already initialized Parent does not print again

If a previous operation has already initialized `Parent`, and then `new Child()` runs, the JVM **does not re-run** `Parent`'s static code just because the subclass is being initialized. "Super before sub" is a **state-guarantee ordering**, not a requirement that every trigger prints the entire new log chain together.

## 4. Interfaces (`interface`): class inheritance rules cannot be applied mechanically

Java supports interface inheritance and default methods. Interface initialization conditions have **two distinct cases**.

### 4.1. Initializing an interface alone does not automatically initialize its superinterfaces

Example:

```java
interface Root {
    int X = Helper.computeRoot();
}
interface Child extends Root {
    int Y = Helper.computeChild();
}
```

If code accesses **`Child.Y`** (a non-constant expression) and neither type has been initialized, this requires initializing the **Child interface**. It **does not automatically initialize Root** just because `Child extends Root`.

Conversely, `Root.X` will require initializing `Root` because `Root` declares field `X`. This is an important difference compared to the rule requiring superclass initialization when initializing a **class**.

The two snippets above are **illustrative code requiring `Helper` to be provided**, not a standalone file. A runnable example demonstrating interface rules is in section 6.

### 4.2. However, when initializing a CLASS: default-method superinterfaces have a special role

In Java 17, when class `C` is initializing, JVMS `5.5 / JLS `12.4.2 requires processing:

1. `C`'s superclass (if any) first.
2. Direct or indirect superinterfaces that **declare at least one default method** — more precisely at the JVMS level, superinterfaces declaring a **non-abstract, non-static** instance method according to the specification's condition.
3. Only then run `C`'s own initialization code.

Superinterfaces are determined by an **ordered recursive traversal**: visit each interface in the `implements` list from left to right, traversing deeply into that interface's superinterfaces in declaration order **before** returning to the current interface. Among the interfaces found, only those meeting the default-method condition above must initialize because of this rule.

```text
class Leaf extends Parent implements ChildInterface, Marker
  │
  ├─ initialize Parent first
  │
  ├─ traverse Leaf's interface hierarchy
  │    ├─ ChildInterface
  │    │     └─ RootInterface  [has default method] → init RootInterface
  │    │  ChildInterface      [has default method] → init ChildInterface
  │    └─ Marker              [no default method] → no auto-init
  │
  └─ initialize Leaf
```

**Note on wording:** an interface that only **inherits** a default method from a parent without **declaring** a default method itself does not necessarily get initialized by the "declares default methods" condition alone. When reading code deeply, you must look at methods **declared** in each interface, not just what methods it inherits.

### 4.3. Static methods in an interface are not default methods

```java
interface Utilities {
    static void run() {}
}
```

A static method in an interface **does not make that interface a default-method interface** for the auto-initialization rule of a class implementing it. A `default void run() {...}` method is the different case. Although calling `Utilities.run()` can itself trigger initialization of `Utilities`, a class merely having `implements Utilities` does not force that interface to initialize before the class.

### 4.4. A `static { ... }` block cannot be declared in an interface

Java interface fields are implicitly `public static final`, but interfaces cannot have a `static { ... }` static initializer block like classes. An interface can still perform initialization work via **the initializer expression of a non-constant field**:

```java
interface Marker {
    int FLAG = Logger.log("Marker initialized");
}
```

If a field initializer calls a method like above, the value `FLAG` **is not a compile-time constant**. Reading `Marker.FLAG` can trigger initialization and run the expression, even though there is no static block in the interface source.

## 5. Static fields and static blocks: textual order

Within a class, static variable initializers and static initializer blocks are processed **in the order they appear in code** when that class initializes. This is a sequence with side effects; changing declaration order can change stdout, data, or cause errors.

```java
class Order {
    static int first = trace("first");
    static { trace("block 1"); }
    static int second = trace("second");
    static { trace("block 2"); }
    static int trace(String value) {
        System.out.println(value);
        return 1;
    }
}
```

When `Order` is initialized for the first time, the corresponding code will print:

```text
first
block 1
second
block 2
```

This is an illustrative class snippet. The JVM does not run every method in the class in sequence: the `trace` method is only called because the initializers invoked it.

### 5.1. The compiler puts code into `<clinit>`

`javac` typically synthesizes static field initializers with runtime operations and static blocks into a class initialization method named **`<clinit>`**, with descriptor **`()V`**.

```text
source:
  static int n = compute();
  static { log(); }

bytecode logic:
  <clinit>:
    invokestatic compute:()I
    putstatic n:I
    invokestatic log:()V
    return
```

`<clinit>` is a JVM method reserved for class/interface initialization; it is **not** called directly from Java like `MyClass.<clinit>()` and is not the constructor `<init>`.

Not every class with static fields needs `<clinit>` in its class file. Classes that only have compile-time constants or no initialization code may **not contain `<clinit>`**. The JVM still maintains the initialization state of the class/interface according to the rules.

### 5.2. The "order within each class" principle, not merging parent/child sources

If `Parent` declares:

```java
static int p = initP();
static { logP(); }
```

and `Child` declares:

```java
static int c = initC();
static { logC(); }
```

then the JVM executes the order **per type**:

```text
Parent.initP → Parent.logP
Child.initC  → Child.logC
```

If Child has uninitialized default-method superinterfaces, those interfaces can **interleave between the two groups** according to the procedure in `5.5`; you cannot conclude that once Parent static finishes, Child static runs immediately.

### 5.3. Constant variables are handled specially

A **constant variable** according to the JLS is a `final` variable of primitive type or `String` initialized with a **constant expression**:

```java
static final int MAX = 10;
static final String NAME = "service";
```

References in source code can have the compiler **embed the value directly into the user's bytecode**, without using `getstatic` to read the field when folded, and thus **do not initialize the declaring type** merely by reading the constant.

Conversely:

```java
static final Integer BOXED = 10;
static final int LENGTH = new String("abc").length();
static final String TEXT = new String("ready");
```

These are not constant variables by the definition above: `Integer` is a reference wrapper; constructor/method calls are runtime expressions. Accessing these static fields in the normal way can trigger initialization of the declaring type.

**Do not equate the `final` keyword with constant-foldable.** `static final` objects and collections do not automatically become compile-time constants.

## 6. Runnable example: superclass, default-method interfaces, marker interface

Create the file **`InitHierarchyDemo.java`** on JDK 17 or higher:

```java
public class InitHierarchyDemo {
    static int trace(String message) {
        System.out.println(message);
        return 1;
    }

    interface Root {
        int VALUE = trace("Root.field");
        default void rootMethod() {}
    }

    interface Branch extends Root {
        int VALUE = trace("Branch.field");
        default void branchMethod() {}
    }

    interface Marker {
        int VALUE = trace("Marker.field");
    }

    static class Parent {
        static int parentValue = trace("Parent.field");
        static { trace("Parent.block"); }
    }

    static class Leaf extends Parent implements Branch, Marker {
        static int leafValue = trace("Leaf.field");
        static { trace("Leaf.block"); }
    }

    public static void main(String[] args) {
        System.out.println("before new");
        new Leaf();
        System.out.println("after new");
        System.out.println("markerValue=" + Marker.VALUE);
    }
}
```

Compile and run:

```bash
javac --release 17 InitHierarchyDemo.java
java InitHierarchyDemo
```

**Exact stdout:**

```text
before new
Parent.field
Parent.block
Root.field
Branch.field
Leaf.field
Leaf.block
after new
Marker.field
markerValue=1
```

### 6.1. Line-by-line explanation

1. When the program enters `main`, the outer class `InitHierarchyDemo` has already been initialized. However, the **nested types** `Parent`, `Leaf` and interfaces `Root`, `Branch`, `Marker` do not have to be initialized merely because the outer class contains their names.
2. `System.out.println("before new")` prints before creating the object.
3. `new Leaf()` requires initializing `Leaf`. The JVM checks superclass `Parent` first: the field initializer prints `Parent.field`, then the static block prints `Parent.block`.
4. `Leaf` directly `implements Branch, Marker`. Traversing interface `Branch` leads back to `Root`: both **declare default methods themselves**, so `Root` initializes then `Branch`. Their corresponding non-constant field initializers print `Root.field` and `Branch.field`.
5. `Marker` does not declare a default method. Therefore it is **not yet** required to initialize during the default-method superinterfaces step of `Leaf`.
6. After the prerequisite types, `Leaf`'s static code runs in order: field then block.
7. `after new` prints after the `Leaf` creation operation completes.
8. `Marker.VALUE` is an `int` field with an initializer via a `trace(...)` call, so it is **not a constant variable**. The access statement causes initialization of `Marker`, printing `Marker.field` before printing `markerValue=1`.

**If you remove `default void rootMethod() {}` from `Root`:** in a newly compiled class file, `Root` no longer belongs to the group that declares a default method, so a plain `new Leaf()` does not by itself require `Root` to initialize via this branch. This is a good way to verify why the interface graph and the "declares a default method" rule matter.

### 6.2. Where does the order Root then Branch come from?

The interface hierarchy traversal mechanism is **recursive before returning to the direct interface**. `Leaf` visits `Branch`, then `Root` as `Branch`'s superinterface; then returns to `Branch`, and finally goes to `Marker`.

Only qualifying interfaces are initialized. Therefore the result is `Root` then `Branch`. Even though `Marker` is in `implements`, it is still uninitialized at the time `Leaf` runs its static block.

If there are diamond-shaped multiple superinterfaces, the algorithm ensures an already completed initialization is not re-run; the same interface may be encountered via multiple branches, but its `<clinit>` code is not executed repeatedly on every traversal.

### 6.3. Why are the static fields of Root/Branch printed?

In a Java interface, `int VALUE = trace("...")` is equivalent to `public static final int VALUE`, but the expression **is not a compile-time constant**. During the interface's initialization due to default methods, the `trace` expression is called and produces a side effect. If replaced with `int VALUE = 1`, retrieving the constant value does not call `trace` and produces no log line.

## 7. Runnable example: static field order and default values

When a static initializer calls a method that reads a static field **not yet assigned by a textual initializer**, the method can observe the default value from preparation. This is a common cause of unpredictable output.

Create the file **`StaticSequenceDemo.java`**:

```java
public class StaticSequenceDemo {
    static int first = readSecond();
    static int second = 7;

    static {
        System.out.println("static block second=" + second);
    }

    static int readSecond() {
        System.out.println("observed second=" + second);
        return second + 1;
    }

    public static void main(String[] args) {
        System.out.println("first=" + first);
        System.out.println("second=" + second);
    }
}
```

Run:

```bash
javac --release 17 StaticSequenceDemo.java
java StaticSequenceDemo
```

**Stdout:**

```text
observed second=0
static block second=7
first=1
second=7
```

Progression:

1. When `StaticSequenceDemo` initializes, `first` and `second` already have the default value **0** from preparation.
2. The initializer of `first` calls `readSecond()`. At this moment `second = 7` **has not run yet**, so the method prints `observed second=0` and returns `1`. The JVM assigns `first=1`.
3. Next, the initializer expression `second=7` runs.
4. The static block prints `static block second=7`.
5. Once class initialization finishes, the launcher invokes `main`, printing `first=1` and `second=7`.

### 7.1. Why not write `static int first = second;` directly?

Due to Java source's **illegal forward reference** rule in certain contexts, the code:

```java
static int first = second;
static int second = 7;
```

may be **rejected by `javac`** because it references by simple name a static field declared later in an initializer. The runnable example called **method `readSecond()`**, and the method body reads the field — a case with different rules, so it can observe the preparation value **0**.

**Do not turn the `first = second;` example into a runnable program with expected stdout**, because it is meant to illustrate a compile error, not runtime behavior.

### 7.2. There is no "reorder by dependency" mechanism

The JVM does not read source code and automatically topologically sort static initializers. If field A depends on B below it, the author must organize dependencies/initialization explicitly. Java preserves execution order matching the source in the class body; the JVM does not guess business intent and run `second=7` before `first=readSecond()`.

## 8. Runnable example: compile-time constant, inherited field, and non-constant static

Create the file **`StaticTriggerDemo.java`**:

```java
public class StaticTriggerDemo {

    static int report(String message, int result) {
        System.out.println(message);
        return result;
    }

    static class Settings {
        static final int LIMIT = 42;
        static final String LABEL = "stable";
        static final Integer BOXED = 42;

        static {
            System.out.println("Settings initialized");
        }
    }

    static class Parent {
        static int inherited = report("Parent initialized", 7);
    }

    static class Child extends Parent {
        static int own = report("Child initialized", 9);
    }

    public static void main(String[] args) {
        System.out.println("limit=" + Settings.LIMIT);
        System.out.println("label=" + Settings.LABEL);
        System.out.println("inherited=" + Child.inherited);
        System.out.println("boxed=" + Settings.BOXED);
        System.out.println("own=" + Child.own);
    }
}
```

Commands:

```bash
javac --release 17 StaticTriggerDemo.java
java StaticTriggerDemo
```

**Exact stdout:**

```text
limit=42
label=stable
Parent initialized
inherited=7
Settings initialized
boxed=42
Child initialized
own=9
```

Explanation:

- `Settings.LIMIT` and `Settings.LABEL` are compile-time constants. The Java compiler can write the constants `42` and `"stable"` directly at the usage sites. The first two accesses do not force `Settings` to initialize, so `Settings initialized` is not seen yet.
- `Child.inherited` accesses a field **declared in `Parent`**. As a result, it requires initializing `Parent`, printing `Parent initialized`; **Child does not have to initialize yet** merely from accessing this field.
- `Settings.BOXED` has type `Integer`, not a constant variable. Reading it via `getstatic` causes `Settings` to initialize, running the static block that prints `Settings initialized`, then printing the value `42`.
- `Child.own` is a field **declared by Child**. When Child needs to initialize, Parent is already initialized so Parent does not print again; only `Child initialized` is printed.

### 8.1. What happens if `Child.inherited` is replaced with `Child.own` on the first line?

If the first access into the class hierarchy is `Child.own`, the JVM must initialize Child and therefore ensure Parent is initialized first. In that case Parent and Child print consecutively in order. However, the original example deliberately separates the two triggers to prove that **the field's declaring type** determines initialization via static field access.

### 8.2. A "compile-time constant" is decided at compile time

If a library changes `Settings.LIMIT` from 42 to 43 and only rebuilds the JAR containing `Settings` without **recompiling client code**, older clients may still use the **inlined constant value 42**. This is a **binary compatibility** consequence: changing a constant variable is not the same as changing a non-constant static field.

When designing a library API, do not use `public static final int` as a "dynamic configuration value" expecting every client to automatically update after swapping the JAR. For runtime/configuration values, expose them through a method or an appropriate access mechanism.

## 9. Static initialization order and instance initialization

A class may contain:

- Static field initializer: `static int x = compute();`.
- Static initialization block: `static { ... }`.
- Instance field initializer: `int y = computeInstance();`.
- Instance initializer block: `{ ... }`.
- Constructor: `MyClass() { ... }`.

These two groups **differ in timing**:

| Component | When does it run according to the Java model? |
| --- | --- |
| Static field initializer with runtime code | When initializing the **class**, once for that class's successful state per loader |
| Static block | When initializing the **class**, in order together with field initializers |
| Instance field initializer | When creating **each object**, in instance initialization order |
| Instance initializer block | When creating **each object**, in instance initialization order |
| Constructor body | During **each object** creation, after the appropriate superclass/instance initialization steps |

Conceptual example:

```text
first new Child()
  → initialize Parent/related interfaces/Child (if not yet)
  → instance initialization + constructor chain
second new Child()
  → no need to re-run <clinit> of types that already succeeded
  → still runs instance initialization + constructor chain for the new object
```

You must not conclude that "static always runs right before the constructor" on **every** object creation: it only needs to execute before the first active use if the type is not yet initialized.

## 10. Reentrant initialization and concurrency

The JVM must coordinate multiple threads wanting to initialize the same class/interface simultaneously. Rule `5.5` uses an **initialization lock** to ensure a class's state is handled consistently.

Conceptual states:

```text
verified/prepared, not initialized
       │
       ├─ thread A starts initialization
       │      ├─ record "initialization in progress by A"
       │      ├─ initialize qualifying superclass/interfaces
       │      └─ run <clinit>, completing successfully or failing
       │
       └─ thread B also needs the class
              → wait for A's initialization per JVM mechanism
              → proceed when class is initialized or receive error
```

- If **the same thread A** is initializing a class and during that process requests initialization of **that same class**, the JVM recognizes recursive initialization and **does not re-run `<clinit>`** from the beginning. This is why `readSecond()` in `StaticSequenceDemo` can be called while the class is initializing.
- If **thread B** needs that class, B may have to wait for A to finish.
- If initialization of the class **fails**, the class may enter an **erroneous state**; subsequent attempts do not simply re-run the static block as if nothing happened.
- Class initialization synchronization **does not** replace thread-safe synchronization for mutable static fields **after** initialization completes.

### 10.1. Do not create circular init dependencies between two classes/threads

If class A's static initializer requires B while class B's static initializer requires A, especially when **two threads** are initializing different classes, circular waiting or an initialization deadlock can occur. JVMs must uphold synchronization rules; designers should avoid complex side effects, blocking I/O, or running worker tasks inside static initializers when dependencies are unclear.

**Practice:** keep static initialization as simple/deterministic as possible; move network connections, thread pool startup, plugin registration, and complex dependency injection into explicitly controlled startup steps whenever possible.

## 11. When static initialization throws an exception

Class initialization can fail:

```java
class Broken {
    static final Object CONFIG = loadConfiguration();

    static Object loadConfiguration() {
        throw new IllegalStateException("bad config");
    }
}
```

This class snippet is **illustrative**. On the first active use of `Broken`:

1. The JVM begins initialization.
2. `<clinit>` (if present) executes the initializer expression and encounters an exception.
3. If the throwable causing initialization to fail **is not an `Error`**, the JVM applies the appropriate wrapping rule in **`ExceptionInInitializerError`** (except for details when the wrapper cannot be created).
4. The class may be recorded in an **erroneous state**.
5. Subsequent active uses may fail with **`NoClassDefFoundError`** stating that the class could not be initialized, rather than running the initializer again.

If the initializer's exception is already an `Error`, it is not necessarily wrapped into `ExceptionInInitializerError` under the same rule. Therefore, do not write monitoring that only counts `ExceptionInInitializerError` while ignoring other types of initialization failures.

### 11.1. How to handle in applications

- Read the **first cause/stack trace** to know which initializer failed.
- Inspect configuration, dependencies, file paths, environment, and code with side effects in static blocks.
- Check whether the class was initialized early by a library, reflection, or framework.
- Do not "retry" by looping `new Broken()` in the **same class loader** expecting the JVM to automatically re-run initialization.
- If dynamic recovery is required, design a service/configuration lifecycle that can retry **outside** `<clinit>`, instead of relying on class initialization.

## 12. `javap`: seeing `<clinit>` and constant folding

Using JDK 17:

```bash
# Compile all three standalone examples:
javac --release 17 InitHierarchyDemo.java
javac --release 17 StaticSequenceDemo.java
javac --release 17 StaticTriggerDemo.java

# View instructions, method/field descriptors:
javap -c -p StaticSequenceDemo
javap -c -p StaticTriggerDemo

# View nested classes, keep the $ sign inside quotes:
javap -c -p 'InitHierarchyDemo$Parent'
javap -c -p 'InitHierarchyDemo$Leaf'
javap -c -p 'InitHierarchyDemo$Root'
javap -c -p 'InitHierarchyDemo$Branch'
javap -c -p 'InitHierarchyDemo$Marker'

# Display ConstantValue and detailed information:
javap -v -p 'StaticTriggerDemo$Settings'
```

With `StaticSequenceDemo`, you will typically see:

```text
static {};
   invokestatic readSecond:()I
   putstatic first:I
   bipush 7
   putstatic second:I
   getstatic java/lang/System.out
   ...
   return
```

This is a **logical excerpt of `<clinit>`**, not exact byte-for-byte/offset output; the string-printing code of `System.out.println` also has other instructions/constant-pool operands. What to verify is that the call to `readSecond()` **comes before** the write `second=7`.

With `Settings`, note:

- `LIMIT` and `LABEL` may have **`ConstantValue` attributes**.
- `BOXED` must be assigned by runtime code in `<clinit>`.
- The static block printing `Settings initialized` is also in `<clinit>` after the `BOXED` assignment step in the example.
- In the **client `StaticTriggerDemo`**, uses of `LIMIT`/`LABEL` may only push a literal or constant onto the stack, without requiring `getstatic Settings.LIMIT`.

### 12.1. How is `-Xlog:class+init` (HotSpot) used?

On the **HotSpot JVM** with Unified Logging, you can view class initialization logs with compatible configuration, for example:

```bash
java -Xlog:class+init=info InitHierarchyDemo
```

This is a **runtime-specific diagnostic option**, not Java/JVMS syntax that every implementation must support. The log can be many lines long, including JDK classes, and the order of information varies across HotSpot builds; therefore **do not prescribe a fixed stdout for this diagnostic**.

To confirm behavior while learning, prefer the **explicit stdout from the `trace()` method** of the `InitHierarchyDemo` example.

## 13. Common mistakes

1. **"`extends` only affects method lookup, not static init order."** False. A superclass must initialize before its subclass.
2. **"Any interface a class implements initializes before that class."** False. For class initialization, the rule specifically involves superinterfaces that **declare default methods**; other interfaces do not auto-initialize merely from `implements`.
3. **"Initializing an interface always initializes its parent interface."** False. Initialization of an interface does not automatically force initialization of its superinterfaces.
4. **"A default method must be called for the interface to init."** False when class initialization requires initializing a superinterface that declares a default method, even if that method is never called.
5. **"Interface static methods are equivalent to default methods."** False. A static method is not an instance default method.
6. **"Static fields run alphabetically or by dependency."** False. Runtime initializer expressions and static blocks of the same type run in the order the code is compiled from Java source.
7. **"Every `static final` is a constant and does not trigger init."** False. Only a **constant variable** per the JLS has compile-time constant properties; `Integer` or runtime expressions are different.
8. **"Reading `Child.parentField` definitely initializes Child."** False. Reading a `static` field triggers the type that **declares the field**, which is usually Parent.
9. **"`C.class` and `new C()` both run the static block."** False. A class literal does not by itself trigger initialization; creating an instance requires class initialization.
10. **"Preparation sets `static int n = 7` to 7 immediately."** False for ordinary initializer expressions. Preparation sets default values; runtime assignment happens during initialization.
11. **"It is impossible to see the value 0 from a static field with initializer 7."** You can see 0 if an earlier initializer calls a method that reads the field before it is assigned, as in `StaticSequenceDemo`.
12. **"Constructor `<init>` and class initialization `<clinit>` are the same."** False; a constructor is the per-object creation procedure.
13. **"Every time an object is created, the class static block runs again."** False if the class has already initialized successfully.
14. **"`<clinit>` always exists in every class."** False. A class containing only compile-time constants may have no initialization method code.
15. **"A static initializer that fails the first time will retry infinitely when the class is used again."** False. Initialization failure leads to an erroneous state per class loader.
16. **"Same class name across the JVM means only a single init."** Not entirely: a class's identity is also tied to its **defining class loader**; different loaders can define different classes with the same binary name.
17. **"Just replacing the JAR containing a static final constant makes the client use the new value."** Not necessarily, because the client may have inlined the compile-time constant.

## 14. Self-check (with answers)

**Question 1.** `class C extends B` with `B` uninitialized. Before running `C`'s static block, what must happen?

**Answer:** `B` and `B`'s uninitialized superclass chain must initialize according to the rules; there may also be related default-method superinterfaces before running `C`'s static body.

**Question 2.** Interface `I` has field `int A = compute()` but declares no default methods. Does `new C()` with `class C implements I` force `I.A`'s initializer to run?

**Answer:** **No**, not merely because `C implements I`. When an active use reads `I.A`, `I` can be initialized; `compute()` will run then.

**Question 3.** `interface B extends A`. If only a non-constant static field declared by `B` is accessed, does `A` necessarily initialize?

**Answer:** **No**. Initializing an interface does not automatically initialize its superinterfaces. If `B`'s initializer expression itself calls into `A`, that is a separate trigger.

**Question 4.** Are `static final int N = 5` and `static final Integer M = 5` the same regarding initialization triggers?

**Answer:** No. `N` is a constant variable (compile-time constant) if it meets the JLS conditions; `M` is a reference of type `Integer`, not a constant variable, and reading it via `getstatic` can trigger initialization.

**Question 5.** Why does `StaticSequenceDemo` print `observed second=0` before `second=7`?

**Answer:** `second` already has the default value 0 after preparation, but the initializer expression `second=7` appears **after** `first`'s initializer. `readSecond()` reads it before the line assigning 7 runs.

**Question 6.** Why does `InitHierarchyDemo` print `Root.field` and `Branch.field` before `Leaf.field` but does not print `Marker.field` right away?

**Answer:** `Root` and `Branch` declare default methods, so they are initialized according to the appropriate traversal when class `Leaf` initializes. `Marker` does not declare default methods; it only initializes later when the source accesses the non-constant `Marker.VALUE`.

**Question 7.** `static int p` is declared in Parent but accessed via `Child.p`. Which type must initialize because of that access?

**Answer:** Parent, because it is the type that **declares the field**. Referencing the name Child in source does not by itself force Child to initialize.

**Question 8.** If class initialization throws an unhandled `IllegalStateException`, what is the outermost error usually seen the first time? And on subsequent times?

**Answer:** The first time is usually **`ExceptionInInitializerError`** wrapping the non-Error exception; the class transitions to an erroneous state. Subsequent uses of the same class/loader usually encounter **`NoClassDefFoundError`**, without re-running the initialization body.

**Question 9.** Does the operation `new SomeClass[2]` by itself require initializing `SomeClass`?

**Answer:** No. This creates an array holding references; the component class does not automatically have to initialize merely due to array allocation.

**Question 10.** If a class has already been initialized in thread A, and thread B calls a static method afterward, does `<clinit>` run again?

**Answer:** No. B uses the class's already-initialized state under JVM synchronization, without re-running the static body.

## 15. Summary

```text
Trigger requires initializing class C?
      │
      ▼
Is C initialized? ───── Yes ───► continue using C
      │ No
      ▼
handle initialization lock/state of C
      │
      ▼
ConstantValue fields of C per JVMS rules
      │
      ▼
If C is a CLASS:
  superclass SC not initialized → initialize SC
  superinterfaces declaring default methods (recursive order) → initialize
      │
      ▼
run <clinit> of C if present
  - static field initializers (runtime)
  - static initializer blocks
  - textual order of C
      │
      ▼
mark successfully initialized
      │
      ▼
continue operation new/getstatic/putstatic/invokestatic...
```

**Core takeaway:** Initialization order is not "everything with the word `static` runs top-to-bottom across the entire inheritance tree". The JVM performs initialization **per class/interface**, with **superclass before subclass**, related **default-method superinterfaces** in recursive order, and then that class's own initializer code. Within one type, static runtime initializers run **in source order**, while constant variables follow their own rules. Distinguishing **declaring type**, **compile-time constant**, and **class vs interface initialization** is the key to predicting output and avoiding initialization bugs.

### Standard References

- [JLS Java SE 17 — 12.4.1 When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1).
- [JLS Java SE 17 — 12.4.2 Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2).
- [JVMS Java SE 17 — 5.5 Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5).
- [JVMS Java SE 17 — 5.4.2 Preparation](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.2).
- [JVMS Java SE 17 — 2.9.2 Class Initialization Methods](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.9.2).
- [JVMS Java SE 17 — 4.7.2 ConstantValue Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.2).
- [JLS Java SE 17 — 8.3.2.1 Static Field Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.2.1).
- [JLS Java SE 17 — 9.3.1 Interface Field Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.3.1).
- [JDK 17 `javap` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html).
