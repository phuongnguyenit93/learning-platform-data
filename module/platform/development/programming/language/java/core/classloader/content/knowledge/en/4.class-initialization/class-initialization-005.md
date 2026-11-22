# Superclass Initialization and Execution Order of Static Initializers in Java

When a program first uses a class in a way that forces the JVM to perform **class initialization**, Java must set up the static state of that class. With inheritance, **the superclass is initialized before running the normal static initializers of the subclass**. Inside each class, assignments to `static` fields and `static { ... }` blocks are executed in the order they appear in the source code.

This is an important rule when reading application startup logs, analyzing the registration order of static components, or troubleshooting errors that occur in a `static initializer`. However, there are exceptions that must be clearly understood: class loading does not necessarily initialize a class, reading a compile-time constant may not trigger initialization, accessing an **inherited** `static` member usually initializes the class that **declares** the member, and certain **superinterfaces with default methods** may also be initialized before the implementing class.

## 1. How Does Class Initialization Differ from Class Loading and Object Creation?

Three concepts are easily confused:

| Activity | What happens | Must the `static initializer` run? |
| --- | --- | --- |
| **Loading** | The class loader/JVM creates a `Class<?>` definition from the class representation. | Not necessarily. |
| **Linking / preparation** | The JVM verifies/links and allocates static fields with default values; certain constants with `ConstantValue` are handled according to separate rules. | Not yet running the full `static` blocks. |
| **Initialization** | The JVM executes the class initialization procedure, including static field initializers and `static` blocks that need to execute. | Yes, if the class has those operations. |
| **Object construction** | Creates an object, running instance initialization and constructors along the inheritance chain. | Only triggers class initialization if the relevant class definition has not yet been initialized. |

For example, `ClassLoader.loadClass(...)` normally **loads** without requiring class **initialization**; the single-parameter form `Class.forName(name)` normally requires initialization. With `Class.forName(name, false, loader)`, the `false` argument lets you obtain the `Class<?>` without yet requiring the `static initializer` to run.

Do not confuse a `static initializer` with a constructor:

- `static { ... }` and normal assignments to `static` fields run **once per successfully initialized class definition**, and do not run again when additional objects are created.
- Instance initializer blocks `{ ... }`, instance field assignments, and constructors execute for **each object creation**.
- `Class<?>.getClassLoader()` indicates the defining loader. Two loaders defining the same binary name can create two distinct class definitions, each with its own initialization state.

## 2. Main Rule: Superclass First, Subclass After

Suppose there is an inheritance chain:

~~~text
java.lang.Object
       │
       ▼
      Root
       │
       ▼
     Parent
       │
       ▼
      Child
~~~

When an action forces `Child` to be initialized and its superclasses have not yet been initialized, the general order is:

~~~text
Initialize Root (after Object if needed)
      ↓
Initialize Parent
      ↓
Initialize Child
      ↓
Continue the action that requested Child
~~~

More precisely, the JVM executes the **initialization procedure** for the class being used, ensuring that the required superclasses and those superinterfaces covered by the rules are initialized before running the normal initialization of the current class. Any superclass that has already been initialized is skipped; the JVM does not re-run its `static` blocks.

This rule ensures that the necessary static members and initialization assumptions in the superclass are ready when the subclass executes its initializers. **There is no rule that “initializes all subclasses when the parent is used.”** Simply using a member declared by `Parent` generally does not force `Child` to initialize.

To avoid misinterpretation, a specification-level detail should be distinguished: the value of a **constant variable** can be set from the `ConstantValue` attribute in a separate step of the initialization procedure; the “parent before child” rule here refers to **the execution order of normal static assignments and `static` blocks with side effects**, and does not mean every byte of static data in the subclass cannot already hold a value before the parent completes.

## 3. Within Each Class, Static Fields and Static Blocks Run in Textual Order

Within a class, static field initializers and `static` blocks run **from top to bottom**, as if combined into a single block:

~~~java
class Settings {
    static int a = calculateA();

    static {
        System.out.println("middle");
    }

    static int b = calculateB();
}
~~~

