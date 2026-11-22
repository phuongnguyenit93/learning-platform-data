# Interface Initialization and the Impact of Default Methods in Java

In Java, **interfaces also have an initialization phase**, even though an instance cannot be created directly with `new Interface()`. A common point of confusion is that interface initialization rules differ from class rules, and a **default method** can cause an interface to be initialized when the JVM initializes a class that implements it, **even when the program has not yet called that default method**.

According to the *Java Language Specification (JLS) §12.4.1*:

- Initializing a **class** requires initializing any uninitialized superclasses, as well as initializing any applicable **superinterfaces that declare at least one default method** in the inheritance hierarchy.
- Initializing an **interface** by itself **does not automatically initialize its superinterfaces**.
- An interface can be initialized due to accessing a `static` field that is not a *constant variable*, invoking a `static` method declared by it, or performing a reflective operation that requires initialization.

Three things must be kept distinct: the JVM having **loaded** the interface definition, having **linked** the interface, and having **initialized** the interface. Only the initialization phase runs the assignment logic for the interface's computed `static` fields.

## 1. What Does It Mean for an Interface to Be Initialized?

With classes, we are familiar with `static` field initializers and `static { ... }`. **Interfaces do not allow declaring `static` initializer blocks**, but fields declared in an interface are `public static final` by default, and the field initialization expressions can execute code when the interface is initialized.

```java
interface Feature {
    int FIXED_LIMIT = 10;
    int RUNTIME_LIMIT = calculate();

    static int calculate() {
        System.out.println("Feature initialized");
        return 20;
    }

    static void printInfo() {
        System.out.println("Feature.printInfo()");
    }
}
```

This is an **illustrative snippet**, not a file with `main`. Both fields implicitly carry `public static final`, yet they differ in an important way:

- `FIXED_LIMIT = 10` is a **constant variable**: of primitive/String type, `final`, and initialized with a *constant expression*. The compiler can inline `10` into the code at the usage site, so merely reading `Feature.FIXED_LIMIT` **does not require initializing `Feature`**.
- `RUNTIME_LIMIT = calculate()` is **not** a constant variable, even though it is also `static final`. Reading `Feature.RUNTIME_LIMIT` directly when the interface is not yet initialized causes the JVM to initialize the interface, call `calculate()` once, and then receive `20`.
- `Feature.printInfo()` is a `static` method call declared by `Feature`; if `Feature` is not yet initialized, this call also triggers initialization.

Fields in an interface are initialized **in the order they are declared in the source code**, in accordance with Java's initialization rules. You must not treat every `static final` field as a value precomputed at compile time.

### Four Commonly Confused States

| Event | Meaning for the `Feature` interface |
|---|---|
| JVM loads/creates the type | Has a runtime representation `Class<Feature>` and an appropriate loader; field initializers have not necessarily run yet |
| JVM links the type | Verifies and prepares; resolution may be done on demand; does not mean evaluating `calculate()` |
| JVM initializes the interface | Runs the initialization of interface variables (such as `RUNTIME_LIMIT = calculate()`), if any |
| Creating an implementing object | Creates an instance of a **class** that implements `Feature`; a direct `new Feature()` does not exist |

An interface is initialized successfully at most once **per runtime type definition** (per defining class loader); multiple objects of an implementing class do not cause its field initializers to run again.

## 2. Interface Initialization Triggers

Common cases:

| Operation | Must interface T be initialized solely because of this operation? | Reason |
|---|---|---|
| `T.class` | No | A class literal obtains the type representation, not an active use |
| `Class.forName(name, false, loader)` | Not required | Looks up/loads and links the type with `initialize=false` |
| `Class.forName(name)` | Yes, if not yet initialized | This overload requires initializing the found type |
| `T.CONST` where the field is a constant variable | No | A compile-time constant value can be inlined |
| `T.RUNTIME_FIELD` where it is a `static` field that is not a constant variable, declared by T | Yes | Accessing a non-constant field is an active use |
| `T.staticMethod()`, method declared by T | Yes | Calling a `static` method is an active use |
| `class C implements T { ... }` (type declaration only) | No | The `implements` relationship alone does not force initialization |
| Initializing class `C implements T`, where T **does not declare a default method** | Not solely because of `implements` | The JVM does not force initializing every implemented interface |
| Initializing class `C implements T`, where T **declares a default method** | Yes, if not yet initialized | Initialization rule for superinterfaces that have default methods |
| Calling an instance default method on an object of `C` | T has already been initialized if T belongs to the required group before C is initialized | Initialization of C already occurred before creating the object to call the method |

