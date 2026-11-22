# How Does Class Lifecycle Differ from Object Lifecycle in Java?

## 1. Two Different Lifecycles, Yet Related

In Java, a **class** is a type definition that the JVM loads, links, and initializes so that the program can use fields, methods, constructors, and create instances. An **object (instance)** is a concrete entity created when the program executes `new` or an appropriate allocation mechanism. The two concepts have different existence milestones and termination conditions.

A class can already be initialized even when **no instances exist yet**; conversely, there can be millions of instances of the same class while the class's `static` initialization block runs **only once per runtime class identity**, provided the initialization succeeds. In contrast, constructors and instance initializers run for **each instance creation under normal object initialization**.

| Criterion | Class Lifecycle | Object Lifecycle |
|---|---|---|
| Managed entity | Runtime type definition, bound to a class loader | A concrete instance of the type |
| Typical starting point | JVM loads the type when needed | Object allocation (usually via `new`) |
| Core phases | Loading → linking → initialization; later, possible unloading | Allocation → default values → instance initialization/constructor → usage → eligible for GC |
| Initialization code execution | `static` initializer/field initializer, once per successful initialization of the class identity | Instance field initializer, instance initializer, and constructor per creation |
| State | Static fields belong to the runtime class, shared across corresponding instances | Instance fields hold the state of each individual object |
| Termination | Class unloading when eligible and the JVM chooses to perform it | When an object is no longer reachable, the JVM **may** collect it |
| Depends on class loader? | Yes: the same name with different defining loaders can be two distinct runtime classes | An instance has a runtime type determined by the class to which it belongs |

> **Do not equate** "no objects of the class remain" with "the class is unloaded." The JVM is not required to unload a class immediately when no instances remain, and garbage collection does not run on a fixed schedule that an application can rely on.

## 2. Object Lifecycle: Creation, Usage, and Potential Collection

After the type has been appropriately prepared/initialized, a `new` call typically leads to:

```text
new Widget(...)
    |
    v
Ensure the relevant class is initialized per JVM rules
    |
    v
Allocate memory and assign default values to instance fields
    |
    v
Run constructor chain: superclass -> subclass
    |    (instance field initializers and instance initializer blocks
    |     are executed in each class in the required order)
    v
Instance is ready for use
    |
    v
No longer strongly reachable from GC roots
    |
    v
Eligible for collection by the garbage collector, depending on the JVM/GC
```

Key points:

- **Each normal `new` creates a new object** (except where the JVM may optimize based on observable semantics; do not rely on physical allocation location).
- **Instance fields** belong to each individual object. Assigning `a.name` does not change `b.name` of another object, unless the two references point to the same object or the fields point to the same mutable object.
- **Instance initializers** and constructors run during normal object creation; an object does not re-run its constructor simply when reading/writing fields or when GC operates.
- A constructor is **not** the `<clinit>` method. In a class file, a constructor is represented as `<init>`; `<clinit>` is the separate class initialization method.
- **Reachability** is what matters for GC: a local variable going out of scope does not mean the object is immediately collected; conversely, assigning `null` to one variable does not guarantee the object has no other strong references.
- `System.gc()` is only a suggestion for collection; it does not guarantee that a specific object will be collected or that finalizers/cleaners will run immediately.

Multiple variables can hold references to the same object:

```java
Widget a = new Widget("first");
Widget b = a;        // two references, only one object
a = null;            // b still keeps the object reachable
// b = null;          // may lose the last strong reference,
//                     // but the timing of GC remains indeterminate
```

The snippet above is for **illustration only**; it needs to be placed in a program with a `Widget` definition to compile.

### Does Every Object Go Through a Constructor?

With `new` in normal Java source code, the constructor chain is executed. However, you should not generalize this to "every object the JVM creates directly invokes a Java constructor": for example, arrays created with `new int[10]`, objects created by certain deserialization mechanisms, or internal runtime mechanisms have different initialization semantics. The main takeaway is that **the individual lifecycle of each instance** is not identical to the one-time initialization of the class.

## 3. Java 17 Demo: Class Initialized Once, Objects Initialized Multiple Times

Create the file `LifecycleDemo.java`:

```java
public class LifecycleDemo {
    static class Widget {
        static int created;

        static {
            System.out.println("Widget: static init");
        }

        final String name;

        {
            System.out.println("Widget: instance init");
        }

        Widget(String name) {
            this.name = name;
            created++;
            System.out.println("Widget: constructor " + name);
        }

        static void ping() {
            System.out.println("Widget: ping");
        }
    }

    public static void main(String[] args) {
        System.out.println("Start");

        Class<?> type = Widget.class;
        System.out.println("Class literal: " + type.getSimpleName());

        Widget.ping();

        Widget first = new Widget("A");
        Widget second = new Widget("B");

        System.out.println("Same Class: "
                + (first.getClass() == second.getClass()));
        System.out.println("Constructed: " + Widget.created);

        first = null;
        second = null;
        System.out.println("References cleared");
    }
}
```