This is an **illustrative snippet** to view the order; the two methods `calculateA` and `calculateB` are not defined, so this code is **not a standalone compilable Java file**. If those methods were defined, the order of side effects would be `calculateA()` → print `middle` → `calculateB()`.

For normal data, the JVM first allocates `static` fields and sets **default values** during the preparation phase (`0`, `false`, `null`, depending on the type). Then the initialization process executes coded assignments and `static` blocks in order. Therefore, an initializer can observe the default value of another field in some circular-dependency cases; you must not assume that the final declared value is already present at every point in time.

The **illegal forward reference** rules restrict certain uses of static fields declared later directly within an initializer of the same class. However, indirect dependencies via methods or via another class can still create syntactically valid initialization cycles that are hard to predict at runtime.

### How Do Static Blocks Differ from Constructors?

`static { ... }` is attached to the **class**, does not depend on a specific object, and cannot directly access `this` or `super`. Constructors are executed when constructing an **instance**, after the required classes have been initialized. If `new Child()` is the first action that uses `Child`, **static initialization occurs before** the constructor/instance initialization chain.

## 4. Java 17 Example: Observing the Full Root → Parent → Child Order

Create the file **`StaticOrderDemo.java`** with the full contents:

~~~java
public class StaticOrderDemo {
    private static int mark(String label, int result) {
        System.out.println(label);
        return result;
    }

    static class Root {
        static int rootValue = mark("Root.field", 1);

        static {
            System.out.println("Root.block");
        }
    }

    static class Parent extends Root {
        static {
            System.out.println("Parent.block-1");
        }

        static int parentValue = mark("Parent.field", 2);

        static {
            System.out.println("Parent.block-2");
        }
    }

    static class Child extends Parent {
        static int childValue = mark("Child.field", 3);

        static {
            System.out.println("Child.block");
        }
    }

    public static void main(String[] args) {
        System.out.println("Before Child");
        System.out.println("Value = " + Child.childValue);
        System.out.println("Again = " + Child.childValue);
    }
}
~~~

Compile/run with JDK 17 or newer:

~~~bash
javac --release 17 StaticOrderDemo.java
java StaticOrderDemo
~~~

**Exact stdout:**

~~~text
Before Child
Root.field
Root.block
Parent.block-1
Parent.field
Parent.block-2
Child.field
Child.block
Value = 3
Again = 3
~~~

**Step-by-step explanation:**

1. The JVM initializes `StaticOrderDemo` to run `main`; the three nested classes `Root`, `Parent`, and `Child` **are not automatically initialized along with the outer class**.
2. `Before Child` appears before `Child` is used in a way that requires initialization.
3. Reading `Child.childValue` forces `Child` to initialize. Because `Child` inherits from `Parent`, and `Parent` inherits from `Root`, the JVM executes the initializers of `Root`, then `Parent`, then `Child`.
4. Inside `Parent`, `Parent.block-1` runs **before** the `parentValue` initializer, followed by `Parent.block-2`; `static` blocks do not have absolute priority over `static` assignments—they depend on **textual order**.
5. After the classes are initialized, the field-read expression returns `3`. Reading `Child.childValue` again does not re-run any blocks.

Try changing the declaration order of the two `static` blocks and `parentValue` inside `Parent` and recompiling to see the log change according to the textual order. This changes the execution order of code within the **same class**, while the **parent → child** order remains guaranteed.

## 5. The Class Name Before the Dot Is Not Always the Declaring Class

If `Parent` declares `static int shared` and `Child extends Parent`, the expression `Child.shared` only initializes **Parent** if needed. If `Child` declares its own field with the same name, that is **field hiding**, and the two fields are separate. With `static final int LIMIT = 99` as a constant variable, reading the constant does not by itself trigger initialization.

The lesson **Reading Inherited Static Fields: The Type That Actually Declares the Field** covers member lookup, hiding, `getDeclaringClass()`, and the `getstatic` bytecode separately. In this lesson, what to retain is **the class that actually owns the field/method** in the initialization chain.

## 6. Static Initialization and Constructors in Two Passes

If `new Child()` is the first active use, the static initializers of `Parent` and then `Child` run before the constructors. Then the constructor chain `Parent()` → `Child()` runs for that instance. A second object only re-runs the constructor chain because the classes have already been successfully initialized. The lesson distinguishing `<clinit>`/`<init>` provides a dedicated example of both sequences.