The table describes **mandatory requirements** according to Java; an interface may already have been initialized for another reason before the operation takes place. Reflection and method handles also have their own specific triggers defined by the API/VM.

**In particular:** you cannot declare a `static` method in an interface and expect an implementing interface to "inherit" that method like a default method. An interface's `static` method is called through the name of the interface that declares the method itself.

## 3. Why Do Default Methods Change the Rules?

A default method (Java 8+) is an **instance method with a default body** declared in an interface:

```java
interface Greeting {
    int INIT = logInitialization();

    static int logInitialization() {
        System.out.println("Greeting initialized");
        return 1;
    }

    default String greet() {
        return "Hello";
    }
}
```

`Greeting` does not need its own instance to exist. A class can implement `Greeting` and use or override `greet()`.

Given:

```java
class Greeter implements Greeting {
    static {
        System.out.println("Greeter initialized");
    }
}
```

When the JVM **initializes `Greeter`**, it must ensure `Greeting` is also initialized because `Greeting` declares a **default method**. According to the JLS, this happens **even if `Greeter`'s constructor does not call `greet()` and even if `Greeter` overrides `greet()`**.

The deciding factor lies in **declaring a default method in a superinterface**, not in how many times the program has executed the default method's body. Calling the default method afterward is simply executing the method on a valid instance.

### How Default Methods Differ from Static Methods, Abstract Methods, and Private Interface Methods

| Method in interface | Example | Does it make the interface a superinterface that must be initialized when an implementing class is initialized? |
|---|---|---|
| **Default instance method** | `default void run() { }` | **Yes** |
| Abstract instance method | `void run();` | **Not solely because of this method** |
| Static method | `static void help() { }` | **Not solely because it exists**; calling the method directly is a different trigger |
| Private helper method | `private void helper() { }` or `private static void helper() { }` | **Not solely because of this helper** |

An interface that has abstract, static, and default methods still belongs to the group that must be initialized when an implementing class is initialized because it **declares a default method**. Without a default method, there is no such requirement solely from the `implements` relationship.

**Bytecode warning:** The Java compiler can generate *synthetic default methods* in certain cases. When analyzing actual bytecode, the JVM rules consider methods declared in the runtime type definition, not only the `default` lines that learners directly see in Java source.

## 4. Three Inheritance Relationships You Must Distinguish

### 4.1. A Class Implements an Interface with Only Abstract Methods

```java
interface AbstractOnly {
    int CHECK = init();

    static int init() {
        System.out.println("AbstractOnly initialized");
        return 1;
    }

    void run();
}

class Implementation implements AbstractOnly {
    @Override
    public void run() { }
}
```

If the program only creates `new Implementation()`, the JVM is **not required** to initialize `AbstractOnly` solely because of the implements relationship. An interface definition may already have been loaded/linked for type checking without running the `CHECK` initializer.

However, accessing `AbstractOnly.CHECK` will force initialization of that interface because `CHECK` is not a compile-time constant.

### 4.2. A Class Implements an Interface with a Default Method

```java
interface WithDefault {
    int CHECK = init();

    static int init() {
        System.out.println("WithDefault initialized");
        return 1;
    }

    default void run() { }
}

class DefaultImplementation implements WithDefault {
    static {
        System.out.println("DefaultImplementation initialized");
    }
}
```

When `new DefaultImplementation()` is the first active use and the types are not yet initialized, the required order will include:

1. Initialize the superclass of `DefaultImplementation` if needed.
2. Initialize the superinterface **`WithDefault`** because it declares a default method.
3. Run `DefaultImplementation`'s own initializers.
4. Create/initialize the instance.

Therefore, `WithDefault initialized` appears before `DefaultImplementation initialized`. The JVM does not have to wait for `run()` to be called before initializing `WithDefault`.

