# Do Not Instantiate Abstract Classes or Interfaces via Ordinary Constructors in Java Reflection

## 1. Understanding Constructor Boundaries Correctly

In Java, an **abstract class** is a class not permitted to be instantiated directly; an **interface** is a type contract, not a class with ordinary constructors. Reflection can read metadata of these types, yet **it does not make them directly instantiable types**.

```java
abstract class Animal {
    protected Animal() { }
    abstract String sound();
}

interface Movable {
    void move();
}
```

These statements are both invalid at compile time:

```java
// ILLUSTRATIVE CODE THAT DOES NOT COMPILE
// Animal animal = new Animal();    // Animal is an abstract class.
// Movable movable = new Movable(); // Movable is an interface.
```

Similarly, using Reflection to look up a `Class` or constructor **cannot bypass** this restriction. You must create an instantiable **concrete class**, then reference that object through the abstract class/interface type if needed.

**Distinguishing the two cases:**

- An abstract class **can declare constructors**; such a constructor executes while constructing an object of a concrete subclass. However, an abstract class's `Constructor` **cannot** create an instance of the abstract class itself.
- An interface **has no constructors**. You cannot find a `Constructor<Interface>` of an interface, even with `getDeclaredConstructor()`.

## 2. Related Reflection APIs

| Operation | Abstract class | Interface |
| --- | --- | --- |
| `SomeType.class`, `Class.forName(...)` | Retrieves `Class` metadata normally | Retrieves `Class` metadata normally |
| `Class.isInterface()` | `false` | `true` |
| `Modifier.isAbstract(type.getModifiers())` | `true` | Also typically `true` because interfaces carry the `abstract` flag |
| `getDeclaredConstructors()` | May return constructors declared in the abstract class | Empty array |
| `getDeclaredConstructor(parameterTypes...)` | Can find a constructor matching signature | Throws `NoSuchMethodException` |
| `getConstructor(parameterTypes...)` | Can find a `public` constructor of the abstract class | Throws `NoSuchMethodException` |
| `Constructor.newInstance(args...)` | Cannot instantiate abstract class; may throw `InstantiationException` | No interface constructor to invoke |
| Instantiating a concrete implementation class | Yes, via a constructor of the **concrete subclass** | Yes, via a constructor of the **concrete implementing class** |

`getDeclaredConstructor(...)` only **looks up declarations**, whereas `Constructor.newInstance(...)` **asks the JVM to create an object**. Finding a constructor does not mean invoking that constructor to create an instance is valid.

Constructors **are not inherited**: `Child.class.getConstructor(...)` only looks up public constructors declared for `Child` per API rules, and does not use `Parent`'s constructor to create `Child`. A subclass object is built by the subclass constructor with the parent constructor invoked in the `super(...)` chain.

## 3. Why Do Abstract Classes Still Have Constructors?

An abstract class's constructor serves to initialize shared state needed by all subclasses.

```java
abstract class Job {
    protected final String name;

    protected Job(String name) {
        this.name = name;
    }

    abstract String run();
}

class EmailJob extends Job {
    EmailJob(String name) {
        super(name); // Calls the constructor of the Job part inside the EmailJob object.
    }

    @Override
    String run() {
        return "EmailJob: " + name;
    }
}
```

At `new EmailJob("daily")`, the JVM creates an object with **runtime class `EmailJob`**, while executing `Job(String)` in the initialization chain. There is no standalone object whose exact runtime class is abstract `Job`.

Reflection finds `Job.class.getDeclaredConstructor(String.class)`, but **calling `newInstance("daily")` on that `Constructor<Job>` does not create an `EmailJob`**. The JVM does not guess a subclass for you. It refuses to create an instance of an abstract type.

## 4. Complete and Runnable Java 17+ Example

Save the following program verbatim as `AbstractConstructorDemo.java`:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Modifier;

public class AbstractConstructorDemo {
    public static abstract class Job {
        protected final String name;

        public Job(String name) {
            this.name = name;
        }

        public abstract String run();
    }

    public interface Work {
        String run();
    }

    public static final class RealJob extends Job implements Work {
        public RealJob(String name) {
            super(name);
        }

