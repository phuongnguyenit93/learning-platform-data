# Identifying `abstract`, `final`, `synchronized`, and `native` on Methods in Java

## 1. What Do These Four Keywords Say About a Method?

A Java method declaration consists of more than just a return type, name, and parameters. The **modifiers** before the return type can determine whether the method must be implemented, whether it can be overridden, whether it acquires a synchronization lock at runtime, or whether its implementation resides outside Java.

Four modifiers to distinguish:

| Modifier | Primary meaning | Has a Java body `{ ... }` in the corresponding declaration? | Execution/implementation | Things to remember |
| --- | --- | --- | --- | --- |
| `abstract` | Declares only the contract of an **instance method**, without providing an implementation | **No**; ends with `;` | A concrete subclass must implement it (unless it has already inherited a suitable implementation) | Cannot simultaneously be `private`, `static`, `final`, `synchronized`, or `native` |
| `final` | Prevents subclasses from **overriding** the method | Yes, if it is a regular Java concrete method; can be combined with `native` | Uses the existing implementation (and can be overloaded) | `final` does not make the object immutable and does not prohibit calling the method |
| `synchronized` | When invoked, the JVM acquires the corresponding **monitor lock** before executing the method | Yes for regular Java methods; can also be combined with `native` | Executes with the lock of the **receiver** (instance) or **Class object** (static) | Only synchronizes with code using the **same monitor**; does not by itself ensure the entire design is thread-safe |
| `native` | Declares a method whose implementation resides outside Java code, typically via JNI | **No**; ends with `;` | The JVM links the call to the native implementation | Requires a matching implementation, library loading, and mapping; may encounter `UnsatisfiedLinkError` |

These modifiers belong to **methods** and are not interchangeable terms. `abstract` specifies that there is **no implementation yet**, `final` specifies that it **cannot be overridden**, `synchronized` specifies **how concurrency is controlled on invocation**, and `native` specifies that **the implementation resides on the native side**.

Quick identification example:

```java
abstract class Processor {
    abstract String process(String input); // abstract; no body

    final String label() {                  // final; has body
        return "processor";
    }

    synchronized void record() {           // synchronized; has body
        System.out.println("record");
    }

    native int nativeCode();                // native; no body
}
```

This is an **illustrative class declaration**, not a standalone runnable program. The `Processor` class is `abstract`, so `new Processor()` cannot be used; if `nativeCode()` is called without configuring a native implementation, the call may fail during linking.

## 2. Modifier Position in Method Syntax

A method with a body in a regular class has the form:

```java
[annotations] [modifiers] ReturnType methodName(Parameters) [throws Exceptions] {
    // Statements
}
```

An abstract or native method can end with a semicolon:

```java
[annotations] [modifiers] ReturnType methodName(Parameters) [throws Exceptions];
```

The two templates above are **explanatory notation**, not verbatim compilable Java code; the parts in square brackets are optional.

Concrete example:

```java
abstract class Operation {
    protected abstract int apply(int left, int right);

    public final String typeName() {
        return "operation";
    }

    public synchronized void logCall() {
        System.out.println("Operation called");
    }
}
```

When reading a method signature:

1. Identify the **modifiers** before the return type: `abstract`, `final`, `synchronized`, `native`, or a valid combination.
2. Identify the **return type** (`int`, `String`, `void`, ...), method name, and parameter list.
3. Check whether the declaration has a **body `{...}`** or simply ends with **`;`**.
4. Check the enclosing class or interface containing the method, because **valid modifiers depend on context**.
5. When inheritance is involved, check whether the method will be **overridden**, **hidden**, **overloaded**, or cannot be overridden.

`abstract` and `native` both have declarations without a Java body, but **they do not have the same meaning**: abstract requires a suitable Java implementation in a concrete subtype; native requires an implementation outside Java and a corresponding linking mechanism.

## 3. `abstract`: Declaring a Contract for Subclasses to Implement

An **abstract method** declares only the signature, optionally with `throws` and appropriate access modifiers, and ends with `;`.

```java
abstract class Shape {
    abstract double area();
}
```

The `Shape` class must be declared `abstract` because it contains the abstract method `area()`. Objects cannot be instantiated directly using `new Shape()`; a **non-abstract** subclass must provide implementations for the missing abstract methods according to overriding rules.

### Complete Example: Abstract Class and Concrete Subclass

Create the file **`AbstractMethodDemo.java`**:

```java
abstract class Shape {
    private final String name;

    Shape(String name) {
        this.name = name;
    }

    abstract double area();

    String describe() {
        return name + " area=" + area();
    }
}

final class Rectangle extends Shape {
    private final double width;
    private final double height;

    Rectangle(double width, double height) {
        super("rectangle");
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException("Dimensions must be positive");
        }
        this.width = width;
        this.height = height;
    }

    @Override
    double area() {
        return width * height;
    }
}

public class AbstractMethodDemo {
    public static void main(String[] args) {
        Shape shape = new Rectangle(3, 4);
        System.out.println(shape.describe());
        System.out.println(shape.area());
    }
}
```

Run with JDK 17+:

```bash
javac AbstractMethodDemo.java
java AbstractMethodDemo
```

Output:

```text
rectangle area=12.0
12.0
```

Explanation:

- `Shape.area()` only describes the **contract** of returning a `double`; it does not compute the area.
- `Rectangle.area()` has `@Override` and a body returning `width * height`; this is a **concrete method**.
- The variable `shape` has static type `Shape` but points to a `Rectangle` instance. When `shape.area()` is called, the JVM dispatches to the `Rectangle.area()` implementation.
- `Shape.describe()` is a concrete method of the abstract class. It calls `area()` on the current receiver; because the receiver is a `Rectangle`, the internal call also uses the `Rectangle.area()` implementation.
- `Rectangle` is marked `final` **at the class level** to prevent creating subclasses of `Rectangle`; this differs from the `final` modifier on a method. The example uses `final class` only to limit the illustrative inheritance hierarchy.

### Abstract Classes Still Have Constructors and Methods with Bodies

An abstract class can have fields, constructors, static methods, concrete instance methods, and abstract methods. The constructor of an abstract class is invoked during the creation of a **subclass instance**, even though the abstract class itself cannot be instantiated directly.

Conversely, a class declared `abstract` is **not required** to have any abstract methods:

```java
abstract class UtilityBase {
    final void ready() {
        System.out.println("ready");
    }
}
```

This is a valid declaration: the author wants to restrict direct instantiation or create a base for subclasses to use. Note that `UtilityBase` does not have a `main`.

### Abstract Methods in Interfaces

In an interface, regular instance methods without a body are implicitly `public abstract` even if the author does not write this explicitly:

```java
interface Formatter {
    String format(String text); // Implicitly public abstract.
}
```

An interface can also have **default methods**, **static methods**, and **private methods** with bodies in appropriate language contexts; they are not abstract methods merely because they are declared in an interface. The modifiers `final`, `synchronized`, and `native` are not valid choices for declaring an interface method; to synchronize a default method's behavior, you can place `synchronized (lock) { ... }` inside the body if the design requires it.

### Invalid `abstract` Combinations

`abstract` cannot be combined with:

- `private`: an abstract method needs a valid implementation/overriding mechanism, whereas private methods are not overridden.
- `static`: static methods belong to the class and do not participate in instance overriding.
- `final`: abstract requires an implementation via overriding; final prohibits overriding.
- `synchronized`: an abstract method has no body to execute under the corresponding monitor at the declaration level.
- `native`: abstract has no implementation yet, whereas native confirms that the implementation resides outside Java.
- `strictfp`: Java's modifier combinations do not allow declaring a method as both abstract and strictfp.

The following lines are **intentionally invalid** and have been commented out to avoid mistaking them for compilable examples:

```java
abstract class InvalidAbstractSamples {
    // abstract final void execute();
    // abstract static void execute();
    // private abstract void execute();
    // abstract synchronized void execute();
    // abstract native void execute();
}
```

For an abstract method, writing a `{ ... }` body directly in the declaration is also a syntax error. If you want to provide existing behavior, remove `abstract` and declare a concrete method.

## 4. `final`: Preventing Method Overriding, Without Preventing Calling or Overloading

A **final method** is a method that subclasses cannot **override**. It can still be called and can still contain state-mutating operations.

```java
class Device {
    final String category() {
        return "device";
    }

    void activate() {
        System.out.println("activated");
    }
}

class Phone extends Device {
    @Override
    void activate() {
        System.out.println("phone activated");
    }

    // String category() { return "phone"; }
    // If uncommented, error: cannot override the final method.
}
```

This is a valid class declaration as long as the line overriding `category()` remains commented out. `Phone` is allowed to override `activate()` because this method is not `final`; conversely, the implementation of `category()` cannot be replaced in a subclass.

### Complete Example: Final Method and Overloading

Create the file **`FinalMethodDemo.java`**:

```java
class BaseService {
    private int requests;

    final void record() {
        requests++;
    }

    final int getRequests() {
        return requests;
    }

    String status() {
        return "base";
    }
}

class ApiService extends BaseService {
    void record(String label) { // Overloads, does not override record().
        System.out.println("label=" + label);
        record();
    }

    @Override
    String status() {
        return "api";
    }
}

public class FinalMethodDemo {
    public static void main(String[] args) {
        ApiService service = new ApiService();
        service.record("create");
        service.record();
        System.out.println("requests=" + service.getRequests());
        System.out.println("status=" + service.status());
    }
}
```

Run:

```bash
javac FinalMethodDemo.java
java FinalMethodDemo
```

Output:

```text
label=create
requests=2
status=api
```

Explanation:

1. `BaseService`'s `record()` is final; `ApiService` cannot override that no-argument method.
2. `record(String)` in the subclass has a **different** parameter list, so it is an **overload** and is completely valid. It calls the inherited `record()`, and then the program calls `service.record()` once more; `requests` becomes `2`.
3. `status()` is not final, so `ApiService` can override it; the final call prints `api`.
4. `getRequests()` is also final yet still reads the instance field. Using `final` on a method **does not make `requests` immutable**; incrementing `requests` still happens.

### Distinguishing `final` by Position

| Declaration | Effect |
| --- | --- |
| `final class Utility { ... }` | Cannot inherit from the `Utility` class. |
| `final void save() { ... }` | Subclasses cannot override the instance method `save()`. |
| `final int size = 3;` | The variable cannot be reassigned after a valid assignment. |
| `private final List<String> items = ...;` | The reference field cannot be reassigned; **does not by itself make the list contents immutable**. |
| `static final int MAX = 10;` | The static field cannot be reassigned after valid initialization; commonly used as a constant. |

`final` on a method also does not mean the method **cannot return a new result** or **has no side effects**. `final` only places a constraint on **overriding in an inheritance relationship**.

### `private`, `static`, and `final`

- `private method` is not **overridden** under Java's inheritance mechanism, so adding `final` to a private method generally brings no additional API design benefit.
- `static method` is not overridden via dynamic dispatch; a subclass can declare a static method with the same signature via **method hiding** when the rules permit. If the superclass's static method is `final`, it also cannot be hidden by a method with a valid matching signature in the subclass.
- A `final` method can still be **overloaded** with a different signature, provided it does not violate other declaration rules.
- `abstract final` cannot be combined; these are two conflicting requirements regarding having to be implemented via overriding and being prohibited from overriding.

You should use a final method when subclasses need to preserve a core algorithm, a validation rule, or a step that must not be altered. Do not add `final` to every method by default if the project intentionally allows extension through inheritance.

## 5. `synchronized`: Automatically Locking a Monitor on Method Invocation

`synchronized` applies Java's **intrinsic synchronization**. When a thread enters a synchronized method, the JVM requires the thread to hold the appropriate **monitor** before executing the method body; when exiting the method, the JVM releases the monitor according to the rules, even if the method terminates due to an exception.

There are two cases to distinguish:

| Method type | Locked monitor | Example |
| --- | --- | --- |
| **Instance synchronized method** | Monitor of the **receiver object** (`this`) | `synchronized void increment() { ... }` |
| **Static synchronized method** | Monitor of the `Class` object representing **the class declaring the method** | `static synchronized void reset() { ... }` |

A monitor belongs to an object at runtime; `synchronized` **does not create a separate lock per method name**.

### Instance Synchronized: Multiple Threads Sharing One Object

Create the file **`SynchronizedCounterDemo.java`** (Java 17+):

```java
final class SafeCounter {
    private int count;

    synchronized void increment() {
        count++;
    }

    synchronized int getCount() {
        return count;
    }
}

public class SynchronizedCounterDemo {
    public static void main(String[] args) throws InterruptedException {
        SafeCounter counter = new SafeCounter();

        Runnable job = () -> {
            for (int i = 0; i < 10_000; i++) {
                counter.increment();
            }
        };

        Thread first = new Thread(job);
        Thread second = new Thread(job);
        first.start();
        second.start();

        first.join();
        second.join();

        System.out.println("count=" + counter.getCount());
    }
}
```

Compile and run:

```bash
javac SynchronizedCounterDemo.java
java SynchronizedCounterDemo
```

Result:

```text
count=20000
```

Analysis:

1. Both threads execute the same `job` and call `counter.increment()` **on the same `SafeCounter` object**.
2. `increment()` synchronizes on `counter`'s monitor, so the two threads do not execute the protected method section **simultaneously on the same monitor**.
3. The `count++` operation actually consists of reading the old value, computing, and writing back. Without proper synchronization, a **lost update** can occur when multiple threads increment the same variable; `synchronized` here helps prevent that problem.
4. `getCount()` is also synchronized, so it reads under the same monitor as the writes. Furthermore, `join()` ensures the main thread only prints after both threads have completed; the example yields the deterministic result `20000`.
5. If **two different `SafeCounter` objects** are created, each object has a different monitor and its own count. Two threads locking two different receivers **do not block each other merely because they call the same method name**.

