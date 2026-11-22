# Class Initialization and Superinterfaces Declaring Default Methods

When Java initializes a class, the JVM does not only handle the superclass in the class inheritance hierarchy. Java also initializes the class's superinterfaces that declare `default` methods before running the class's `static` initializers. This rule ensures that the relevant interfaces have already been initialized before the class's code begins executing.

The important point is that **not every interface that a class implements is automatically initialized**. The special rule applies to superinterfaces that declare `default` methods; other interfaces are initialized only when an active use of them occurs.

## 1. When Is a Class Initialized?

*Class initialization* is the process of executing a class's `static` variable initializers and `static` blocks in the order they appear in the source code. This process differs from *instance initialization*, which includes instance field initializers, instance initialization blocks, and constructors.

A class is typically initialized immediately before the first active use of the class occurs, such as:

- Creating an object using `new`.
- Calling a `static` method declared in the class.
- Assigning to a `static` field declared in the class.
- Reading a `static` field declared in the class, if that field is not a compile-time constant variable.

When a class is initialized for the first time, Java performs the steps in this general order:

1. Initialize the superclass first.
2. Initialize the class's superinterfaces that declare `default` methods, in the recursive enumeration order specified by Java.
3. Run the `static` field initializers and `static` blocks of the class itself, in textual order within the class.

If the superclass or a required superinterface has already been initialized previously, Java does not initialize it a second time. A class or interface undergoes initialization only once within the lifetime of its corresponding class loader.

## 2. Why Are Interfaces with Default Methods Handled Specially?

A `default method` is an instance method with a body declared in an interface. It allows implementing classes to inherit a default behavior without having to write that method themselves.

For example:

~~~java
interface Auditable {
    int INITIALIZED = InitLog.mark("Auditable");

    default void audit() {
        System.out.println("audit");
    }
}
~~~

The `INITIALIZED` field is a `public static final` field according to interface rules. Its value is computed by a method call, so it is not a compile-time constant variable. When the `Auditable` interface is initialized, the `InitLog.mark(...)` call will be executed.

If a class implements `Auditable`, class initialization will initialize the `Auditable` interface before running the class's `static` initializers. This holds true even if the program does not call `audit()` during object creation.

Java examines superinterfaces in the recursive inheritance hierarchy, not only the interfaces listed directly on the class. Therefore, if `Child` inherits a `default method` from `Parent`, `Parent` still belongs to the set of interfaces that must be considered when initializing a class that implements `Child`.

Two concepts must be distinguished:

- **Declaring a `default method`:** the interface declares a `default` method itself.
- **Inheriting a `default method`:** the interface receives a default method from a parent interface but does not declare that method itself.

An interface that only inherits a default method without declaring a `default method` itself is not selected solely because it inherits that method. However, the parent interface that actually declares the default method is still evaluated separately during superinterface traversal.

## 3. Runnable Java 17+ Example

Save the following program to the file `DefaultInterfaceInitialization.java`.

~~~java
class InitLog {
    static int mark(String name) {
        System.out.println(name);
        return 0;
    }
}

class Base {
    static int initialized = InitLog.mark("Base");
}

interface PlainParent {
    int initialized = InitLog.mark("PlainParent");
}

interface RootDefault {
    int initialized = InitLog.mark("RootDefault");

    default void root() {
    }
}

interface ChildWithDefault extends PlainParent, RootDefault {
    int initialized = InitLog.mark("ChildWithDefault");

    default void child() {
    }
}

interface Marker {
    int initialized = InitLog.mark("Marker");
}

class Sample extends Base implements ChildWithDefault, Marker {
    static int initialized = InitLog.mark("Sample");
}

public class DefaultInterfaceInitialization {
    public static void main(String[] args) {
        System.out.println("start");

        new Sample();
        System.out.println("instance ready");

        // The second instantiation of Sample does not re-run the initializers.
        new Sample();

        // Marker does not declare a default method, so it is only initialized
        // when a non-constant field of the interface itself is read.
        System.out.println("Marker value=" + Marker.initialized);
        System.out.println("PlainParent value=" + PlainParent.initialized);
    }
}
~~~

Compile and run with JDK 17 or later:

~~~text
javac DefaultInterfaceInitialization.java
java DefaultInterfaceInitialization
~~~

Expected output:

~~~text
start
Base
RootDefault
ChildWithDefault
Sample
instance ready
Marker
Marker value=0
PlainParent
PlainParent value=0
~~~

### Reading the Output in Order

**`start` appears first.** No operation requiring the initialization of `Sample` has occurred yet, so the initializers have not run.