### 4.3. An Interface Extends an Interface with a Default Method

```java
interface Parent {
    int VALUE = trace();

    static int trace() {
        System.out.println("Parent initialized");
        return 1;
    }

    default void ping() { }
}

interface Child extends Parent {
    int CHILD_VALUE = childTrace();

    static int childTrace() {
        System.out.println("Child initialized");
        return 2;
    }
}
```

With the code above:

- **Reading `Child.CHILD_VALUE`** forces initialization of `Child` (the field is declared in Child). Initializing `Child` **does not automatically initialize `Parent`**, even though Parent declares a default method.
- **Reading `Child.VALUE`** syntactically uses the name Child, yet the `VALUE` field is actually **declared by Parent**. This access forces initialization of **Parent**, with no reason to automatically initialize Child.
- **Initializing a concrete class `C implements Child`**: the JVM inspects the superinterfaces in C's inheritance hierarchy. Because **Parent declares a default method**, Parent must be initialized (if not already) before C is initialized. `Child` is *not automatically* initialized due to implements if it does not declare its own default method and there is no other trigger.

A common point of confusion: **initializing the interface Child** is different from **initializing a class that implements Child**. The latter considers superinterfaces that have default methods; the former does not automatically propagate initialization up to all parent interfaces.

## 5. Deep Inheritance Hierarchies: Which Interfaces Run Their Initializers?

Suppose we have the following relationship:

```text
interface Root              declares default method
    |
    v
interface Mid               only abstract / static methods
    |
    v
interface Leaf              only constants / abstract methods
    ^
    |
class Concrete              implements Leaf
```

When `Concrete` is initialized, **`Root`** belongs to the group of superinterfaces that declare a default method. If `Mid` and `Leaf` do not declare any default methods and have no other triggers, they are **not required** to be initialized solely because `Concrete implements Leaf`.

Thus, thinking "only directly implemented interfaces matter" is also wrong: the condition is evaluated across the **superinterface hierarchy**, including indirect ancestors that have default methods.

### Observed Order When Multiple Branches Exist

The JVM has an initialization algorithm involving superclasses and superinterfaces containing default methods; it guarantees that the necessary types are initialized before the class itself completes initialization. The detailed rules for traversing the hierarchy and checking already-initialized states are in **JVM Specification §5.5**.

Therefore, you should not assume a fixed log order for **multiple independent branches** merely from a diagram that does not fully reflect declaration order and the JVM algorithm. What is guaranteed in a simple scenario is:

```text
new Concrete()
    |
    +--> initialize superclass if not yet initialized
    |
    +--> initialize superinterfaces with default methods
    |    per JVM rules, if not yet initialized
    |
    +--> initialize Concrete
    |
    +--> call Concrete constructor
```

**Not** all loaded interfaces have to be initialized, nor does the initializer of the same interface definition run repeatedly each time an object is created.

## 6. Java 17+ Experiment: Observing All Three Cases

Create a file named **`InterfaceInitializationDemo.java`** with the entire program below. The example uses nested interfaces and nested static classes so it can run in a single file; the `mark` method prints a message whenever a computed initializer is executed.

```java
public class InterfaceInitializationDemo {
    static int mark(String name) {
        System.out.println("init " + name);
        return 1;
    }

    interface AbstractOnly {
        int VALUE = mark("AbstractOnly");
        void work();
    }

    interface Defaulted {
        int VALUE = mark("Defaulted");

        default void work() {
            System.out.println("Defaulted.work");
        }
    }

    interface Parent {
        int VALUE = mark("Parent");

        default void work() {
            System.out.println("Parent.work");
        }
    }

    interface Leaf extends Parent {
        int VALUE = mark("Leaf");
    }

    interface Config {
        int CONST = 10;
        int NON_CONST = mark("Config");

        static void ping() {
            System.out.println("Config.ping");
        }
    }

    static class AbstractImpl implements AbstractOnly {
        static {
            System.out.println("init AbstractImpl");
        }

        @Override
        public void work() { }
    }

    static class DefaultImpl implements Defaulted {
        static {
            System.out.println("init DefaultImpl");
        }
    }

    static class LeafImpl implements Leaf {
        static {
            System.out.println("init LeafImpl");
        }
    }

    public static void main(String[] args) {
        System.out.println("1) literal: " + Leaf.class.getSimpleName());
        System.out.println("2) Leaf.VALUE: " + Leaf.VALUE);
        System.out.println("3) constant: " + Config.CONST);

        System.out.println("4) construct AbstractImpl");
        new AbstractImpl();

        System.out.println("5) construct DefaultImpl");
        new DefaultImpl().work();

        System.out.println("6) construct LeafImpl");
        new LeafImpl().work();

        System.out.println("7) Config.NON_CONST: " + Config.NON_CONST);
        System.out.println("8) Config.ping");
        Config.ping();
    }
}
```

