# Java `Object`: The Root Class and Shared Methods

## 1. Why Is Every Java Class Related to `Object`?

`java.lang.Object` is the root class of the **class** hierarchy in Java. A class that does not declare `extends` directly inherits from `Object`; a class that `extends` another class indirectly inherits from `Object` through the superclass chain. Therefore, Java objects all have a foundational set of methods for determining runtime type, comparing, representing as strings, and coordinating between threads.

```java
class Animal { }                 // implicitly extends Object
class Dog extends Animal { }     // indirectly inherits Object
```

- `Object x = new Dog();` is valid because a `Dog` is also an `Object`. The variable `x` has the declared type `Object`, while the actual object remains a `Dog`.
- `null` does not point to any object; calling a method through a `null` reference causes a `NullPointerException`.
- `int`, `boolean`, and other primitive types are **not** objects. Wrapper classes such as `Integer` and `Boolean` are objects. Arrays are objects and can be assigned to a variable of type `Object`.
- `Object` does not define `compareTo`, `size`, or business operations. Those capabilities belong to other interfaces/classes or are defined by the application.

`java.lang` is imported automatically, so there is no need to write `import java.lang.Object;`.

## 2. Catalog of Important Methods

| Method in `Object` | Role | Key points to remember |
| --- | --- | --- |
| `public final Class<?> getClass()` | Gets the **actual runtime** class type of the object. | `final`: cannot be overridden. |
| `public boolean equals(Object obj)` | Checks whether two objects are considered equal. | Defaults to reference equality; many classes override it to compare by value. |
| `public int hashCode()` | Generates a hash code for data structures such as `HashMap`, `HashSet`. | Must be consistent with `equals`; a hash code is not a unique ID. |
| `public String toString()` | Produces a string describing the object. | Should be overridden for convenient logging/debugging; do not expose secret information. |
| `protected Object clone()` | Object copying mechanism. | Defaults to shallow copy; has `Cloneable` constraints; clearer copying approaches are usually preferred. |
| `protected void finalize()` | Legacy cleanup hook before garbage collection. | Deprecated and slated for removal; do not rely on it to release resources. |
| `public final void wait()`, `wait(long)`, `wait(long, int)` | Waits for a signal on the object's monitor. | Must own the monitor; `wait` releases that monitor while waiting. |
| `public final void notify()`, `notifyAll()` | Wakes up one or all threads waiting via `wait` on the same monitor. | Does not hand over the lock immediately; the awakened thread must reacquire the monitor. |

`Object` also has a public constructor `Object()`; constructors are not overridden methods. Most applications call the methods in the table through subclasses rather than creating `new Object()` to represent business data.

## 3. `==`, `equals()`, and the Concept of Equality

For **object references**, `a == b` asks whether two variables point to the **exact same object**. Meanwhile, `a.equals(b)` asks whether two objects are **equal according to the class's rules**.

The default implementation of `Object.equals` is equivalent to checking `this == obj`. Therefore, if a class does not override it, two different objects are not equal even if their fields have the same values. Classes such as `String`, numeric wrapper classes, and `record` types have their own value-comparison rules.

```java
String first = new String("Java");
String second = new String("Java");
System.out.println(first == second);      // false: two different objects
System.out.println(first.equals(second)); // true: same content
```

Do not use `==` to compare the **content** of a `String` or value object. The fact that some string literals may be interned does not turn `==` into a content comparison.

### Contract When Overriding `equals`

For non-`null` references, a valid equality relation must satisfy:

1. **Reflexive:** `x.equals(x)` is `true`.
2. **Symmetric:** `x.equals(y)` and `y.equals(x)` return the same result.
3. **Transitive:** if `x.equals(y)` and `y.equals(z)`, then `x.equals(z)`.
4. **Consistent:** repeated comparisons yield the same result if the state involved in comparison does not change.
5. **Non-nullity:** `x.equals(null)` is `false`.

Override the exact signature `equals(Object)`, and use `@Override` so the compiler catches mistakes. Writing `equals(MyType)` only **overloads** and does not replace `Object.equals(Object)`.

When designing an inheritance hierarchy that can be extended with additional state, special care is needed to avoid breaking symmetry/transitivity. For value objects, an immutable `final` class or a `record` usually keeps the rules simpler and safer.

## 4. The `hashCode()` Contract Accompanying `equals()`

Mandatory rule: **if `a.equals(b)` is `true`, then `a.hashCode() == b.hashCode()` must be `true`.** The converse is not true: two unequal objects can still share the same hash code (*collision*). If the same object does not change state relevant to `equals`, its hash code must remain stable across calls within the same execution according to the API contract.

`HashMap` and `HashSet` use `hashCode` to locate candidate buckets, then use `equals` to distinguish elements. Overriding `equals` while forgetting `hashCode` can cause a set to accept two elements considered equal, or fail to find an equivalent key.