Run with JDK 17 or later:

```bash
javac LifecycleDemo.java
java LifecycleDemo
```

Stdout:

```text
Start
Class literal: Widget
Widget: static init
Widget: ping
Widget: instance init
Widget: constructor A
Widget: instance init
Widget: constructor B
Same Class: true
Constructed: 2
References cleared
```

Reading the output in order:

1. `Widget.class` lets you obtain the `Class` object and call `getSimpleName()` without **triggering** static initialization on its own. Therefore, `Class literal: Widget` appears before `Widget: static init`.
2. `Widget.ping()` is a static method call; before running the method, the class is initialized, so the static block prints **once**.
3. For each `new Widget(...)` statement, the instance initializer and constructor run **once more for the new object**. The static block does not run again.
4. `first.getClass() == second.getClass()` prints `true` because both instances share the same runtime class identity.
5. `Widget.created` is the **total number of objects created by the written constructor**, not the number of objects guaranteed to still be alive. After setting both references to `null`, the counter remains `2` because it is static state.
6. The line `References cleared` does not prove that GC has collected the two objects. GC was not invoked directly, nor can the collection timing be inferred from stdout.

Distinguish the three entities in the example:

- **Runtime class `LifecycleDemo.Widget`**: where the class loading/linking/initialization rules apply.
- **`Class<?> type`**: a reference to the `Class` object reflecting the runtime class definition, not a `Widget` instance created by `new Widget`.
- **`first` and `second`**: two references to two separate `Widget` instances.

## 4. Can a Class Exist Without Any Instances?

**Yes.** For example, `Math` has static methods, or a user-defined utility class can operate without needing an instance of that class itself. Having only a class literal, reflection metadata, or static state does not mean an object of that class has been created.

A runtime class typically continues to exist as long as there are still things keeping it or its class loader reachable. On JVMs that support class unloading, the condition for collection/class unloading is tied to whether the **defining class loader can be collected by GC**. Besides the class loader itself, references to `Class<?>`, instances, method/field reflection objects, thread context class loaders, or cache structures can extend the lifetime of the loader and the classes it defines.

Do not think "when all objects end their lifecycle, the class ends its lifecycle":

```text
t0: Load + initialize class A
t1: Create object a1
t2: Create object a2
t3: a1 is no longer reachable, eligible for GC
t4: a2 is no longer reachable, eligible for GC
t5: Class A remains in the runtime because of the loader and related metadata
t6: If the loader can truly be reclaimed and the JVM decides to unload,
    the classes defined by the loader may be unloaded
```

The milestones t3/t4/t6 are **possibilities**, not guarantees about timing. Classes defined by the bootstrap class loader typically stay alive for the entire lifetime of the JVM.

### Class Unloading Is Not the Same as Instance Garbage Collection

The garbage collector can reclaim the memory of individual objects when they are no longer reachable **without needing to unload their class**. Conversely, unloading a class from the JVM is an operation at the metadata/runtime class and class loader level. In a long-running JVM—such as a server that continuously hot-reloads plugins—a classloader leak can keep old metadata alive even when the application logic assumes the plugin has been removed.

Common sources of references that keep a class loader alive include still-running threads with an old thread context class loader, uncleaned `ThreadLocal`s, static caches from long-lived code holding `Class<?>` or plugin instances, or unregistered callbacks/listeners. This cannot be fixed merely by setting `someObject = null` if another reference path still exists.

Note also: `Class<?>` **is itself a Java object**, but it represents a runtime type; collecting the `Class` object and unloading the type are governed by reachability relationships with the class loader and runtime metadata. Do not treat every `Class<?>` as an instance created by the represented type's constructor.

## 5. Inheritance: Order of Static Initialization and Constructor Chain

A common question is: "When calling `new Child()`, whose static block and constructor does the JVM run first?"

Meaningful rules:

- Required superclasses are guaranteed to be initialized before the subclass is initialized; static initializers belonging to each class run once when that class is initialized.
- For **each** new `Child` instance, the superclass constructor is invoked in the constructor chain before the subclass constructor body, following `super(...)`/`this(...)` mechanics and instance initializer rules.
- If `new Child()` is called multiple times, the constructor chain runs multiple times; static initializers do not re-run for classes that have already been successfully initialized.

Runnable program—create the file `InheritanceLife.java`:

```java
public class InheritanceLife {
    static class Parent {
        static {
            System.out.println("Parent static");
        }

        {
            System.out.println("Parent instance");
        }

        Parent() {
            System.out.println("Parent constructor");
        }
    }

    static class Child extends Parent {
        static {
            System.out.println("Child static");
        }

        {
            System.out.println("Child instance");
        }

        Child() {
            System.out.println("Child constructor");
        }
    }

    public static void main(String[] args) {
        new Child();
        System.out.println("---");
        new Child();
    }
}
```