Use **JDK 17 or newer**:

```bash
javac InterfaceInitializationDemo.java
java InterfaceInitializationDemo
```

**Expected stdout (in this program):**

```text
1) literal: Leaf
init Leaf
2) Leaf.VALUE: 1
3) constant: 10
4) construct AbstractImpl
init AbstractImpl
5) construct DefaultImpl
init Defaulted
init DefaultImpl
Defaulted.work
6) construct LeafImpl
init Parent
init LeafImpl
Parent.work
init Config
7) Config.NON_CONST: 1
8) Config.ping
Config.ping
```

### Exact Breakdown of Each Step

**(1) `Leaf.class`:** The JVM provides `Class<Leaf>`. Obtaining the literal does not by itself require initializing `Leaf` or `Parent`; therefore, no `init ...` line appears yet.

**(2) `Leaf.VALUE`:** This field is declared by **Leaf**; its value comes from calling `mark("Leaf")`, so it is not a constant variable. Accessing it causes **Leaf to be initialized** and prints `init Leaf`. Although Leaf extends Parent and Parent has a default method, **Parent is not automatically initialized** when Leaf is initialized.

**(3) `Config.CONST`:** The value `10` is a compile-time constant, so merely reading it does not require initializing Config. There is no `init Config` line here.

**(4) `new AbstractImpl()`:** AbstractImpl implements AbstractOnly, but AbstractOnly **does not declare a default method**. The `AbstractImpl` initializer runs, while `init AbstractOnly` does not appear. The JVM may have already loaded/linked AbstractOnly; this is still distinct from initialization.

**(5) `new DefaultImpl().work()`:** Before initializing DefaultImpl, the JVM initializes **Defaulted** because this interface declares a default method. The order is `init Defaulted` and then `init DefaultImpl`, after which `Defaulted.work` is called. If you omit the `work()` call and only write `new DefaultImpl()`, both initializer lines still appear.

**(6) `new LeafImpl().work()`:** LeafImpl implements Leaf; Leaf inherits a default method from Parent. **Parent** actually declares the default method, so Parent is initialized before LeafImpl, even though Leaf was already initialized in step (2) and Leaf itself does not declare a default method. The `Parent.work` body runs *after* the object has been created.

**(7) `Config.NON_CONST`:** Accessing the field that is not a compile-time constant is what triggers `Config`, printing `init Config` before the value `1` is printed.

**(8) `Config.ping()`:** An interface's static method is an initialization trigger; in this program, Config **was already initialized in step (7)**, so only the method call occurs without re-running `mark("Config")`.

### Variations Worth Trying (Not Shown in the Stdout Above)

- Move `new DefaultImpl()` before the `Leaf.VALUE` operation: you will see `Defaulted` initialized before you need to read Leaf's field.
- Remove the entire `Leaf.VALUE` operation while keeping `new LeafImpl()`: Parent is still initialized because of the default method; **Leaf is not forced to be initialized** simply because it sits between Parent and LeafImpl.
- Change `Defaulted.work()` from `default` to an abstract method and add an override of `work()` in DefaultImpl: when initializing DefaultImpl, there is no longer a requirement to initialize Defaulted solely from the implements relationship, if Defaulted does not declare any other default method.
- Add an override of `work()` in DefaultImpl while **still keeping the default method declared in Defaulted**: the JVM still must initialize Defaulted when initializing DefaultImpl.
- Replace `Config.CONST` with `Config.NON_CONST` in step (3): `Config` is initialized earlier because the field is no longer a compile-time constant.