The example uses `Thread` and `join` to demonstrate correctness, without promising a specific scheduling or CPU execution order. The final result is predictable because the same object is locked consistently and main waits for the threads to finish.

### Equivalent Form Using a Synchronized Block

For a simple instance synchronized method:

```java
class Box {
    private int value;

    synchronized void addOne() {
        value++;
    }
}
```

An alternative using the same monitor is:

```java
class Box {
    private int value;

    void addOne() {
        synchronized (this) {
            value++;
        }
    }
}
```

The two declarations above are **two separate versions of the same class for comparison**; do not place them simultaneously in a single source file because `Box` would be defined twice. In the second version, the block is written explicitly as `synchronized (this)` and the lock scope is limited to the block. In the first version, the lock covers the entire method body.

A synchronized block can also lock **any object**:

```java
private final Object lock = new Object();

// Snippet inside an instance method:
synchronized (lock) {
    // Access the state to be protected.
}
```

This snippet is an **illustrative code fragment**; the `lock` field must be placed inside the class and the `synchronized` block must reside inside an appropriate method/constructor/initializer. Using a private lock object can prevent external code from acquiring the `this` monitor, though all operations accessing shared data must consistently use the same lock.

### Static Synchronized: Locking the `Class` Object

Create the file **`StaticSynchronizedDemo.java`**:

```java
class Registry {
    private static int registered;

    static synchronized void register() {
        registered++;
    }

    static synchronized int total() {
        return registered;
    }
}

public class StaticSynchronizedDemo {
    public static void main(String[] args) {
        Registry.register();
        Registry.register();
        System.out.println(Registry.total());
    }
}
```

```bash
javac StaticSynchronizedDemo.java
java StaticSynchronizedDemo
```

```text
2
```

`Registry.register()` and `Registry.total()` are **static synchronized methods**, using the monitor of `Registry.class` when called. They do not acquire the monitor of any `new Registry()` object. Regarding **the lock used**, a static synchronized method is equivalent to a `synchronized (Registry.class) { ... }` block wrapping the entire body.

**Pitfall:** A `synchronized` instance method and a `static synchronized` method of the same class **do not block each other**, because the `this` lock and the `Class` lock are **two different monitors**. If both modify a static field, using different locks may fail to protect the invariant.

### `synchronized` Also Helps Ensure Visibility

According to the **Java Memory Model**, a monitor unlock *happens-before* every **subsequent** lock on that same monitor. Therefore, `synchronized` not only prevents two threads from entering regions protected by the same monitor concurrently, but also establishes **memory visibility** relationships between properly synchronized operations.

However, `synchronized` **does not automatically make the entire class thread-safe**:

- If another method reads/writes the same field **without participating in the same synchronization protocol**, the data can still suffer from races.
- If **two different monitors** are used to protect an invariant, two threads can still interleave unexpectedly.
- When a synchronized method calls another method and exposes a mutable object externally, you must examine **the entire sequence of operations** and reference escaping.
- If the logic involves separate calls to `get()`, a check, and then `set()`, having each method synchronized individually may still not be enough to guarantee **the atomicity of the entire sequence**; it may be necessary to wrap the entire transaction in a single locked region.
- Be aware of the risk of **deadlock** if threads acquire multiple locks in inconsistent orders; holding a lock while waiting on long I/O can also reduce responsiveness.

Synchronized methods on the **same monitor** are **reentrant**: a thread currently holding the monitor can call another synchronized method requiring the same monitor without deadlocking itself on that lock. Reentrancy does not resolve all deadlocks between **different locks**.

### Must an Overriding Method of a Synchronized Method Be Synchronized?

No. The `synchronized` modifier **is not part of the method signature** and is not automatically inherited as a constraint that "an overriding method must be synchronized." For example:

```java
class Parent {
    synchronized void process() {
        System.out.println("parent");
    }
}

class Child extends Parent {
    @Override
    void process() {
        System.out.println("child");
    }
}
```

This is a valid class declaration. `Child.process()` overrides `Parent.process()` without using synchronized; a call dispatched to `Child.process()` will **not automatically acquire the monitor from the superclass version's synchronized modifier**. Therefore, APIs relying on synchronization across overrides must be designed and reviewed carefully.

