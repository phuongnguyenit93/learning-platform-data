# Initializing the Superclass Before the Subclass in Java

## Learning Objectives

After this lesson, you will be able to:

- Accurately explain the meaning of **“the superclass initializes before the subclass”** in two different contexts: **class initialization** (`static` members) and **object initialization** (instance fields, initializer blocks, and constructors).
- Predict the execution order upon `new Child()`: required class initialization, assigning default values to object fields, the `super(...)` constructor call chain, instance initializers, and constructor bodies.
- Understand `this(...)` and `super(...)` in Java 17, multi-level constructor chaining, available superclass constructor requirements, and common compilation errors.
- Distinguish static initialization **once per runtime class** from instance initialization **per object**.
- Explain why a superclass constructor can invoke a method overridden in a subclass **before the subclass's field initializers run**, and why this is a design risk.
- Recognize that reading a static field **declared in the superclass** through the subclass name does not necessarily trigger subclass initialization.
- Understand the role of access modifiers, `final`, field hiding, interface initialization, and errors occurring in a constructor/class initializer.
- Compile/run standalone examples compatible with JDK 17+, read stdout accurately, and independently analyze an inheritance hierarchy.

## 1. One Statement, Two Mechanisms to Distinguish

Given:

~~~java
class Parent {
}

class Child extends Parent {
}
~~~

`Child` is a subclass of `Parent`. Saying “Parent initializes before Child” can refer to two **different** processes:

1. **Class initialization:** The JVM executes `Parent`'s static field initializer expressions and `static { ... }` before executing the corresponding parts of `Child` when initializing `Child`.
2. **Initializing a Child object (object initialization):** when a `Child` object is created, the superclass constructor chain precedes the initialization of the subclass's instance fields and constructor body, according to Java rules.

The two processes are related, yet **not the same**. A class may undergo `static` initialization beforehand without creating any object; afterward, each `new Child()` still performs the **instance initialization** sequence for the new object.

### 1.1. A General Timeline

~~~text
On the first new Child() in a simple JVM:

CLASS INITIALIZATION (if the classes are not yet initialized):
  Parent: static fields / static blocks
  Child:  static fields / static blocks

OBJECT CREATION:
  Allocate Child object; fields initially hold default values
  Constructor chain ascends to Parent / Object
  Initialize superclass instance fields, instance blocks
  Run superclass constructor body
  Initialize subclass instance fields, instance blocks
  Run subclass constructor body
  Return reference to the successfully created Child object
~~~

The diagram only depicts a simple inheritance hierarchy. In practice, there are also grandparent classes, `this(...)` constructor delegation, superinterfaces with default methods, previously completed initialization, and exceptions that halt the process.

**Key point:** there is no rule stating that “every static block runs only when creating an object”. They run when the class is **initialized**, and `new` is just one of the triggering situations.

## 2. Distinguishing Class Loading, Linking, Initialization, and Object Creation

To speak accurately about ordering, four concepts need to be identified:

| Phase | Main Task | Relationship to `new Child()` |
| --- | --- | --- |
| **Loading** | Locate/define the binary representation of the class at runtime | May have already occurred earlier |
| **Linking** | Verification, preparation, and resolution per JVM rules | Static fields are prepared; details may take place at different times |
| **Class initialization** | Execute static initializers according to rules and superclass dependencies | Parent is initialized before Child when Child needs to be initialized |
| **Object initialization** | Create and initialize the state of **an instance** | Constructor chain and instance initializers are executed for the object |

`static` fields belong to the runtime class; instance fields belong to each object. Although both can receive **default values** before initializer expressions run, “assigned default values” must not be interpreted to mean that the constructor has completed or that business invariants are satisfied.

### 2.1. Default Field Values Are Not Complete Initializers

Example:

~~~java
class Child extends Parent {
    int age = 18;
    String name = "An";
}
~~~

Before the instance field initializers `age = 18` and `name = "An"` are executed for the object, the field slots hold default values of `0` and `null`, respectively. These default values are especially important if an overridden method is called prematurely from the superclass constructor.

For local variables in a method, Java has its own *definite assignment* rules: you cannot assume that a local variable can be read with a default of 0/null like instance fields.

## 3. Class Initialization Example: Superclass Static Before Subclass Static

Save **`ParentChildStaticDemo.java`**:

~~~java
public class ParentChildStaticDemo {
    static int trace(String message, int value) {
        System.out.println(message);
        return value;
    }

    static class Parent {
        static int parentNumber = trace("Parent.static field", 10);

        static {
            System.out.println("Parent.static block");
        }
    }

    static class Child extends Parent {
        static int childNumber = trace("Child.static field", 20);

        static {
            System.out.println("Child.static block");
        }
    }