- Compute the hash from the exact same attributes that `equals` uses. You can write `Objects.hash(field1, field2)` for readability; note that this approach can incur extra overhead compared to a direct formula.
- Do not treat `hashCode` as a unique identifier, a memory address, or a value guaranteed to stay constant across two JVM runs.
- Avoid mutating fields involved in `equals/hashCode` while the object is a key in a `HashMap` or an element in a `HashSet`: after mutation, the structure may fail to find it under the new hash code.
- When you need a hash based on **object identity** regardless of whether the class overrode `hashCode`, `System.identityHashCode(obj)` is available; this method does not guarantee uniqueness either.

## 5. Java 17+ Example: Correctly Overriding Three Common Methods

Create the file `ObjectDemo.java` with the following full content:

```java
import java.util.HashSet;
import java.util.List;

public class ObjectDemo {
    static final class Point {
        private final int x;
        private final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Point other)) {
                return false;
            }
            return x == other.x && y == other.y;
        }

        @Override
        public int hashCode() {
            return 31 * x + y;
        }

        @Override
        public String toString() {
            return "Point[x=" + x + ", y=" + y + "]";
        }
    }

    public static void main(String[] args) {
        Point a = new Point(2, 3);
        Point b = new Point(2, 3);

        System.out.println("==: " + (a == b));
        System.out.println("equals: " + a.equals(b));
        System.out.println("same hash: " + (a.hashCode() == b.hashCode()));
        System.out.println("HashSet size: " + new HashSet<>(List.of(a, b)).size());
        System.out.println("toString: " + a);
        System.out.println("runtime class: " + a.getClass().getSimpleName());
    }
}
```

Run:

```bash
javac ObjectDemo.java
java ObjectDemo
```

Output:

```text
==: false
equals: true
same hash: true
HashSet size: 1
toString: Point[x=2, y=3]
runtime class: Point
```

**Explanation:** `a` and `b` are created by two `new` calls, so they have different references. They are equal by their `x/y` coordinate pair and have the same hash code, so `HashSet` keeps only one equivalent value. Making the class and fields `final` prevents state mutation issues or subclasses altering the comparison rules. The formula `31 * x + y` can produce hash collisions for different points, but does not violate the contract.

## 6. Understanding `getClass()` and `toString()` Accurately

### `getClass()`: Runtime Type

```java
Object value = "hello";
System.out.println(value.getClass() == String.class); // true
```

The declared type is `Object`, while the actual type is `String`. `getClass()` returns the `Class` object used in reflection. Do not confuse `value.getClass() == SomeClass.class` (matching **that exact class**) with `value instanceof SomeClass` (which accepts subclasses or classes implementing an interface). On a `null` variable, `getClass()` cannot be called.

### `toString()`: A Human-Useful Description

By default, `Object.toString()` produces a string in the format class name + `@` + hexadecimal representation of `hashCode()`, such as `mypackage.Point@1a2b3c`; the hex part is **not necessarily** a memory address or identity hash if the class has overridden `hashCode`.

Override `toString()` to show the fields needed for observation, such as `Point[x=2, y=3]`. Concatenating an object with a string or calling `System.out.println(obj)` typically invokes the `toString()` representation (for `null`, string conversion produces `"null"`). Do not print passwords, tokens, sensitive data, or structures that can recurse infinitely.

## 7. `wait()`, `notify()`, `notifyAll()`: Coordinating via Monitors

Every object has a monitor/intrinsic lock used by `synchronized`. `Object`'s `wait`/`notify` methods operate on **the monitor of the target object itself**. They are the foundational mechanism for waiting on conditions between threads; this is not the typical approach for new application code when appropriate `java.util.concurrent` utilities can be used.

- `wait()`: the thread must hold the object's monitor; while waiting, it **releases that monitor** so another thread can change the condition. Upon waking up, the thread must reacquire the monitor before continuing.
- `notify()`: wakes up one thread waiting on the same object, with no guarantee about which thread is chosen.
- `notifyAll()`: wakes up all threads waiting on the object; they still must take turns reacquiring the lock and checking the condition.
- Calling these methods without owning the corresponding monitor throws `IllegalMonitorStateException`. Typically, wrap them in `synchronized (lock)` or a `synchronized` method on `lock` itself.
- Always call `wait` inside a `while` loop that checks the condition, because *spurious wakeups* can occur, a thread can be awakened before the condition is true, or the condition may have been changed by another thread. With `wait(long timeout)`, a value of `0` means wait indefinitely; timed calls also need to recheck the condition.
- `wait` can throw `InterruptedException`. Handle it appropriately: propagate it outward, or restore the interrupt flag if caught and unable to rethrow. `Thread.sleep` does **not** release held monitors.

Example of a single-slot mailbox. Create the standalone file `MonitorDemo.java`:

```java
public class MonitorDemo {
    static final class Mailbox {
        private String message;

        synchronized void put(String value) throws InterruptedException {
            while (message != null) {
                wait();
            }
            message = value;
            notifyAll();
        }

        synchronized String take() throws InterruptedException {
            while (message == null) {
                wait();
            }
            String value = message;
            message = null;
            notifyAll();
            return value;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Mailbox mailbox = new Mailbox();

        Thread consumer = new Thread(() -> {
            try {
                System.out.println("Received: " + mailbox.take());
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        });

        consumer.start();
        mailbox.put("hello");
        consumer.join();
    }
}
```