### `synchronized` Cannot Be Used on Constructors

Java does not allow declaring `synchronized ConstructorName(...)`. If part of the work in a constructor needs synchronization, a synchronized block can be used according to the rules. However, an object is typically not yet published to other threads before the constructor finishes, so using the `this` monitor inside a constructor merely "to be safe" may be a sign to reconsider how the object is published.

## 6. `native`: Declaring a Method Whose Implementation Resides Outside Java Code

`native` indicates a method whose **implementation body is not written as a Java body directly in that declaration**. The traditional scenario is **Java Native Interface (JNI)** connecting Java code to functions written in C/C++ or other native code through an appropriate mechanism.

```java
class NativeMath {
    native int square(int value);
}
```

The signature is valid, though the class does not yet contain a Java implementation of `square`. A native method must be declared **without a body**, ending with `;`. To invoke it successfully, the runtime must have a corresponding native function properly linked through the JNI environment or a related mechanism.

### Identification Example with Library Loading

```java
class NativeCalculator {
    static {
        System.loadLibrary("native_calculator");
    }

    native int multiply(int left, int right);

    static native String platformName();
}
```

This is **illustrative declaration code**; it does not run standalone without compiling and providing the `native_calculator` library for the target platform. `System.loadLibrary(...)` instructs the JVM to locate and load the native library according to the operating system's library path/naming configuration mechanism.

- `multiply` is an **instance native method**; the call `calculator.multiply(2, 3)` has receiver `calculator`, while the implementation runs on the native side.
- `platformName` is a **static native method**; the call `NativeCalculator.platformName()` does not use a regular receiver object.
- Arguments, return types, and exception-throwing behavior remain subject to the constraints of the bridge between Java and native code.
- If the library is not found, is loaded for the wrong architecture, or lacks a matching native symbol/mapping, the JVM may throw **`UnsatisfiedLinkError`** during loading or linking.
- Native code can interact with memory or resources outside the standard Java model; errors on the native side can corrupt or crash the process, rather than just being an ordinary Java exception.

### Minimal Workflow When Using JNI

A common workflow with JNI on modern JDKs:

1. Declare the native method in Java and use `javac -h` to generate JNI headers for the necessary declarations.
2. Write and compile the native shared library according to the generated header and the operating system's platform ABI.
3. Place the library in a location where the JVM can load it, or configure an appropriate library load path.
4. Load it with `System.loadLibrary(...)` or an equivalent mechanism, then call the method to verify the function name, types, and behavior.

Example command syntax with an actual `NativeMath.java` file containing the corresponding native declaration:

```bash
javac -h . NativeMath.java
```

Depending on the class/package structure, the JDK generates an appropriately named header file; the C/C++ side must implement the generated signature accurately. Running `javac -h` alone **is not enough to successfully call a native method** without a complete native library.

### How Does `native` Differ from `abstract`?

| Point of comparison | `abstract` | `native` |
| --- | --- | --- |
| Has an inline Java body? | No | No |
| Expected implementation | A concrete subclass/implementing class provides a matching implementation | A native implementation is linked at runtime |
| Can it be called directly on an instance of the declaring class? | Cannot create an instance if the class is still abstract | Can create an instance of a concrete class with a native method; calling it still requires a native link |
| Can it be `static`? | No | Yes |
| Can it be `final`? | No | Yes |
| Can it be `synchronized`? | No | Yes, subject to applicable method rules |
| Typical use cases | Polymorphic APIs/contracts | JNI, native library/system integration |

A `native` declaration **does not make a method abstract**, and an `abstract` declaration **does not imply a C/C++ implementation**.

### Can `native` Be Combined with `synchronized` and `final`?

At the level of Java modifier syntax for **methods in a class**, a native method can be `static`, `final`, or `synchronized` as long as no other condition is violated:

```java
class NativeBridge {
    final native int checksum(byte[] bytes);
    static native long nativeClock();
    synchronized native void updateNativeState();
}
```

This snippet **illustrates valid declarations only**; there is no JNI library, so it has no standalone output. `final` on `checksum` prevents overriding; `synchronized` on `updateNativeState` requires acquiring the receiver monitor during invocation according to JVM rules, even though the body executes on the native side.

A native method has no Java body, so you cannot write:

```java
// native int checksum(byte[] bytes) {
//     return 0;
// }
// Intentionally invalid: a native method must not have a Java method body.
```

`native` also cannot be combined with `abstract` or `strictfp` under modifier rules. A `native` method cannot be placed in a Java interface as a valid interface method modifier.

## 7. Modifier Combination Table: Valid or Error?