The variations above are intended to verify **triggers**; you should not compare exact class-loading order solely using initializer output.

## 7. Does a Default Method Cause an Interface to Be Initialized Immediately Upon Loading?

**No.** An interface with a default method can still be **loaded/linked** by the JVM without being initialized:

```java
Class<?> type = Defaulted.class;
Class<?> checked = Class.forName(
        type.getName(), false, type.getClassLoader());
```

This is an **illustrative snippet in the same scope where `Defaulted` is visible**. `Class.forName(name, false, loader)` finds/loads and links the type without requiring initialization. Therefore, **defining a default method does not by itself create a trigger at loading time**.

The trigger here is the **initialization of an implementing concrete class**. At that point, the JVM inspects the relationships with superinterfaces that declare default methods and initializes them according to the rules.

Nor should you conflate:
- **Being allowed to call a default method**: requires method resolution/dispatch on a valid instance.
- **Initializing the interface containing the default method**: a mandatory consequence when an implementing class is initialized, even if the method has not been called yet.
- **Initializing an interface directly via a static field/method**: a separate trigger that does not depend on having an instance or a default method.

## 8. What Happens When a Class Overrides a Default Method?

Consider the class:

```java
interface Auditor {
    int READY = Hooks.touch();

    default String audit() {
        return "default";
    }
}

class Record implements Auditor {
    @Override
    public String audit() {
        return "override";
    }
}

class Hooks {
    static int touch() {
        System.out.println("Auditor initialized");
        return 1;
    }
}
```

This is a **set of illustrative declarations**, without a `main` yet. When the `Record` class is initialized, `Auditor` is still a superinterface **declaring a default method**, so `Auditor` must be initialized even if every instance of `Record` invokes the overridden version. This is an initialization rule based on **method declaration**, independent of which body dispatch will actually execute.

You can use `javap -c -p Auditor` and `javap -c -p Record` to observe the bytecode, but `javap` output depends on the compiler and JDK version; **do not** take a specific listing as a substitute for the JLS/JVMS rules.

## 9. Initialization Order, Circular Dependencies, and Errors

### 9.1. Initialization Order Within an Interface

Interfaces do not have `static { ... }`, but initialization expressions for fields that are not constant variables can call methods. Initializers within an interface are processed in **source code order** during the initialization phase.

```java
interface Ordered {
    int A = log("A");
    int B = log("B");

    static int log(String name) {
        System.out.println(name);
        return 1;
    }
}
```

If the program reads `Ordered.A` when Ordered is not yet initialized, the initialization output order is `A` then `B`. Reading `Ordered.B` afterward does not repeat the output. In an interface, fields are `final` yet can still have runtime initialization expressions.

### 9.2. Initializing Multiple Interfaces with Default Methods

If a class extends a superclass and implements multiple superinterfaces with default methods, the types that must be initialized are determined by the JLS/JVMS rules; multiple interfaces may be initialized before the class, and you cannot assume only the first listed interface will run.