    public static void main(String[] args) {
        System.out.println("main starts");
        System.out.println("childNumber=" + Child.childNumber);
        System.out.println("childNumber again=" + Child.childNumber);
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac ParentChildStaticDemo.java
java ParentChildStaticDemo
~~~

**Exact stdout:**

~~~text
main starts
Parent.static field
Parent.static block
Child.static field
Child.static block
childNumber=20
childNumber again=20
~~~

Sequence of events:

1. The JVM initializes the outer class `ParentChildStaticDemo` to run `main`; the outer class has no static initializer that prints any line.
2. `main` prints `main starts`.
3. On the first read of `Child.childNumber`, the field is declared by `Child` and is a non-constant static field, so `Child` requires initialization.
4. Before executing `Child`'s static initializers, the superclass `Parent` is initialized according to JLS rules.
5. Within each class, static field initializers and static blocks run **in the order they appear in the class body**.
6. Reading `Child.childNumber` a second time does not re-run the initializers; the value remains 20.

**Do not confuse:** Java does not run all static fields of the entire hierarchy before all static blocks. The order is **superclass before subclass**, and **within each class** it is the declaration order of field initializers/blocks.

### 3.1. Why Can `trace` Be Called Before `main`?

`trace` is a static method declared in the outer class. When a field initializer calls `trace`, that method executes and prints the corresponding line. The source order of a method declaration relative to a static field is not a promise that the method is “run beforehand”; it only needs to resolve validly when the expression is evaluated.

### 3.2. The Second Call Does Not Re-Initialize the Class

According to JVM rules, initialization state is managed per **runtime class**. In the typical case of a single JVM and a single defining class loader, the same `Parent`/`Child` do not re-run their static blocks after being initialized.

If you start a new Java process, the runtime classes in the new JVM have a new lifecycle. With different class loaders, separate runtime classes bearing the same binary name can exist; do not generalize absolutely as “only once across all programs”.

## 4. Object Creation Order Example: Superclass Before Subclass, Per Instance

Save **`ParentChildInstanceDemo.java`**:

~~~java
public class ParentChildInstanceDemo {
    static int trace(String name, int value) {
        System.out.println(name);
        return value;
    }

    static class Parent {
        int parentValue = trace("Parent.instance field", 10);

        {
            System.out.println("Parent.instance block");
        }

        Parent() {
            System.out.println("Parent.constructor value=" + parentValue);
        }
    }

    static class Child extends Parent {
        int childValue = trace("Child.instance field", 20);

        {
            System.out.println("Child.instance block");
        }

        Child() {
            super();
            System.out.println("Child.constructor value=" + childValue);
        }
    }

    public static void main(String[] args) {
        System.out.println("before new");
        new Child();
        System.out.println("after new");
    }
}
~~~

Run:

~~~bash
javac ParentChildInstanceDemo.java
java ParentChildInstanceDemo
~~~

**Output:**

~~~text
before new
Parent.instance field
Parent.instance block
Parent.constructor value=10
Child.instance field
Child.instance block
Child.constructor value=20
after new
~~~

Reading the order:

- `new Child()` begins creating **a Child object**, which contains the fields declared in `Parent` and `Child`.
- `Child`'s constructor has an explicit `super()`, which invokes the no-argument constructor of `Parent`.
- Before the body of `Parent()`, the instance field initializers and instance initializer blocks belonging to `Parent` are executed in class body order.
- After `Parent()` completes, `Child`'s instance initializers run, followed by the body of `Child()`.
- `main` prints `after new` after the `Child()` constructor returns normally.

In this example, no static block prints any line. That does **not** mean static initialization is skipped: there are simply no static initializers with observable side effects.

### 4.1. The Order Within Each Class Is Also Declaration Order

~~~java
class Parent {
    int a = log("field a");
    {
        log("instance block");
    }
    int b = log("field b");

    Parent() {
        log("constructor body");
    }
}
~~~

This is an illustrative snippet with an appropriate `log(String)` method. The order of `Parent`'s instance initialization is field a → instance block → field b → constructor body. Java does **not** by default run all field initializers before all instance blocks.

If the subclass also has fields/blocks, the subclass's steps are executed during the corresponding subclass phase, after the superclass constructor chain has executed according to the rules.

### 4.2. Constructors Are Not Inherited

Even though `Child extends Parent`, `Parent`'s constructors do not become `Child`'s constructors. `new Child(...)` is only valid if `Child` has a compatible declared constructor or the compiler provides an implicit default constructor when conditions are met.

A `Child` constructor **invokes** a `Parent` constructor via `super(...)`; that is not “constructor inheritance”.

## 5. Combined Example: Static Once, Constructor Multiple Times

Save **`StaticAndInstanceLifecycleDemo.java`**:

~~~java
public class StaticAndInstanceLifecycleDemo {
    static class Parent {
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

    static class Child extends Parent {
        static {
            System.out.println("Child.static");
        }

        {
            System.out.println("Child.instance");
        }

        Child() {
            System.out.println("Child.constructor");
        }
    }

    public static void main(String[] args) {
        System.out.println("first");
        new Child();
        System.out.println("second");
        new Child();
    }
}
~~~

Commands:

~~~bash
javac StaticAndInstanceLifecycleDemo.java
java StaticAndInstanceLifecycleDemo
~~~

Stdout:

~~~text
first
Parent.static
Child.static
Parent.instance
Parent.constructor
Child.instance
Child.constructor
second
Parent.instance
Parent.constructor
Child.instance
Child.constructor
~~~

For the first object:

1. `Parent.static` then `Child.static`.
2. `Parent.instance`, `Parent.constructor`.
3. `Child.instance`, `Child.constructor`.

For the second object, both classes are already initialized, so only the **instance** and **constructor** steps occur. The name `Parent.static` in the output indicates that the static block runs **once for the runtime Parent**, not “once for a Parent object inside a Child object”.

### 5.1. How Many Parts of Instance State Does a Child Object Have?

Creating `new Child()` does not create **two separate objects**, one Parent and one Child. It creates **one object** whose runtime type is `Child`, and that object has state/behavior defined according to the appropriate inheritance structure. Both superclass and subclass constructors participate in initializing that **same object**.

If the `Parent()` constructor prints `this.getClass().getSimpleName()` in this case, the object's runtime class can be `Child`, even while code is executing inside `Parent()`. This relates directly to the dynamic dispatch risk covered in a later section.

## 6. Multi-Level Inheritance: Object → Grandparent → Parent → Child

When the inheritance chain has multiple levels, initialization proceeds through the superclasses from top to bottom in the appropriate order.

Save **`ThreeLevelInitializationDemo.java`**:

~~~java
public class ThreeLevelInitializationDemo {
    static class Grandparent {
        static {
            System.out.println("Grandparent.static");
        }

        {
            System.out.println("Grandparent.instance");
        }

        Grandparent() {
            System.out.println("Grandparent.constructor");
        }
    }

    static class Parent extends Grandparent {
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

    static class Child extends Parent {
        static {
            System.out.println("Child.static");
        }

        {
            System.out.println("Child.instance");
        }

        Child() {
            System.out.println("Child.constructor");
        }
    }

    public static void main(String[] args) {
        System.out.println("create");
        new Child();
        System.out.println("complete");
    }
}
~~~

Compile and run:

~~~bash
javac ThreeLevelInitializationDemo.java
java ThreeLevelInitializationDemo
~~~

Output:

~~~text
create
Grandparent.static
Parent.static
Child.static
Grandparent.instance
Grandparent.constructor
Parent.instance
Parent.constructor
Child.instance
Child.constructor
complete
~~~

Tree structure:

~~~text
java.lang.Object
       |
   Grandparent
       |
     Parent
       |
      Child
~~~

The static initializers of the user-declared classes follow the order of superclass before subclass in this scenario. The constructor chain must always ascend to the appropriate superclass, ultimately reaching `Object` (even though `Object` prints nothing in the example), and then instance initialization/constructor bodies complete from the top class down to the bottom class.

**There are not three `new` calls for Grandparent, Parent, and Child.** There is only a single `new Child()`, with the chain of constructors participating.

## 7. `super(...)`: Choosing Which Superclass Constructor to Run

A subclass constructor can declare an explicit constructor invocation to its superclass:

~~~java
class Parent {
    private final String name;

    Parent(String name) {
        this.name = name;
    }
}

class Child extends Parent {
    Child() {
        super("default");
    }
}
~~~

The two classes above are valid **illustrative code** within an appropriate file/package. `super("default")` selects the `Parent(String)` constructor, ensuring the superclass initializes its own state.

### 7.1. What Happens If `super()` Is Not Written?

In Java 17, when a constructor body does not begin with an explicit `this(...)` or `super(...)`, Java treats it as having an implicit `super()` before the body.

~~~java
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
~~~

This is illustrative code; when creating a Child, `Parent()` is called before `Child()`.

**However**, an implicit `super()` is only valid if the superclass has an **accessible and callable no-argument constructor**. The compiler does not automatically substitute `super("x")` or `super(0)` to “pick arbitrarily” another constructor.

### 7.2. Case Without a Superclass No-Arg Constructor

Intentionally invalid example:

~~~java
class Parent {
    Parent(int id) {
    }
}

class Child extends Parent {
    // Child() { } // Error because the compiler implicitly inserts super(), but
    //              // Parent has no no-argument constructor.
}
~~~

Even if `Child` declares no constructor at all, the compiler generates a default constructor for Child and still needs to call `super()`; therefore, this `Child` class **does not compile** with `Parent` as shown above. Merely commenting out the constructor is not enough to make the example source code valid: the entire **pair of classes** is presented to illustrate the error.

Fix:

~~~java
class Parent {
    Parent(int id) {
        System.out.println("Parent id=" + id);
    }
}

class Child extends Parent {
    Child() {
        super(10);
        System.out.println("Child()");
    }
}
~~~

Now the `Child()` constructor explicitly invokes `Parent(int)`. If `new Child()` is run, the output is:

~~~text
Parent id=10
Child()
~~~

These are **two alternative versions** of the Parent/Child classes; do not place both pairs with the same names into the same package and build them simultaneously.

### 7.3. An Accessible Constructor Is a Separate Requirement

A subclass cannot automatically invoke a `private Parent()`. If the parent constructor is inaccessible at the call site, `super()` is invalid. `protected` constructors, public constructors, and package-private constructors follow their respective access rules.

Changing a `private` constructor to `public` just to silence a compiler error is not always the right solution: you should determine by design who is allowed to instantiate which type of object and provide an appropriate constructor/factory.

## 8. `this(...)`: Multiple Subclass Constructors Without Running Initializers Multiple Times

Within the same class, one constructor can **delegate to another constructor** using `this(...)`.

Save **`ConstructorChainingDemo.java`**:

~~~java
public class ConstructorChainingDemo {
    static class Parent {
        Parent(String name) {
            System.out.println("Parent(" + name + ")");
        }
    }

    static class Child extends Parent {
        {
            System.out.println("Child.instance block");
        }

        Child() {
            this(7);
            System.out.println("Child()");
        }

        Child(int id) {
            super("root");
            System.out.println("Child(int) id=" + id);
        }
    }

    public static void main(String[] args) {
        new Child();
    }
}
~~~

Compile/run:

~~~bash
javac ConstructorChainingDemo.java
java ConstructorChainingDemo
~~~

Output:

~~~text
Parent(root)
Child.instance block
Child(int) id=7
Child()
~~~

Trace:

1. `new Child()` invokes `Child()`.
2. `Child()` begins with `this(7)`, forwarding to `Child(int)`.
3. `Child(int)` begins with `super("root")`, calling `Parent(String)`.
4. When the Parent constructor completes, **Child's instance initializer block runs once**.
5. The body of `Child(int)` prints `Child(int) id=7`.
6. Control returns to the remainder of `Child()` and prints `Child()`.

Importantly, **Child's instance initialization block does not run twice** just because two constructor bodies participate in a `this(...)` chain. It runs for the new Child object as part of the appropriate initialization sequence.

### 8.1. In Java 17, the Constructor Invocation Must Be the First Statement

Intentionally invalid example:

~~~java
class Child extends Parent {
    Child() {
        // System.out.println("before super");
        super();
    }
}
~~~

In **Java 17**, ordinary statements cannot be placed before an explicit `super(...)` or `this(...)` in a constructor body. The print line is commented out to highlight this restriction. In addition, the example requires a superclass Parent with an accessible no-arg constructor to compile.

Do not use syntax or relaxations from newer Java versions to infer Java 17 behavior.

### 8.2. `this(...)` and `super(...)` Cannot Both Appear as Two Constructor Invocations

Each constructor has only **one** explicit constructor invocation at the start (or an implicit `super()` when applicable); you cannot write both `this(...)` and `super(...)` consecutively. Superclass initialization is performed by the target constructor of the `this(...)` chain.

A `this(...)` chain cannot form a cycle calling each other indefinitely; compiler rules prevent recursive constructor invocation.

## 9. The Superclass Is Initialized First, Yet the Subclass May Still Hold Default Values

There is a very important exception to the “superclass before subclass” intuition: **an instance method of the superclass called inside a constructor still dispatches dynamically to the subclass override**, even though the subclass's instance initializers have not yet executed.

~~~java
class Parent {
    Parent() { display(); }
    void display() { System.out.println("Parent"); }
}
class Child extends Parent {
    private String label = "READY";
    @Override void display() { System.out.println(label); }
}
~~~

This is a **snippet**: if `new Child()` is created for the first time with no other side effects, the `display()` call from the Parent constructor can print `null`, because `label` has not yet been assigned `"READY"`. The object is already allocated and its instance fields hold **default values**, while Child's initializer assignment runs only after superclass construction. This is not a case of “Java not overriding before construction completes”: dynamic dispatch itself is the cause.

**Safe design:** do not invoke an overridable method that depends on subclass state from a constructor; place superclass validation in an appropriate private/final helper or move polymorphic hooks to a phase after the object has been successfully created. The lesson “Calling an Overridden Method When the Object Is Not Yet Fully Initialized” is the main place for analyzing this: tracing `null/0`, indirect methods, `toString()`, `this` escape, and factory/lifecycle approaches.

### Field Hiding Is Not Like Method Overriding

Fields do **not** dispatch dynamically like overridden instance methods:

~~~java
class Parent {
    int value = 1;
}
class Child extends Parent {
    int value = 2;
}
~~~

With a `Child child` variable, `child.value` accesses Child's field, whereas `((Parent) child).value` accesses Parent's field. Those are **two fields in the same object**, not virtual dispatch of a method. In practice, you should avoid hiding fields when it makes semantics hard to read.

## 10. Creating a Child Object Does Not Separately Create Another Parent Object

A common question: does `new Child()` implicitly call `new Parent()`?

**Not in the sense of creating two independent objects.** Calling `super(...)` drives the initialization of the superclass part of **the same Child object**, rather than allocating a separate Parent object and attaching it to Child.

Data:

~~~java
class Parent {
    int baseId = 10;
}

class Child extends Parent {
    int childId = 20;
}
~~~

A Child object can contain both `baseId` and `childId`. Parent's constructor does the superclass's part; Child's constructor does the subclass's part. This mechanism **differs from composition**, where Child has a field `Parent component = new Parent()` — in that case, `new Parent()` actually creates a separate object.

### 10.1. `super` Is Not a Variable Holding an Independent Parent Object

`super.method()` is the way to select an implementation/method belonging to the superclass under Java rules, not a field reference pointing to a separate “Parent object inside the Child object”. Even when calling `super.method()`, `this` is still the same object with runtime type Child.

This distinction is crucial when reasoning about state and the constructor chain.

## 11. Inherited Static Fields: `Child.PARENT_FIELD` Does Not Necessarily Initialize Child

A common misconception is that “mentioning Child in any expression will definitely initialize Child”.

According to the JLS, when reading a **non-constant static field** using a name that may be written via a subclass, initialization pertains to **the class that actually declares the field**.

Save **`InheritedStaticFieldDemo.java`**:

~~~java
public class InheritedStaticFieldDemo {
    static class Parent {
        static int CODE = init();

        private static int init() {
            System.out.println("Parent initialized");
            return 10;
        }
    }

    static class Child extends Parent {
        static {
            System.out.println("Child initialized");
        }

        Child() {
            System.out.println("Child constructor");
        }
    }

    public static void main(String[] args) {
        System.out.println("before field");
        System.out.println("code=" + Child.CODE);
        System.out.println("before new");
        new Child();
    }
}
~~~

Run:

~~~bash
javac InheritedStaticFieldDemo.java
java InheritedStaticFieldDemo
~~~

**Output:**

~~~text
before field
Parent initialized
code=10
before new
Child initialized
Child constructor
~~~

Explanation:

- `CODE` **is declared in Parent**, not Child.
- Reading `Child.CODE` forces Parent to initialize if not yet initialized, but **does not itself force Child to initialize**.
- The subsequent `new Child()` is an active use of Child, so Child is initialized and prints `Child initialized`.
- Parent was already initialized in the first step, so `Parent initialized` is not printed again.

**Do not draw the rule that every `Child.` name skips Child initialization.** If that field is **declared in Child**, and is not a compile-time constant variable, the read can initialize Child, triggering the superclass as well if it is not yet initialized.

### 11.1. Compile-Time Constants Are Another Exception

If Parent declares:

~~~java
static final int CONSTANT = 42;
~~~

with a constant expression initializer, reading `Child.CONSTANT` **does not itself require** initialization of either Parent or Child, because this is a constant variable. The compiler can use the value 42 directly at the call site.

`static final int RUNTIME = compute();`, on the other hand, is **not** a compile-time constant; reading it can trigger initialization of the declaring class.

For a complete understanding, you must check **the field's declaring class** and **whether it is a constant variable**, not just the static/final modifiers.

## 12. Type Names, Class Literals, and Static Methods: Different Triggers

Having a class `Child` **referenced as a type** in code does not mean it has definitely run its static initializer.

Example:

~~~java
Class<?> type = Child.class;
~~~

A class literal creates/obtains the corresponding `Class` object, yet by itself it is not an operation that necessarily initializes Child under standard rules. Calling `Class.forName("...")` with the default overload or accessing an applicable non-constant static field can trigger initialization.

You should also distinguish:

- **Calling a static method declared in Child**: can be an active use that causes Child to be initialized.
- **Calling a static method actually declared in Parent but written as `Child.parentMethod()`**: initialization pertains to the declaring class Parent according to the rules; Child is not initialized by default just because of the qualifier.
- **Calling an instance method through an already-created Child object**: in typical contexts Child already had to be initialized when the object was created; do not infer that an instance method has its own “separate class initialization” on each call.

When analyzing output, identify **which operation first actually forces the class to be initialized**, rather than merely spotting the name `Child`.

## 13. Constructor Chain When the Superclass Has `final` Fields

An object must be constructed in a valid state, and a superclass can protect its state via `private final` fields.

Save **`ConstructorValidationDemo.java`**:

~~~java
public class ConstructorValidationDemo {
    static class Parent {
        private final String id;

        Parent(String id) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("id required");
            }
            this.id = id;
            System.out.println("Parent validated " + id);
        }

        final String id() {
            return id;
        }
    }

    static class Child extends Parent {
        private final int level;

        Child(String id, int level) {
            super(id);
            if (level <= 0) {
                throw new IllegalArgumentException("level must be positive");
            }
            this.level = level;
            System.out.println("Child validated level=" + level);
        }

        int level() {
            return level;
        }
    }

    public static void main(String[] args) {
        Child child = new Child("A", 3);
        System.out.println(child.id() + ":" + child.level());

        try {
            new Child("", 3);
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid parent id rejected");
        }

        try {
            new Child("B", -1);
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid child level rejected");
        }
    }
}
~~~

Run:

~~~bash
javac ConstructorValidationDemo.java
java ConstructorValidationDemo
~~~

Output:

~~~text
Parent validated A
Child validated level=3
A:3
invalid parent id rejected
Parent validated B
invalid child level rejected
~~~

**Interpretation:**

- Valid case: the superclass validates and assigns `id`, then the subclass validates and assigns `level`. Both `final` fields are assigned along the constructor chain.
- With `new Child("", 3)`, the superclass constructor throws an exception **before** printing or before the subclass body runs; the caller catches the error and does not receive a successfully created Child object.
- With `new Child("B", -1)`, the superclass constructor **already** printed `Parent validated B`, but the subclass constructor detects the invalid level and throws an exception. The caller does not receive a successful Child object.
- If the superclass constructor performs I/O or modifies shared state and then the subclass constructor fails, those side effects **are not automatically rolled back**. This is one reason to minimize hard-to-recover side effects inside constructors.

### 13.1. Protecting Invariants at the Right Level

A superclass should protect invariants related to the state it owns, without assuming the subclass is already fully initialized. A subclass should validate its own state before the object is published by the API.

You should not expose `protected` mutable fields and let subclasses directly mutate all state without validation. Consider `private` fields and protected/public methods with clear contracts if subclasses need extension points.

## 14. Errors in a Superclass Static Initializer Affect the Subclass

If Parent is not initialized successfully, an active use of Child that depends on Parent can fail before Child's static initializer or Child's constructor gets a chance to run.

Save **`ParentInitializationFailureDemo.java`**:

~~~java
public class ParentInitializationFailureDemo {
    static class Parent {
        static int STATUS = prepare();

        private static int prepare() {
            System.out.println("Parent preparing");
            throw new IllegalStateException("parent configuration invalid");
        }
    }

    static class Child extends Parent {
        static {
            System.out.println("Child static");
        }

        Child() {
            System.out.println("Child constructor");
        }
    }

    public static void main(String[] args) {
        try {
            new Child();
        } catch (Error error) {
            System.out.println("first=" +
                    error.getClass().getSimpleName());
        }

        try {
            new Child();
        } catch (Error error) {
            System.out.println("second=" +
                    error.getClass().getSimpleName());
        }
    }
}
~~~

Run:

~~~bash
javac ParentInitializationFailureDemo.java
java ParentInitializationFailureDemo
~~~

**Output:**

~~~text
Parent preparing
first=ExceptionInInitializerError
second=NoClassDefFoundError
~~~

- The first initialization of Child requires Parent to be initialized first. Parent calls `prepare()` and throws `IllegalStateException`; the JVM typically reports `ExceptionInInitializerError` for an exception that is not an `Error`.
- `Child static` and `Child constructor` are **not** printed because Parent initialization failed.
- When attempting another active use of the relevant runtime class after it has been marked erroneous, `NoClassDefFoundError` can occur, as illustrated by the program.
- Error message details and cause chains may vary across JDK versions; the example prints only the simple class name so the output remains stable.

**Catching `Error` in this example is solely to observe the mechanism**, not guidance for ordinary applications to catch and ignore all `Error`s. In real systems, design clear startup failure handling/monitoring, inspect the cause, and do not expect another `new` call to re-run a failed static initializer.

## 15. If a Superclass Constructor Throws an Exception, Does the Subclass Run?

If `super(...)` does not complete normally, the Child creation process stops; Child's instance initializers and constructor body are not executed.

Example:

~~~java
class Parent {
    Parent(int id) {
        if (id < 0) {
            throw new IllegalArgumentException("invalid id");
        }
    }
}

class Child extends Parent {
    int value = print("Child field");

    Child(int id) {
        super(id);
        System.out.println("Child body");
    }

    private static int print(String text) {
        System.out.println(text);
        return 10;
    }
}
~~~

This is an **illustrative class snippet**; when `new Child(-1)` is called, the superclass constructor throws before the `Child field` or `Child body` lines are executed. If the Parent constructor had side effects that completed before throwing, they do not automatically roll back.

This differs from a class initialization error: a constructor failure **does not by default cause the class itself to be marked as erroneous initialization**. If the class has already initialized successfully and the input data for a subsequent object creation is valid, you can generally attempt to create a new object, depending on the contract and side effects.

## 16. Remembering the Phases of Object Creation More Accurately

Upon `new Child()` with a valid class hierarchy:

1. **Active use/initialization:** the Child class must be initialized before completing instance creation, following superclass/interface rules as needed.
2. **Allocate object:** the Child object is allocated and the hierarchy's instance fields initially hold **default values**.
3. **Evaluate constructor argument expressions** according to Java rules (which may have side effects and exceptions).
4. **Constructor invocation chain:** `Child(...)` invokes `this(...)` or `super(...)`, continuing up to the superclass as required.
5. **Superclass initialization of the instance:** at the corresponding superclass level, instance field initializers and instance initializer blocks run in textual order, after the superclass call above, followed by this level's constructor body.
6. **Subclass initialization of the instance:** after the superclass constructor completes, the subclass's instance field initializers/blocks run in textual order, and the subclass constructor body is executed.
7. **Constructor returns normally:** `new` returns a reference to the object. If an exception occurs, there is no successfully created object result for that `new` expression.

This is a learning model for Java 17; JLS `12.5` and `8.8.7.1` describe the sequence more precisely, including instance initializer exceptions, constructor delegation, and evaluation.

### 16.1. Do Not Phrase It as “Subclass Fields Only Come Into Existence After the Superclass Constructor Finishes”

The Child object and its fields are allocated storage according to allocation rules **before all constructors finish**. What runs later are Child's **explicit instance field initializer expressions**, not the fields themselves being “created” only after the Parent constructor returns.

Because the fields already have default values, early dynamic dispatch can read those values. This is the root cause of `Child.describe label=null,level=0` in the earlier example.

### 16.2. Do Not Equate “Class Initialized” with “All Instances Initialized”

Having a class `Child` initialized at the `static` level does not mean a specific object of it has been created. You can call a static method or read a non-constant static field to initialize the class without ever executing `new Child()`.

Conversely, after the initial class initialization, thousands of Child objects can be created, and each object still runs its own constructor chain.

## 17. Interface Initialization Is Not Entirely Like the Superclass Chain

A Java class can `extends` one class and `implements` multiple interfaces. Class and interface initialization order have distinct details:

- When initializing a class, the JVM/JLS requires initializing the superclass and any relevant superinterfaces that declare default methods according to the rules.
- Initializing an interface **does not automatically trigger initialization of every superinterface** like a superclass constructor chain.
- An interface does not have constructors or instance initializer blocks like a class; interface fields are implicitly `public static final`, though some fields have a runtime initializer rather than a compile-time constant.

Therefore, you should not take the rule **“Parent class before Child class”** and apply it verbatim to every interface in the implements/extends hierarchy.

### 17.1. There Is No Interface “super()”

A class does not call `super()` to an interface constructor because interfaces **have no object constructors**. `super(...)` in a constructor refers to the immediate superclass. Syntax such as `InterfaceName.super.defaultMethod()`, when valid, is an invocation of a specific default method, not initialization of a separate interface instance.

For introductory examples on classes and objects, keep these clearly separated:
- **Class inheritance:** `extends` and the constructor chain.
- **Interface contract:** `implements`, default methods, static interface fields, and different initialization rules.

## 18. Why Does Initialization Order Matter in OOP Design?

The superclass → subclass order is the foundational mechanism for these responsibilities:

- **Superclass validation:** ensures Parent's portion of state is valid before Child completes.
- **Code reuse:** Parent initializes shared fields through a constructor inherited in terms of behavior, without inheriting the constructor itself.
- **Polymorphism:** a Child object is a subtype of Parent and has runtime dispatch; however, premature polymorphism inside a constructor can observe incomplete state.
- **Encapsulation:** each level should control the state it owns, limiting exposure of mutable fields to subclasses.
- **Failure safety:** if a constructor or class initialization fails, all side effects must be considered.
- **Testability:** a stdout trace can reveal which constructor was called and when initializer expressions ran.

### 18.1. Designing a Safe Parent Constructor

A typically clear approach:

~~~java
class Parent {
    private final String id;

    Parent(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id required");
        }
        this.id = id;
    }

    final String id() {
        return id;
    }
}
~~~

`Parent` validates its own input data and does not call an overridable method in the constructor. `final id()` also prevents subclasses from overriding the getter if the contract must remain fixed. `Child` can invoke `super(id)` and perform its own state validation afterward.

### 18.2. If a Subclass Hook Is Needed, Invoke It After Creation Finishes

You should not place an overridable hook in `Parent()` if the hook needs Child's state. Consider a factory:

~~~java
static Child createChild(String id) {
    Child child = new Child(id);
    child.afterConstruction();
    return child;
}
~~~

This is an **illustrative** snippet inside an appropriate class/factory. If `afterConstruction()` is designed as a lifecycle method that runs after the constructor completes, it can observe the already-initialized instance fields. However, a clear contract must be defined: the object should not be published to external code before mandatory initialization steps finish, and callers should not be left liable to forget calling the lifecycle method.

For critical invariants, prefer a constructor/factory that produces a **complete** object before returning it rather than relying on manual public callbacks.

## 19. A Few Points on `final` and Initialization Order

- `final` instance fields can be assigned in a field initializer or constructor following Java's definite assignment rules.
- A superclass with `final` fields cannot have them directly reassigned by a subclass merely because of `extends`.
- A `final` method cannot be overridden by a subclass, so calling it from a constructor does not encounter **that exact** risk of dispatching to an overridden method; however, the method's logic must still avoid unready state or external side effects.
- A `final` class has no subclasses, reducing the risk of subclass overrides, yet still must protect invariants when initializing state.
- `static final` fields following constant-expression rules can be compile-time constants; reading them does not require initializing the class. This is a separate matter from `final` instance fields.

Do not equate `final`, immutability, thread safety, and class initialization order.

## 20. Common Mistakes When Analyzing Output

| Mistake | Fact |
| --- | --- |
| “`new Child()` runs the Child constructor then Parent.” | Chaining invokes the superclass before the Child body completes. |
| “The static block runs every time a Child object is created.” | A static block belongs to class initialization and typically runs once per runtime class. |
| “Parent and Child static field initializers are grouped together.” | Each class is initialized per the rules; Parent before Child, textual order within each class. |
| “All Child instance fields already hold initializer values before the Parent constructor.” | Not yet; they hold default values before Child's initializers run. |
| “A Parent constructor calling `virtualMethod()` is guaranteed to run the Parent implementation.” | An override can be dispatched to Child even though Child has not finished initializing. |
| “Once the Parent constructor finishes, a separate Parent object is created.” | The same single Child object is being initialized across the hierarchy. |
| “Parent's constructors are inherited in Child.” | Constructors are not inherited; a Child constructor can invoke a super constructor. |
| “If Parent has no no-arg constructor, Child() automatically calls another constructor.” | No; an explicit `super(args)` or appropriate constructor structure is required. |
| “`this(...)` in Child causes Child fields/blocks to run twice.” | A constructor delegation chain for the same object does not repeat instance initialization like that. |
| “In Java 17, you can print a line before `super()`.” | Under Java 17, the explicit constructor invocation must be the first statement. |
| “Reading `Child.CODE` always initializes Child.” | If CODE is declared in Parent, it may initialize only Parent. |
| “Reading a static final constant always runs the static block.” | A constant variable can be inlined, without triggering initialization. |
| “`Child.class` always initializes Child.” | A class literal does not itself require class initialization in ordinary contexts. |
| “If Parent's static initializer fails, Child's static initializer still runs.” | Parent failure can prevent Child from completing initialization. |
| “If a constructor throws an exception, all classes become erroneous.” | Constructor failure does not equate to class initialization failure. |
| “Interface constructors also run before the class constructor.” | Interfaces have no instance constructors. |
| “Field shadowing and method overriding are the same mechanism.” | Field lookup is generally based on static type; instance methods use dynamic dispatch. |
| “It is always safe for a superclass constructor to call an overridable method.” | Child's overriding method may read fields still holding default values. |
| “Thread-safe class initialization means all static mutable state is thread-safe.” | Synchronization during initialization is different from synchronization during subsequent updates. |

## 21. Checklist for Predicting a Program Before Running It

For an example containing `new Child()`:

1. **Find the hierarchy**: `Child extends Parent`, what does Parent extend, and are there relevant interface default methods?
2. **Identify which classes are already initialized beforehand**; did any active use occur before `new`?
3. **Write out each class's static initializers** in textual order, starting from the appropriate uninitialized superclass.
4. **Check which constructor `new Child(arguments)` selects** and any argument expressions that might have side effects.
5. **Trace `this(...)` or `super(...)`** at the start of each Java 17 constructor; implicit `super()` when there is no explicit invocation.
6. **Reach the topmost required superclass**, then process instance initializers and constructor bodies as control descends the hierarchy.
7. **Note the default values of subclass fields** if superclass code can access them via dynamic dispatch.
8. **Distinguish method overriding from field hiding** when predicting where values are read from.
9. **If a method/initializer throws an exception**, halt the remaining initialization and follow the appropriate catch/unwind path.
10. **If `new` runs a second time**, do not re-print static initializers of already-initialized classes; run only the instance/constructor logic.
11. **Verify the actual stdout** using Java 17, without skipping the explanation of why each line occurs.
12. **Check design risks:** overridden callbacks in constructors, side effects upon failure, mutable static state, thread safety, and constructor API access.

## 22. Self-Check Questions and Answers

**Question 1.** Both class `Parent` and `Child extends Parent` have a static block. When creating a Child for the first time, which block runs first?  
**Answer:** Parent initializes before Child according to class initialization rules (assuming neither is already initialized).

**Question 2.** Why does creating a Child a second time typically not print the static blocks again?  
**Answer:** The runtime classes are already initialized; static initialization does not repeat for each instance.

**Question 3.** Whose constructor does `Child() { super(); ... }` invoke?  
**Answer:** The no-argument constructor of the immediate superclass Parent, if accessible/valid.

**Question 4.** What does Java 17 do when the `Child()` constructor has no explicit `this(...)`/`super(...)`?  
**Answer:** The compiler applies an implicit `super()`. If Parent has no accessible no-arg constructor, an error will be reported.

**Question 5.** Parent only has `Parent(int)`. How can a no-argument Child constructor be valid?  
**Answer:** Child() must invoke an appropriate Parent constructor using an explicit `super(value)`, for example `super(10)`.

**Question 6.** If `Child()` calls `this(10)` and then `Child(int)` calls `super()`, how many times does Child's instance initializer run for one object?  
**Answer:** Once within the object's constructor delegation chain.

**Question 7.** Why can the Parent constructor invoke `Child.override()`?  
**Answer:** Instance method overriding uses dynamic dispatch based on the Child runtime type, even when executing from the Parent constructor.

**Question 8.** When the Parent constructor calls Child's override, what value does the Child field `int level=9` typically hold if its field initializer has not run yet?  
**Answer:** `0` — the default value of an `int` instance field. The value 9 is assigned later during Child's instance initialization phase.

**Question 9.** Can Child's `String label="READY"` be `null` when an override is called from the Parent constructor?  
**Answer:** Yes. Before Child's initializer runs, the reference field has the default `null`.

**Question 10.** Does `new Child()` create a separate Parent object and a separate Child object?  
**Answer:** No. A single Child object is initialized through the hierarchy's constructor chain.

**Question 11.** Both Parent and Child declare `int value`. Does `((Parent)child).value` always read Child's field?  
**Answer:** No. Field access depends on static type/name lookup; casting to Parent selects Parent's field (if accessible).

**Question 12.** When `CODE` is a static field declared in Parent, does `Child.CODE` necessarily run Child's static block?  
**Answer:** No. Reading the field may initialize only the declaring class Parent.

**Question 13.** If `CODE` is a compile-time constant variable, does reading it require initializing Parent?  
**Answer:** No. The compiler can use the constant value without initializing the declaring class.

**Question 14.** Parent's static initialization throws `IllegalStateException` during the first active use of Child; what error is typically observed?  
**Answer:** `ExceptionInInitializerError`; subsequent uses may produce `NoClassDefFoundError` due to the failed initialization state.

**Question 15.** The Parent constructor throws `IllegalArgumentException` while `super(...)` runs. Does Child's instance initializer proceed?  
**Answer:** No. The constructor chain does not complete, so Child's subsequent steps do not run.

**Question 16.** The Child constructor throws an exception after the Parent constructor prints a log; is the log line from Parent automatically undone?  
**Answer:** No. Prior side effects do not automatically roll back when the Child constructor fails.

**Question 17.** In Java 17, can `System.out.println("x")` be placed before `super()` in a constructor?  
**Answer:** No. The explicit constructor invocation must be the first statement.

**Question 18.** If class Child has static fields, does `Child.class` necessarily execute Child's static block?  
**Answer:** No; a class literal by itself does not require initialization.

**Question 19.** Do interfaces have a `super()` instance constructor like a superclass class?  
**Answer:** No. Interfaces have no constructors; the class constructor chain applies only to classes.

**Question 20.** What should a Parent constructor avoid if Child can override methods?  
**Answer:** Avoid calling overridable methods that depend on uninitialized subclass state; prefer safe private/final logic or calling extension points after the object is completely constructed.

**Question 21.** Parent's `static` block prints before Child's, but are instance blocks printed if only `Child.staticValue` is read?  
**Answer:** No, if no object has been created. Class initialization and object initialization are different.

**Question 22.** Both constructors and static initializers can throw exceptions. Do these two kinds of failure leave the class in the same state afterward?  
**Answer:** No. A class initialization error can leave the runtime class in an erroneous state; a failed constructor invocation does not itself mean class initialization failed.

## 23. References

- Java Language Specification (Java SE 17), [12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): when classes and superclasses are initialized.
- Java Language Specification (Java SE 17), [12.4.1 — When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1): active use, declaring class, and constants.
- Java Language Specification (Java SE 17), [12.4.2 — Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2): initialization procedure and errors.
- Java Language Specification (Java SE 17), [12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): object creation sequence and execution of instance initializers.
- Java Language Specification (Java SE 17), [8.8 — Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8): constructor declarations.
- Java Language Specification (Java SE 17), [8.8.7.1 — Explicit Constructor Invocations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8.7.1): `this(...)`, `super(...)`, and Java 17 rules.
- Java Language Specification (Java SE 17), [8.6 — Instance Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.6): instance blocks.
- Java Language Specification (Java SE 17), [8.7 — Static Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.7): static blocks.
- Java Language Specification (Java SE 17), [15.12.4 — Run-Time Evaluation of Method Invocation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4): how method invocation works, useful when examining dynamic dispatch.

## Conclusion

“**The superclass initializes before the subclass**” holds true in two contexts that must be clearly stated: **static initialization** of the superclass before the subclass, and **constructor/instance initialization** of an object traversing the superclass's portion of state before the subclass's portion. Within each class, instance field initializers and initializer blocks follow source order; that class's constructor body executes at the corresponding step. `this(...)` and `super(...)` define the constructor chain, without creating an independent Parent object.

Most importantly, **the superclass running before the subclass does not mean all subclass fields have already received their initializer values while the superclass is running**. Due to dynamic dispatch, a superclass constructor calling an overridable method can inadvertently access subclass fields that are still `0` or `null`. Design constructors to focus on the state owned by that class level itself, avoid callbacks into subclasses before the object is complete, and clearly distinguish **one-time** class initialization from **per-object** object initialization. This is the foundation for understanding inheritance in Java accurately and avoiding subtle bugs caused by initialization order.