The following table applies to **methods in a regular class**; it does not apply by default to interface methods, constructors, or class declarations.

| Combination | Valid? | Explanation |
| --- | --- | --- |
| `abstract void run();` | Yes, in an abstract class | No body yet; a class containing an abstract method must be abstract. |
| `final void run() { }` | Yes | Concrete method that cannot be overridden. |
| `synchronized void run() { }` | Yes | Instance method that locks the receiver's monitor. |
| `static synchronized void run() { }` | Yes | Static method that locks the monitor of the `Class` declaring the method. |
| `native void run();` | Yes | Implementation is outside Java. |
| `static native void run();` | Yes | Static native method. |
| `final synchronized void run() { }` | Yes | Cannot be overridden; method uses the receiver's monitor. |
| `final native void run();` | Yes | Native method that cannot be overridden. |
| `synchronized native void run();` | Yes | Native method invoked under the corresponding monitor. |
| `abstract final void run();` | **No** | Needs overriding to be implemented, while final prohibits overriding. |
| `abstract synchronized void run();` | **No** | An abstract method has no body to synchronize at declaration. |
| `abstract native void run();` | **No** | Two conflicting implementation-providing models. |
| `abstract static void run();` | **No** | A static method is not an overridable instance method. |
| `private abstract void run();` | **No** | Private methods cannot be overridden as required by abstract. |
| `native void run() { }` | **No** | A native method must not have a Java method body. |
| `synchronized Constructor() { }` | **No** | Constructors cannot carry the synchronized modifier. |

A combination being **valid in modifier syntax** does not yet guarantee that calling it will succeed: for example, every `native` declaration still requires a suitable implementation and library linking.

Quick reference by identification questions:

- See **`abstract`** → look for the **subclass/implementation** and check whether the enclosing class is `abstract`.
- See **`final`** → look for **inheritance/overriding** and block violating overrides; do not infer immutable state.
- See **`synchronized`** → determine **which monitor is locked** and whether other access paths to the shared state use the same monitor.
- See **`native`** → look for **JNI/native integration**, library loading capability, and implementation mapping.

## 8. Inheritance and All Four Modifiers in One Design

Different modifiers can be combined on **different methods** to create a clear base class.

Create the file **`MethodPolicyDemo.java`**:

```java
abstract class WorkerTask {
    private int completed;

    abstract String perform();

    final String category() {
        return "worker-task";
    }

    synchronized void markCompleted() {
        completed++;
    }

    synchronized int completedCount() {
        return completed;
    }
}

class EmailTask extends WorkerTask {
    @Override
    String perform() {
        markCompleted();
        return "sent";
    }
}

public class MethodPolicyDemo {
    public static void main(String[] args) {
        WorkerTask task = new EmailTask();

        System.out.println("category=" + task.category());
        System.out.println("result=" + task.perform());
        System.out.println("result=" + task.perform());
        System.out.println("completed=" + task.completedCount());
    }
}
```

Compile/run:

```bash
javac MethodPolicyDemo.java
java MethodPolicyDemo
```

Output:

```text
category=worker-task
result=sent
result=sent
completed=2
```

Reading the design:

1. `WorkerTask.perform()` is an **abstract method**, requiring `EmailTask` to provide an implementation because `EmailTask` is a concrete class.
2. `category()` is a **final method**; subclasses cannot change how the category is returned. Even though the variable `task` has type `WorkerTask` and the actual receiver is `EmailTask`, the final method is still used according to the rules.
3. `markCompleted()` and `completedCount()` are **instance synchronized methods** both locking on receiver `task`; they protect access to the `completed` field when those calls are made from multiple threads on the same object.
4. `EmailTask`'s `perform()` calls `markCompleted()`. `perform()` itself is **not synchronized**, so other parts of the body outside the `markCompleted()` call are not covered by the monitor.
5. This example does not need `native` because the logic resides entirely in Java. Adding `native` merely to "show all four keywords" would create an unhelpful native dependency.

The example also shows that **final and synchronized do not replace each other**: `category()` disallows overriding without needing a lock, whereas `markCompleted()` uses a lock to protect state yet can still be overridden if a subclass deliberately does so. When protecting invariants in an API that allows inheritance, consider whether to add `final` to synchronized methods to prevent subclasses from dropping the synchronization mechanism, or design the API to avoid relying on uncontrolled overrides.

## 9. Interface, Constructor, and Static Method Contexts

Some confusion comes from applying **class method** modifiers to other constructs.

### Interface

In Java 17, an interface can contain:

```java
interface TaskListener {
    void onDone(); // Implicitly public abstract.

    default void onStart() {
        System.out.println("start");
    }

    static String kind() {
        return "listener";
    }

    private void helper() {
        System.out.println("helper");
    }
}
```

- `onDone()` is an abstract method; it has no body.
- `onStart()` is a default method with a body, which can be inherited/overridden by implementing classes according to the rules.
- `kind()` is a static interface method with no receiver instance, invoked via `TaskListener.kind()`.
- `helper()` is a private interface method with a body that supports reusing internal logic within the interface.

Do not declare interface methods with `final`, `native`, or `synchronized`. Also do not combine `abstract` with `default` or `static` on the same method; these are distinct modes.

### Constructor

A constructor has the class name and **no return type**:

```java
class Report {
    Report() {
        System.out.println("created");
    }

    final void publish() {
        System.out.println("published");
    }
}
```

`Report()` **is not a method**, so it is not declared with `abstract`, `final`, `synchronized`, or `native` as method modifiers. `publish()` is the final instance method.

### Static Method

`static synchronized void refresh() { ... }` is valid and locks the `Class` monitor. `static final void refresh() { ... }` is also valid in a class, though using `final` with a static method relates to **method hiding**, since static methods do not participate in overriding/dynamic dispatch.

`static abstract` is invalid. `static native` can be valid and is commonly used when a native function does not need a Java instance receiver.

## 10. Method Modifiers Do Not Cover All Aspects of Safety and Design

### 10.1. `final` Does Not Make a Method Side-Effect-Free

```java
class ChangingState {
    private int value;

    final void increase() {
        value++;
    }

    int value() {
        return value;
    }
}
```

`increase()` can certainly mutate a field even as a final method. Achieving an immutable object requires properly designing its fields, publication flow, and mutating APIs; that is independent of whether a method can be overridden.

### 10.2. `synchronized` Does Not Protect by Field Name Automatically

Two different methods modifying the same field under **different** locks do not guarantee safety. If `methodA()` uses `synchronized (lockA)` while `methodB()` uses `synchronized (lockB)`, two threads can still modify the field concurrently. A consistent lock discipline must be designed.

### 10.3. `native` Does Not Mean Running Faster

Calling a native method can add overhead for crossing the JNI boundary, processing data, and managing resources. Speed depends on the workload and implementation. `native` is an integration decision, not a speedup switch.

### 10.4. `abstract` Does Not Force Subclasses to Have Only One Implementation

Multiple subclasses can implement the same abstract method in their own ways. The declaration acts as a contract, while the concrete behavior can vary by the runtime receiver. An abstract class itself can provide part of the shared behavior and manage state.

### 10.5. `final` Does Not Always Prevent All Forms of Customization

A final instance method cannot be overridden, yet subclasses can still declare **method overloads** with different parameters or provide new methods. A subclass can also modify state that the final method implementation uses through valid paths; thus, a final method helps stabilize an algorithm but does not necessarily guarantee that the entire business outcome remains unchanged.

### 10.6. Exceptions and Locks in `synchronized`

If a synchronized method throws an exception, the monitor is released when the method exits. However, this does not automatically roll back state changes made before the exception. If an invariant spans multiple fields, you must design the update order and failure handling appropriately.

### 10.7. Native Code and Packaging Requirements

A class containing a native declaration can **compile** without a JNI library, but **running successfully** when calling the method requires a library matching the platform, architecture, path, and symbol. Do not introduce native methods into ordinary APIs without a clear integration need.

## 11. How to Identify Compile Errors Through Short Examples

The scenarios below are **intentionally invalid snippets**; do not copy them directly into a runnable program.

### Error A: Abstract Method with a Body

```java
// abstract class Bad {
//     abstract void execute() {
//         System.out.println("run"); // An abstract method cannot have a body.
//     }
// }
```

Fix it with `abstract void execute();` or remove `abstract` to make it a concrete method.

### Error B: Subclass Overriding a Final Method

```java
// class Parent {
//     final void ping() { }
// }
// class Child extends Parent {
//     @Override
//     void ping() { } // Cannot override Parent.ping().
// }
```

Fix it by not overriding, changing the design contract if you have permission to modify the superclass, or using a true overload with a different signature.

### Error C: Combining abstract with synchronized

```java
// abstract class Bad {
//     abstract synchronized void run(); // Invalid modifier combination.
// }
```

Fix it to `abstract void run();`. The concrete implementation in a subclass can use `synchronized` on its own if needed:

```java
abstract class ParentTask {
    abstract void runTask();
}

class LoggedTask extends ParentTask {
    @Override
    synchronized void runTask() {
        System.out.println("run");
    }
}
```