## 7. Important Exception: Superinterfaces with Default Methods

The complete order cannot be explained using the `extends` tree alone. As of Java 17, when a **class** is initialized, the JVM also initializes any **direct or indirect superinterfaces that declare a default method** if they have not yet been initialized. These interfaces are visited in the recursive order defined by the specification. Conversely:

- An interface **without default methods** is not necessarily initialized just because a class implements it.
- Initializing an **interface** by itself **does not trigger initialization of all superinterfaces** that it extends.
- Static methods declared in an interface **are not default methods**. `default` is an implementation of an instance method in an interface.

Observe this with the example **`InterfaceInitDemo.java`**:

~~~java
public class InterfaceInitDemo {
    private static int trace(String label, int value) {
        System.out.println(label);
        return value;
    }

    interface Plain {
        int NUMBER = trace("Plain initialized", 1);
    }

    interface WithDefault {
        int NUMBER = trace("WithDefault initialized", 2);

        default void run() {
            // Does not need to be called for the interface to be initialized with the class.
        }
    }

    static class Impl implements Plain, WithDefault {
        static {
            System.out.println("Impl initialized");
        }
    }

    public static void main(String[] args) {
        System.out.println("Before object");
        new Impl();
        System.out.println("After object");
        System.out.println("Plain number = " + Plain.NUMBER);
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 InterfaceInitDemo.java
java InterfaceInitDemo
~~~

Stdout:

~~~text
Before object
WithDefault initialized
Impl initialized
After object
Plain initialized
Plain number = 1
~~~

`WithDefault` is initialized **before `Impl`** because it declares the default method `run`. `Plain` does not yet need to be initialized at the time of `new Impl()`; it only initializes when `Plain.NUMBER` is accessed. Both interface fields are `public static final` by language rules, but their initializers call the `trace(...)` method, so they are **not compile-time constants** and can be observed during initialization.

**Advanced detail:** With multiple superinterfaces having default methods, the JLS 12.4.2 order uses a **recursive traversal in left-to-right declaration order**, visiting superinterfaces before the interface currently being traversed, after the class's superclass; it is not simply that “an interface written on the left has higher priority than every other ancestor.” There are cases where the compiler generates a **synthetic default method**, which can also affect interface initialization. To understand complex scenarios accurately, inspect the interface graph and `javap -v` output rather than inferring solely from the `implements` line.

## 8. Actions That Do and Do Not Require Class Initialization

Common scenarios (assuming the class is not yet initialized and no other factor forces initialization earlier):

| Action | Result to remember |
| --- | --- |
| `new Child()` | Requires initializing `Child`; necessary superclasses are initialized before the subclass's normal static code. |
| `Child.ownStaticField` (field declared in Child, not a constant variable) | Requires initializing `Child`. |
| `Child.ownStaticMethod()` (method declared in Child) | Requires initializing `Child`. |
| `Child.inheritedStaticField` (field declared in Parent) | Requires initializing the class **that actually declares the field**, without automatically requiring `Child` to initialize. |
| Reading a `static final int` declared with a constant expression | Normally does not force initialization of the declaring class to read the value. |
| `Child.class` | Obtaining a class literal **does not by itself force** initialization. |
| `Class.forName("pkg.Child")` | The standard form requires initializing `Child`. |
| `Class.forName("pkg.Child", false, loader)` | Does not require initialization from this call alone. |
| `loader.loadClass("pkg.Child")` | By the `loadClass` contract, normally loads without initializing. |
| Creating a second instance of `Child` | Does not re-run `static` code of an already successfully initialized `Child`; the constructor still runs. |

This table is a **required behavioral model for when initializers run**, not the actual schedule by which the JVM reads bytecode files. The JVM may load, verify, or resolve a class earlier, as long as it preserves the observable initialization semantics.

## 9. When the Initialization Chain Is Interrupted

If the initializer of a superclass or a required superinterface throws an error, the subclass cannot complete initialization normally. Circular dependencies created by code can read fields that still hold default values; two threads waiting on each other can deadlock. Those are the topics of three separate lessons on **synchronization**, **recursive initialization**, and **failed initialization**. The order in the preceding sections describes the normal success path.

## 10. How to Reason About and Debug Initialization Order

When you see logs that differ from expectations, check in order:

1. **Which class undergoes an “active use” first?** Look for `new`, `invokestatic` (static method calls), `getstatic`/`putstatic` (non-constant-variable fields), reflection, or the `main` entry point.
2. **Where is the static member actually declared?** `Child.shared` may actually be `Parent.shared`; avoid guessing from the dot notation in the source code.
3. **Which superclasses are still uninitialized?** Walk through the superclass chain in order; note any superinterfaces of the class that have default methods.
4. **Within each class, what is the textual order?** Read field initializers and `static` blocks interleaved, rather than grouping all fields first and all blocks afterward.
5. **Are there compile-time constants?** `static final int LIMIT = 10` has different semantics from `static final Integer LIMIT = 10` or `static final int LIMIT = calculate()`.
6. **Are there circular dependencies or initialization errors?** Look for the first exception, `ExceptionInInitializerError`, `NoClassDefFoundError`, or side effects from reading default values.
7. **Are there multiple class loaders or multiple threads?** The same class name with different defining loaders can be two independent definitions; multiple threads may be waiting on initialization.

To observe the bytecode on HotSpot/JDK 17+, run:

~~~bash
javap -c -p StaticOrderDemo
javap -c -p 'StaticOrderDemo$Parent'
~~~

Note that the second command uses single quotes to prevent the shell from interpreting the `$` character in the nested class name on Unix-style shells. On Windows PowerShell, single quotes also preserve the nested class string literally. `javap` can display the special `<clinit>` method, which is where the bytecode for `static` assignments and `static` blocks is combined in compiled order. Use `javap -v -p` when you need to view more metadata.

If you only look at `javap -c` for each individual class, remember that **the ordering across classes comes from the JVM initialization procedure**, not because the `Child.<clinit>` bytecode itself contains all the code of `Parent.<clinit>`.

## 11. Self-Check

**Question 1.** `Child extends Parent`. If `Child` is not yet initialized and a static method declared on `Child` is called, whose `static` block runs first?

**Answer:** If `Parent` is not yet initialized, `Parent`'s normal static initializers run before the corresponding parts of `Child` (and `Parent`'s superclasses even earlier if needed). If `Parent` is already initialized, it does not run again.

**Question 2.** In the same class: `static { A(); }`, followed by `static int x = B();`, and finally `static { C(); }`. What is the order of calls?

**Answer:** `A()` → `B()` → `C()`, in textual order, assuming no errors or side effects trigger another initialization path that alters what is observed.

**Question 3.** Why might `Child.PARENT_FIELD` only print logs from `Parent`?

**Answer:** The field is declared in `Parent`; initialization follows the class **that declares the field** for static field access, not simply the type written before the dot.

**Question 4.** `interface Metrics` has no default methods, yet declares `int X = helper();`. Does creating an object of a class that `implements Metrics` necessarily run the initializer of `Metrics`?

**Answer:** No. An interface without default methods is not forced to initialize just because an implementing class is initialized. Accessing `Metrics.X` will require initialization because `helper()` does not produce a constant variable.

**Question 5.** Does creating a second object from the same class re-run `static` blocks?

**Answer:** No, if the class definition has already been successfully initialized. Instance initializers and constructors still run for the new object.

## Key Takeaways

To accurately predict logs and state when the JVM initializes classes, identify in order **the action that actually forces initialization**, **the class declaring the member**, **the required chain of superclasses and default-method superinterfaces**, and then **the top-to-bottom order of field initializers / static blocks within each class**. A class that has already been successfully initialized is not re-initialized on subsequent uses. Cases that require separate consideration are compile-time constants, circular dependencies, static initializer failures, and different class loaders.

**Authoritative sources for further reference:** Java Language Specification (Java SE 17), §12.4 *Initialization of Classes and Interfaces*, especially §12.4.1–§12.4.2: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4 ; Java Virtual Machine Specification (Java SE 17), §5.5: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