Run:

```bash
javac InheritanceLife.java
java InheritanceLife
```

Stdout:

```text
Parent static
Child static
Parent instance
Parent constructor
Child instance
Child constructor
---
Parent instance
Parent constructor
Child instance
Child constructor
```

The first `new Child()` causes both the parent and child classes to be initialized according to JVM rules; the two constructor chains then execute per instance. The second call only runs the instance initialization/constructor parts.

## 6. Applications in Design and Diagnostics

- **Designing static state:** remember that static caches/counters live tied to the class identity, often outliving the objects that use them; consider avoiding unnecessary references to stopped class loaders/modules.
- **Reflection/frameworks:** distinguish between obtaining type metadata and actually performing initialization. Initializing classes that have side effects (opening connections, registering callbacks, reading config) during plugin scanning can trigger behavior earlier than intended; choose APIs with an `initialize` flag when control is needed.
- **Startup performance:** loading, linking, and initializing classes incur different costs; measure the exact phase you need to optimize, and do not assume every class load has run every static initializer.
- **Resource management:** a constructor may open files/sockets, but GC is not a reliable closing mechanism; use `AutoCloseable` and `try-with-resources` when resources need prompt release.
- **Hot redeploy and plugins:** check threads, executors, listeners, `ThreadLocal`, host-side caches, and reflection references holding onto old classes/loaders before concluding that the JVM "cannot unload classes."
- **Reading errors:** `ClassNotFoundException` is typically tied to a failed request to find a class; `NoClassDefFoundError` can also be related to a linking or initialization error that occurred earlier. Do not infer from the exception name that the JVM "never loaded" the class.

With HotSpot, you can observe class loading/unloading activity using Unified Logging (`-Xlog:class+load=info,class+unload=info`), or use `jcmd <pid> VM.classloader_stats` to inspect loader statistics on JVMs that support this command. Results depend on the JVM version, process state, and attach permissions; these tools aid investigation rather than turning unload timing into a guarantee.

## 7. Self-Check Exercises

**Question 1.** If you evaluate `A.class` and then call `new A()` twice, how many times does `A`'s static block run, and how many times does its constructor run?

**Answer:** Assuming `A` was not previously initialized and initialization succeeds, the static block runs once (when active use causes the class to be initialized); the normal constructor runs twice. `A.class` by itself does not require initialization.

**Question 2.** Two objects `a` and `b` both belong to class `Foo`. Once both become eligible for GC, is class `Foo` guaranteed to be unloaded?

**Answer:** No. The class/loader may still be reachable from many places, and the JVM does not promise unloading at a deterministic time.

**Question 3.** Two plugins have a class with the same binary name `org.example.Task` defined by two different defining loaders. `Task.counter` is a static field. Do they share the same `counter`?

**Answer:** No. They are two different runtime classes, so they have separate static state even though the type name in source code is identical.

**Question 4.** How are `Class.forName("com.example.Service", false, loader)` and `Class.forName("com.example.Service")` similar, and how do they differ?

**Answer:** Both aim to find the class with the specified binary name and return a `Class<?>` if successful. The three-argument overload with `false` does not require initialization; the single-argument overload requires initialization and uses the caller's loader per the API. Whether the two calls actually refer to the same runtime class also depends on the loader.

**Question 5.** Do `static final int CODE = 7` and `static final Integer CODE = 7` necessarily trigger initialization the same way when the field is read from another class?

**Answer:** No. An `int` field that is a compile-time constant may be inlined without triggering initialization; `Integer` is not a constant variable of a primitive type or `String` according to the JLS, so a normal static field access can trigger initialization of the declaring class.

**Question 6.** Why does `Widget.created` remain `2` in the `LifecycleDemo` example after `first` and `second` are set to `null`?

**Answer:** It is a static counter of how many times the constructor has incremented it, not a live-object counter. GC does not automatically decrement that field, even if the two objects are actually collected.

## 8. Key Takeaways and References

**Remember along two independent axes:**

- **Class:** load/link/initialize per JVM rules; initializes static state and `<clinit>`; identity is tied to the defining class loader; may be unloaded when the loader becomes eligible.
- **Object:** allocation, instance initialization, and constructor; stays alive according to reachability; eligible for GC when no longer reachable, though collection timing is not guaranteed.
- **Relationship:** one runtime class can create many objects; a successfully initialized class does not need to re-initialize for each new object; instance collection does not automatically end the class's lifecycle.

Authoritative documentation for exact rules:

- [Java Language Specification 17, Chapter 12 — Execution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html): loading, linking, initialization, instance creation, and class lifetime termination.
- [Java Virtual Machine Specification 17, Chapter 5 — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): loader semantics, class identity, preparation, resolution, initialization, and unloading.
- [Java SE 17 — Class.forName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): overloads involving the `initialize` flag and class loader.
- [Java SE 17 — System.gc()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html): suggestion for collection, with no guarantee of immediate execution.