### Error D: Native Method with a Java Body

```java
// class Bad {
//     native int read() {
//         return 1; // A native method must not have a Java body.
//     }
// }
```

If you want to write a Java body, remove `native`; if you want JNI, keep the declaration `native int read();` and provide a native implementation through an appropriate library.

### Error E: Assuming Overriding a Synchronized Method Automatically Synchronizes It

```java
class Base {
    synchronized void update() {
        System.out.println("base");
    }
}

class Derived extends Base {
    @Override
    void update() {
        System.out.println("derived");
    }
}
```

This snippet is **completely valid** syntactically, yet `Derived.update()` is **not automatically synchronized**. This is a behavioral reasoning error, not a compile-time error. If the design requires all state-writing paths to be synchronized, you must verify which paths actually hold the lock.

## 12. Self-Check with Answers

**Question 1.** Can the method `abstract int size();` appear in a concrete class?

**Answer:** No. A class containing an abstract method must be `abstract`; a concrete implementation must be provided in a non-abstract subclass (unless validly satisfied through inheritance).

**Question 2.** Does `final void run() { }` forbid all calls to `run()` from subclasses?

**Answer:** No. A subclass can inherit and call a final method when access permissions allow, though it cannot override it. Overloading with a different signature can still be valid.

**Question 3.** When two threads call `counter.increment()` on the **same** object and the method is an instance synchronized method, which lock is used?

**Answer:** The monitor of the `counter` object itself; one thread must wait if that monitor is currently held by the other thread.

**Question 4.** Does a `static synchronized void update()` lock an instance object or the class?

**Answer:** It locks the monitor of the **`Class` object** representing the class declaring the method; it is not the `this` lock.

**Question 5.** Why can `native int sum(int a, int b);` compile yet throw `UnsatisfiedLinkError` when called?

**Answer:** A valid Java declaration does not mean the JVM has loaded and linked the native implementation. If the corresponding library or symbol is missing or mismatched, the native call can fail.

**Question 6.** Is `abstract native void work();` valid?

**Answer:** No. These two modifiers cannot be combined on the same method.

**Question 7.** Is a method `final synchronized void save() { ... }` valid, and what do the two keywords control?

**Answer:** Yes, for an appropriate class method. `final` prevents overriding in subclasses; `synchronized` acquires the receiver's monitor when the instance method is called.

**Question 8.** If you override a synchronized instance method with a non-synchronized method, does the JVM automatically acquire the lock declared by the superclass?

**Answer:** No. A call dispatched to the overriding implementation will synchronize according to the modifier of the invoked method itself and any synchronized blocks inside it.

**Question 9.** Why should `native` not be viewed as a "performance optimization" keyword by default?

**Answer:** JNI is a technical bridge to a native implementation; whether it is faster or slower depends on the workload and data conversion overhead, with no guarantee of speedup merely from the modifier.

**Question 10.** In `MethodPolicyDemo`, when calling `task.perform()`, why is the behavior that of `EmailTask` even though the variable has type `WorkerTask`?

**Answer:** `perform` is an abstract instance method and `EmailTask` provides the implementation. At runtime, dispatch follows the actual receiver, which is `EmailTask`.

## 13. Checklist When Reading Method Signatures in a Java Project

When encountering a method with these modifiers, review in sequence:

1. **Syntax:** Does the method end with `;` or have `{ ... }`? `abstract` and `native` require no Java body; `final` and `synchronized` have their own constraints.
2. **Context:** Is the method in an abstract class, concrete class, or interface? Are there any invalid modifiers in that position?
3. **Inheritance:** Can the method be overridden? Is there @Override in a subclass? Does `final` block replacing the implementation?
4. **Invocation:** Is the method static or instance? Static synchronized locks `Class`; instance synchronized locks the receiver object.
5. **State:** Does synchronization cover all access paths to the shared fields? Are there multiple steps that must execute atomically as a single transaction?
6. **Implementation:** If `native`, where is the library loaded, how is the JNI mapping set up, and does the native ABI match?
7. **Verification:** Check for compile errors with invalid modifier combinations; run thread examples with `join` to observe final values; do not use race-dependent outputs to claim a behavior "always happens."

---

**Remember:** `abstract` is **a contract awaiting implementation**, `final` is **a constraint preventing overriding**, `synchronized` is **monitor locking on invocation**, and `native` is **a declaration whose implementation resides outside Java**. For every method, correctly identifying its modifiers, static/instance kind, enclosing class/interface, presence of a method body, and inheritance relationships tells you **where the call is implemented, when it is locked, and who is allowed to change its behavior**.