For complex inheritance hierarchies and diamond inheritance, you need to apply the initialization algorithm of **JVMS `5.5** to predict the order among specific interfaces. Do not deduce that whichever default method is selected when called will be the **only interface** that needs to be initialized.

### 9.3. If an Interface Initializer Fails

If an interface's initializer throws an exception while it is being initialized, initialization can fail, affecting the implementing class waiting on it. The first use may see `ExceptionInInitializerError` (as exceptions are typically wrapped), and subsequent uses with the **same type definition** may see `NoClassDefFoundError: Could not initialize class ...`.

**In practice:** avoid placing hard-to-control side effects, network connections, database queries, or complex circular dependencies in an interface's field initializer; creating an implementing object can trigger that initializer **earlier than expected** if the interface has a default method.

### 9.4. Multithreading

The JVM synchronizes initialization per class/interface definition. Two threads concurrently creating instances of an implementing class will not cause the interface's initializer to run successfully twice; one thread may have to wait for the initialization performed by the other thread. Blocking logic in an initializer or circular dependencies between types can still cause deadlocks or hard-to-analyze situations.

## 10. Misconceptions to Correct

1. **"Interfaces have no constructors, so they are never initialized."** False. An interface is initialized when there is a trigger such as reading a field that is not a constant variable, calling a static method, or an implementing class meeting the default method condition.
2. **"All interfaces of a class are initialized upon `new`."** False. Only superinterfaces declaring default methods belong to the group required by the class initialization rules; other interfaces need their own triggers.
3. **"Only calling a default method initializes an interface."** False. An interface containing a default method is normally already initialized before the implementing class finishes initialization.
4. **"The class overrides the default method, so that interface does not need to be initialized."** False. The deciding factor is that the interface **declares a default method**, not which method is dispatched.
5. **"`Child extends Parent`, so initializing Child guarantees Parent is initialized."** False for interfaces: initializing an interface does not automatically trigger initialization of its superinterfaces.
6. **"When a class implements Child, only default methods declared directly in Child are considered."** False. **Indirect** superinterfaces such as Parent must also be considered.
7. **"No `static final` field ever triggers initialization."** False. A runtime initialization expression makes the field not a *constant variable*.
8. **"`T.class` and `Class.forName(name)` are equivalent."** False. A class literal does not by itself initialize T; the `Class.forName(String)` overload requires initializing the found type.
9. **"Loading an interface with a default method immediately runs its initializer."** False. Loading/linking is different from initialization.
10. **"Having a default method is enough to instantiate an interface."** False. An interface cannot be directly instantiated with `new`; the object still has a concrete class as its runtime type.

## 11. Self-Check Questions

**Question 1.** Interface `I` declares `default void save() { }`. Class `C implements I` and overrides `save()`. On the first `new C()`, does `I` need to be initialized?

**Answer:** Yes, if not yet initialized. `I` is a superinterface of the class being initialized and **declares a default method**. Overriding does not remove this requirement.

**Question 2.** Interface `I` declares only `void save();` and `int X = trace();`. Class `C implements I`. Does `new C()` automatically force `I`'s `trace()` to run?

**Answer:** Not solely because of implements. `I` does not declare a default method. However, if the code reads `I.X`, it will be initialized and run `trace()`.

**Question 3.** `Parent` has a default method, and `Child extends Parent` without declaring its own default method. Does reading the runtime field `Child.X` automatically initialize Parent?

**Answer:** No. Initializing Child does not automatically propagate up to the superinterface Parent. Conversely, when a class implementing Child is initialized, Parent must be initialized because of the default method that Parent declares.

**Question 4.** Why is reading `I.X` with `int X = 123;` different from `int X = calculate();`?

**Answer:** `123` is a constant expression, so `X` is a compile-time constant. Calling `calculate()` is not a constant expression; therefore, reading `I.X` in the second case is an initialization trigger.

**Question 5.** An interface has been initialized, and a class implementing it creates 100 objects. How many times does the interface's field initializer run?

**Answer:** It does not run again during those 100 instantiations. For the same runtime type definition that has been successfully initialized, the interface's initialization executes once.

## 12. Quick Check Mindset

```text
Observing whether interface I is initialized
                       |
          +------------+-------------+
          |                          |
          v                          v
   Using I itself?         Initializing class C?
          |                          |
   +------+------+                   v
   |             |         Is I a superinterface
static method  non-constant  (direct/indirect)
of I           static field  that DECLARES a default method?
   |             |                 /         \
   +------+------+               yes          no
          |                        |             |
triggers initializing I    initialize I       not solely due
(if not yet)               (if not yet)       to implements

Reading a compile-time constant or I.class does not by itself initialize I.
Initializing an interface does not automatically initialize its parent interfaces.
```

In practical analysis, ask **(1) which class is being initialized, (2) which interfaces in the inheritance hierarchy *declare* a default method, and (3) whether any own static field/method has previously triggered initialization?** These three questions explain both the case where an interface is initialized before a default method is used and the case where a purely abstract interface still has not run its initializer after an implementing class has been created.

### Official References

- [Java Language Specification, 12.4 and 12.4.1 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.4.1)
- [Java Virtual Machine Specification, 5.5 — Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5)
- [Java Language Specification, 9.4.3 — Interface Method Body (default methods)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.4.3)