        @Override
        public String run() {
            return "run:" + name;
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("Job abstract: "
                + Modifier.isAbstract(Job.class.getModifiers()));

        Constructor<Job> baseCtor =
                Job.class.getDeclaredConstructor(String.class);
        System.out.println("Job constructor parameters: "
                + baseCtor.getParameterCount());

        try {
            baseCtor.newInstance("x");
        } catch (InstantiationException e) {
            System.out.println("Job newInstance: InstantiationException");
        }

        System.out.println("Work interface: " + Work.class.isInterface());
        System.out.println("Work constructors: "
                + Work.class.getDeclaredConstructors().length);

        try {
            Work.class.getDeclaredConstructor();
        } catch (NoSuchMethodException e) {
            System.out.println("Work lookup: NoSuchMethodException");
        }

        Constructor<RealJob> realCtor =
                RealJob.class.getConstructor(String.class);
        Job asJob = realCtor.newInstance("demo");
        Work asWork = (Work) asJob;

        System.out.println("concrete class: "
                + asJob.getClass().getSimpleName());
        System.out.println("job call: " + asJob.run());
        System.out.println("interface call: " + asWork.run());
    }
}
```

Run with JDK 17 or later:

```bash
javac AbstractConstructorDemo.java
java AbstractConstructorDemo
```

Stdout:

```text
Job abstract: true
Job constructor parameters: 1
Job newInstance: InstantiationException
Work interface: true
Work constructors: 0
Work lookup: NoSuchMethodException
concrete class: RealJob
job call: run:demo
interface call: run:demo
```

**Output explanation:**

1. `Modifier.isAbstract(Job.class.getModifiers())` confirms `Job` is abstract.
2. `Job.class.getDeclaredConstructor(String.class)` still finds the one-parameter constructor.
3. `baseCtor.newInstance("x")` fails with `InstantiationException` because the declaring type is abstract; the fact that the constructor exists and was looked up properly does not change that.
4. `Work.class.isInterface()` returns `true`; `getDeclaredConstructors()` has length `0`. Looking up a no-arg constructor on an interface throws `NoSuchMethodException`.
5. `RealJob` is a concrete class with constructor `public RealJob(String)`. `realCtor.newInstance("demo")` creates an actual object with runtime class `RealJob`.
6. The `RealJob` object can be referenced as `Job` and `Work`. The reference variable's type **is not** proof that the JVM directly created an instance of an abstract class/interface.

In the example, `Job`'s constructor is declared `public` so access checks do not mask the error being studied. If an abstract class's constructor is `protected` or `private`, Reflection access rules can trigger `IllegalAccessException` or another permission error **before** reaching the instantiability check.

## 5. Three Error Groups to Distinguish

When working with constructors, errors can happen at **different stages**:

| Stage | Case | Typical outcome |
| --- | --- | --- |
| Lookup | `Interface.class.getDeclaredConstructor()` | `NoSuchMethodException` because interfaces have no constructors |
| Lookup | Looking up a wrong constructor signature of a class, e.g. `RealJob.class.getConstructor(int.class)` | `NoSuchMethodException` because only `RealJob(String)` exists |
| Instantiation | `Job.class.getDeclaredConstructor(String.class).newInstance("x")` | `InstantiationException` because `Job` is abstract |
| Access permission | Constructor exists, but caller is not permitted to use it | `IllegalAccessException` or access error depending on context |
| Argument check | Invalid argument count/types when calling `newInstance` | `IllegalArgumentException` |
| Running constructor | Concrete constructor executes and throws an exception | `InvocationTargetException` containing the root cause |

Do not catch only `NoSuchMethodException` for the entire workflow. That error belongs to the **lookup step**; `InstantiationException` happens at the **creation step**, once constructor metadata has already been obtained.

`Constructor.newInstance(...)` can throw checked exceptions such as `InstantiationException`, `IllegalAccessException`, `InvocationTargetException`, alongside argument/access exceptions. When writing library code, handle each error according to its meaning instead of repeatedly retrying the same constructor on an abstract class.

## 6. Checking the Type Before Selecting a Constructor

When a class is provided via configuration, annotation scanning, or `Class.forName`, verify the type's concreteness before attempting instantiation:

```java
// Standalone helper method placed in a Java class; illustrates only the check step.
static boolean isConcreteClass(Class<?> type) {
    int modifiers = type.getModifiers();
    return !type.isInterface()
            && !java.lang.reflect.Modifier.isAbstract(modifiers)
            && !type.isPrimitive()
            && !type.isArray()
            && !type.isAnnotation();
}
```

This step separates abstract classes and interfaces from ordinary classes, yet **is not enough to guarantee every remaining `Class<?>` can be instantiated**. For example: the class may lack a matching constructor; the constructor may be inaccessible; enums restrict instantiation via Reflection; `void.class` also does not represent an instantiable class. `Class.isInterface()` is the direct signal to distinguish interfaces, since checking only `Modifier.isAbstract(...)` lumps interfaces together with abstract classes.

A more practical workflow:

1. Check `type.isInterface()` and `Modifier.isAbstract(type.getModifiers())`. If either is true, **do not use a constructor on that type itself**.
2. Determine the concrete class to create from configuration or a known contract; check `expectedType.isAssignableFrom(concreteType)` to confirm compatibility.
3. Use `concreteType.getDeclaredConstructor(parameterTypes...)` or `getConstructor(...)` per the required scope, passing exact parameter types.
4. Check constructor accessibility; do not assume permission to open internal modules/packages.
5. Call `newInstance(args...)` on a constructor **of the concrete class** and handle execution errors.

**Do not infer** that a subclass is selected merely by calling `getConstructor` on an abstract class: finding a concrete subtype is the responsibility of the application or container/DI, not `Constructor.newInstance`.

## 7. Using an Abstract Class/Interface as a Reference Type Is Completely Valid

Some code patterns can mislead beginners into thinking they "created an interface" or "created an abstract class".

### 7.1. Concrete Subclass

```java
// When the RealJob class is present in a complete program:
Job job = new RealJob("billing");
Work work = (Work) job;
```

`new` instantiates `RealJob`. Both variables simply hold references assigned according to inheritance/implements rules.

### 7.2. Anonymous Subclass of an Abstract Class

```java
// Placed in a method that can access AbstractConstructorDemo.Job:
AbstractConstructorDemo.Job anonymous =
        new AbstractConstructorDemo.Job("one-off") {
            @Override
            public String run() {
                return "anonymous:" + name;
            }
        };
System.out.println(anonymous.run()); // anonymous:one-off
```

The syntax `new AbstractConstructorDemo.Job(...) { ... }` creates a **concrete anonymous subclass** with implementations of the abstract methods. It **does not** directly create an object whose runtime class is `Job`. This snippet is illustrative, not a standalone program.

### 7.3. Lambda for a Functional Interface

```java
// Work is an interface with a single abstract method as in the program in section 4.
AbstractConstructorDemo.Work action = () -> "lambda";
System.out.println(action.run()); // lambda
```

A lambda supplies an object implementing a functional interface through Java's language mechanism; **the `Work` interface does not itself have a constructor**. If an interface has multiple abstract methods and is not a functional interface, lambda syntax is invalid.

### 7.4. Dynamic Proxy

`java.lang.reflect.Proxy.newProxyInstance(...)` can create a **proxy object implementing an interface** backed by an `InvocationHandler`, yet the object's runtime class is a runtime-generated proxy class, not the interface itself. This is a dynamic implementation generation technique, **different from** invoking an interface constructor. Do not use a proxy as the default replacement for designing a concrete implementation when dynamic behavior is unnecessary.

## 8. Role of the Parent Constructor Under Inheritance

Standard initialization order when calling `new RealJob("demo")`:

```text
RealJob(String) is selected as the target constructor
    |
    v
super(name) calls Job(String)
    |
    v
Job initializes name
    |
    v
RealJob completes construction
    |
    v
Object has runtime class RealJob
```

That is why an abstract class needs and can have constructors: **the parent class must set up the shared state portion** for subclass objects. Java forbids **directly instantiating an abstract class**, but does not forbid its constructor from participating in a valid initialization chain.

One design note: an abstract class constructor should not call overridable methods if those methods depend on state that the subclass has not yet initialized. Dynamic dispatch rules can trigger the subclass implementation too early while the parent constructor is still running.

## 9. Common Errors and How to Handle Them

| Symptom / Misconception | Cause | How to handle |
| --- | --- | --- |
| `getDeclaredConstructor` succeeds, but `newInstance` throws `InstantiationException` | Using a `Constructor` of an abstract class | Select a constructor of a concrete subclass |
| `Interface.class.getDeclaredConstructor()` throws `NoSuchMethodException` | Interfaces declare no constructors | Pick an implementing class or suitable implementation-creation mechanism |
| Thinking an abstract class cannot have constructors | Confusing object-creation restrictions with constructor declarations | Abstract class constructors serve subclass construction |
| Thinking calling `abstractType.getConstructor(...)` automatically finds a subclass | Reflection lookup does not pick subclasses | Identify the concrete class explicitly |
| Thinking `Class.forName("...")` instantiates an interface | `Class.forName` retrieves/loads `Class` and may initialize the class per API semantics, not create an instance of the type | Distinguish `Class` metadata from an implementation object |
| Checking `Modifier.isAbstract` to tell the two apart | Interfaces also carry the `abstract` modifier | Check `isInterface()` first |
| Subclass constructor does not call parent constructor | Java constructors must lead to a `super(...)` or `this(...)` call, explicitly or implicitly | Check the constructor chain and parent constructor signatures |
| Using legacy `Class.newInstance()` to avoid errors | Old API is deprecated; cannot bypass abstract/interface | Use `getDeclaredConstructor(...).newInstance(...)` on a concrete type |
| Creating a proxy and concluding interfaces have constructors | Proxy generates a dynamic implementation class | Check `object.getClass()`; understand a proxy is an implementation |

**Key takeaway:** **An abstract class can have constructors yet cannot be instantiated directly; an interface has no constructors.** Reflection faithfully reflects both rules. Always obtain a `Constructor` of an **instantiable concrete class**, then use the abstract class/interface as a reference type where appropriate.

References: [Java SE 17 `Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html), [`java.lang.reflect.Constructor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html), [JLS §8.1.1.1 — abstract Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.1).