**`Base` appears first.** The `new Sample()` statement requires initializing the `Sample` class, so the superclass `Base` is initialized first. The `Base.initialized` field calls `InitLog.mark("Base")`, producing the line `Base`.

**`RootDefault` appears before `ChildWithDefault`.** `Sample` implements `ChildWithDefault`; this interface declares a `default method`. When traversing the superinterfaces, Java encounters `RootDefault`, which also declares a `default method` itself, before initializing `ChildWithDefault`. Both interfaces are initialized before the `static` part of `Sample`.

**`Sample` appears after the qualifying interfaces.** At this point, the superclass and the superinterfaces requiring initialization have finished, so `Sample`'s `static` field is now processed.

**`instance ready` appears after `new Sample()` completes.** Object creation completes only after the class has been initialized and instance initialization has finished running.

**The second `new Sample()` does not print any additional initialization lines.** Java does not re-run initializers once the class has been successfully initialized.

**`Marker` and `PlainParent` appear only at the end.** These two interfaces do not declare a `default method` themselves, so they are not automatically initialized merely because `Sample` implements or indirectly inherits them. Reading each interface's `initialized` field is an active use of a non-compile-time-constant `static` field, so it triggers the initialization of the corresponding interface.

The `initialized` fields in the interfaces are `public static final`, but they are not compile-time constant variables because their values come from method calls. Therefore, reading them actually triggers interface initialization.

## 4. Initializer Order Within a Type

When a class or interface begins initialization, the initializers of that type itself run in the order they appear in the source code. For example:

~~~java
class Example {
    static int first = log("first");

    static {
        log("static block");
    }

    static int last = log("last");

    static int log(String message) {
        System.out.println(message);
        return 0;
    }
}
~~~

When `Example` is initialized, the order is:

~~~text
first
static block
last
~~~

For a class with a superclass and superinterfaces that declare a `default method`, the outer order is: the superclass, the qualifying superinterfaces in the specified order, and then the class's `static` initializers. Within each type, that type's own initializers still follow textual order.

## 5. Direct Interface Initialization Differs from Class Initialization

An interface can also be initialized by an active use of the interface itself, such as calling its `static` method or reading a `static` field that is not a compile-time constant variable.

However, **initializing an interface directly does not automatically initialize all of its superinterfaces**. The rule for initializing superinterfaces with a `default method` applies when initializing a class. Do not infer that every parent interface is initialized whenever a child interface is used.

A `static final` field with a compile-time constant value, such as `int LIMIT = 10`, can be replaced directly with its constant value by the compiler. Merely reading such a field does not trigger initialization of the interface that declares it. Conversely, a field assigned via a method call such as `int value = compute()` is not a compile-time constant variable, so reading the field triggers initialization of the interface.

## 6. Common Mistakes

- **Assuming all interfaces are initialized along with the class:** Java automatically handles the superclass and superinterfaces that declare a `default method`. Remaining interfaces may still be uninitialized.
- **Assuming a `default method` must be called for the interface to be initialized:** this is incorrect. Initializing the implementing class already causes qualifying superinterfaces to be initialized, even if the default method has not been called.
- **Confusing class initialization with instance initialization:** `static` initializers run when the class is initialized; instance initializers and constructors run during the creation of each object.
- **Forgetting the order among the superclass, interfaces, and the class:** a subclass's `static` initializers do not run before the superclass and the superinterfaces that require initialization.
- **Assuming a parent interface always initializes before a child interface is used:** directly initializing an interface does not automatically trigger all of its superinterfaces. Identify the active use and distinguish it from the initialization process of a class.
- **Confusing `static final` with a compile-time constant:** `final` is not enough to conclude that a field is a constant variable. The value must be a constant expression according to Java rules; a method call does not satisfy that condition.

## 7. Process for Analyzing a Scenario

When you need to determine the print order from initializers, follow these steps:

1. Identify which operation triggers class or interface initialization.
2. If it is a class, identify the superclass and the superinterfaces in the recursive inheritance hierarchy that declare a `default method` themselves.
3. Mark types that have already been initialized previously; they do not re-run their initializers.
4. Record the initialization order of the superclass, the qualifying superinterfaces, and then the class's `static` initializers.
5. Within each type, read the `static` field initializers and `static` blocks in textual order.
6. Only after completing class initialization, consider instance initialization and constructors if the initial operation was `new`.

This analysis approach helps accurately predict initialization order, avoid bugs that depend on initializer order, and understand why some interfaces are initialized earlier than others.