```bash
javac MonitorDemo.java
java MonitorDemo
```

Stdout of a normal run:

```text
Received: hello
```

Regardless of whether the producer or consumer runs first, `while` guards the `message` condition, and the `wait/notifyAll` calls occur while holding the monitor of the same `Mailbox`. This is an example for learning the mechanism; in production, `BlockingQueue`, `Lock`/`Condition`, or high-level concurrency utilities are usually clearer and easier to maintain.

## 8. `clone()` and `finalize()`: Know Their Limitations

### `clone()` Is Usually a Shallow Copy

`Object.clone()` has `protected` access; classes wanting to expose cloning typically override it, call `super.clone()`, and implement `Cloneable`. If an object does not support `Cloneable`, the default clone mechanism throws `CloneNotSupportedException` (arrays have their own clone rules). A shallow copy creates a new object, but reference fields can still point to the **same child objects**.

For example, an object containing a `List<String>`: if shallow-cloned, both copies can share the same `List`; modifying the copy's list affects the original. To be independent, the necessary components must be explicitly copied. `Cloneable` also does not provide a public `clone()` method in the interface itself.

In application design, copy constructors, factories, or immutable value types usually express intent better than `clone()`. Never assume `clone` performs a deep copy.

### `finalize()` Is Not for Resource Management

`finalize()` is a legacy mechanism that has been deprecated and targeted for removal. There is no guarantee it runs in time or before the program exits; misusing it also introduces performance and reliability risks. **Do not use `finalize()` to close files, sockets, connections, or release important resources.** Instead, use `AutoCloseable` and `try-with-resources`:

```java
try (var reader = java.nio.file.Files.newBufferedReader(path)) {
    // read data from reader; reader will be closed when leaving the block
}
```

The snippet above illustrates the syntax when `path` is already a `java.nio.file.Path`; it is not a standalone program. Memory collection is handled by the GC; closing OS resources is a responsibility that must be expressed explicitly in application logic.

## 9. Distinguishing `Object`, `Objects`, and `record`

`java.util.Objects` is a **utility class** (distinct from `java.lang.Object`) providing static methods such as `Objects.equals(a, b)`, `Objects.hash(...)`, `Objects.requireNonNull(value)`, and `Objects.toString(value)`. `Objects.equals(a, b)` is `null`-safe; whereas `a.equals(b)` throws an exception if `a == null`.

For simple data models, `record` (Java 16+) automatically generates `equals`, `hashCode`, and `toString` based on the record components:

```java
record Position(int x, int y) {}
```

`new Position(2, 3).equals(new Position(2, 3))` is `true`. A record does not allow reassigning its components, but if a component holds a mutable object (for example, a list), that object itself can still be modified; therefore, consider deep immutability when using a record as a hash key. Records are a solid choice for many value data types, though they do not replace every class with business behavior.

## 10. Common Mistakes and Application Checklist

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Comparing object contents with `==`. | Confuses identity with value. | Use `equals` per the class contract; for potentially `null` values, use `Objects.equals`. |
| Overriding `equals` without overriding `hashCode`. | `HashMap`/`HashSet` behave unexpectedly. | Update both methods together and test with equivalent objects. |
| Only writing `equals(MyClass)` without `equals(Object)`. | Does not override; collections still call the `Object` version. | Write the exact signature and always add `@Override`. |
| Mutating fields used to compute the hash of a stored key. | Looking up or removing the key may fail. | Use immutable values for keys or avoid mutating relevant state. |
| Treating `hashCode` as a unique ID or memory address. | Misidentifies objects when collisions occur. | Use explicit business keys/IDs. |
| Calling `wait` outside a monitor or using `if` instead of `while`. | `IllegalMonitorStateException` or race conditions. | Synchronize on the right object and recheck the condition in a loop. |
| Thinking `notify` immediately yields the lock. | Misreasons about execution order between threads. | Understand that the awakened thread must wait to reacquire the monitor. |
| Assuming `clone` deep-copies or `finalize` always runs. | Unintended shared state or resource leaks. | Copy explicitly; use `try-with-resources`. |

**Self-check questions:**

1. Why can two newly created objects have `equals == true` yet `== false`?
2. Why must equal objects have the same hash, yet having the same hash does not guarantee equality?
3. When a thread calls `lock.wait()`, which lock does it release? Why must `while` be used?
4. How does `getClass()` differ from an `instanceof` check when inheritance is involved?
5. Why might a copy constructor or `record` be more suitable than `clone()` or a mutable class in a value model?

Remember: `Object` sets the shared foundation for Java classes; when overriding, the most important things are **obeying the `equals`/`hashCode` contract, providing an appropriate `toString` representation, and understanding monitors properly when using `wait`/`notify`**.