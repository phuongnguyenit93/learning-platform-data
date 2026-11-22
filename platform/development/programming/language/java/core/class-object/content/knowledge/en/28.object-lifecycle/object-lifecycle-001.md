# Java Object Lifecycle: From Object Creation and Usage to Becoming Unreachable

## 1. Lesson Objectives

A Java object does not have the same lifecycle as a local variable. A variable can go out of scope while the object is still referenced elsewhere; conversely, an object can become **unreachable** before the method ends if the program no longer needs a reference to it. And even when the object is no longer reachable, the JVM **does not promise to free memory immediately**.

To understand the lifecycle, we need to distinguish four conceptual layers:

1. **Object creation:** The JVM performs allocation and initializes the instance according to Java rules.
2. **Object usage:** Code holds, passes, assigns, or stores references, calls instance methods, and makes valid state changes.
3. **Reachability:** At a given point in time, can the object still be reached from the reference sources that the JVM considers live?
4. **Memory and resource management:** The garbage collector can reclaim the memory of an object that is no longer reachable; resources such as file/socket/database connections must instead be closed through other mechanisms and should not wait for GC.

Short example:

```java
Person person = new Person("An");
person.greet();
person = null;
```

This is an **illustrative code snippet**; assume `Person` has a constructor and a `greet()` method.

- `new Person("An")` creates a Person object.
- `person` is a reference-type variable pointing to the object.
- `person.greet()` uses the object through that reference.
- `person = null` makes **the person variable no longer reference the old object**.
- That **does not by itself prove** that the old object is no longer reachable: another variable or another field might still hold a reference.
- Even when it is no longer reachable, the time when GC runs and reclaims memory **is not determined by the null assignment statement**.

**Overarching message:** Java automatically manages heap memory at the level of object reachability, yet developers are still responsible for reference lifetimes, state validity, and closing resources in a timely manner.

All runnable examples below target **Java 17+**, are separated by filename, and include `javac`/`java` commands and deterministic stdout where appropriate. Explanations regarding GC avoid relying on the JVM having to run GC at a fixed time.

## 2. How Does an Object Differ from a Reference Variable?

An object is an instance of a class (or an array instance) that has identity and state according to its type. A reference variable **does not contain the entire object**; it holds a reference value that can be used to access the object, or `null`.

Create **`ObjectAndReferenceDemo.java`**:

```java
class Person {
    private final String name;

    Person(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }
}

public class ObjectAndReferenceDemo {
    public static void main(String[] args) {
        Person first = new Person("An");
        Person second = first;

        System.out.println(first.name());
        System.out.println(second.name());
        System.out.println(first == second);

        first = null;
        System.out.println(second.name());
    }
}
```

```bash
javac ObjectAndReferenceDemo.java
java ObjectAndReferenceDemo
```

```text
An
An
true
An
```

`first` and `second` **point to the same Person**, not two copies. Assigning `first = null` only changes the value of **one variable**; `second` can still access the old object. This is why an object's lifecycle cannot be tied to a single variable name.

### Reference Diagram

```text
Initially:
first  ──┐
         ├────> Person("An")
second ──┘

After first = null:
first  ───────> null
second ───────> Person("An")
```

GC is not allowed to reclaim an object still needed for `second.name()`; the object remains reachable through a valid strong reference.

## 3. Conceptual States of the Lifecycle

Imagine the progression:

```text
new → allocation/initialization → object ready to be used
   → references are passed/stored/changed
   → no appropriate strong reachability path remains
   → can be detected and reclaimed by GC
```

This is a **conceptual diagram**, not an official JVM state machine API. In particular:

- Java does not provide a regular method that precisely answers "at which second object X will be reclaimed".
- GC can run multiple times while the object is still alive.
- An object no longer being accessible from code **does not mean** it is immediately freed.
- The JVM may optimize allocation and internal representation; this diagram should not be used to claim that every `new` corresponds to an observable physical heap allocation.
- The lifetime of a **file descriptor, socket, transaction** is not identical to the lifetime of the wrapper Java object.

First mental exercise: **do not ask "has the variable gone out of scope?" before asking "is there still any strong reference path to the object?"**

## 4. Step 1: `new` Marks a Request to Create a Class Instance

Example:

```java
Person p = new Person("Lan");
```

A class instance creation expression `new Person(...)` executes the instance creation process according to Java semantics:

1. Determine the class to instantiate and the constructor selected via overload resolution.
2. When needed, ensure the class has been initialized according to class initialization rules.
3. Allocate space for the instance according to the JVM mechanism.
4. Instance fields first have **default values** (0, false, null...) before the initialization defined in the source.
5. Execute the constructor chain, calling the appropriate superclass constructor before executing the remainder in Java's defined order.
6. Execute field initializers and instance initializer blocks in the specified order, along with the constructor body.
7. If construction completes normally, the expression receives a reference to the instance and code continues using it.

The order observable from source code is illustrated in the following sections. You should not equate these conceptual steps with the order of individual machine code instructions in an optimizing JVM, as long as behavior still conforms to the Java specification.

## 5. Class Initialization and Object Initialization Are Two Different Events

`static` fields/static initializer blocks belong to the **class**, whereas instance fields/instance initializer blocks and the constructor body apply to **each instance**.

Create **`ClassVersusInstanceInitDemo.java`**:

```java
class Widget {
    static {
        System.out.println("class initialized");
    }

    {
        System.out.println("instance initialized");
    }

    Widget() {
        System.out.println("constructor");
    }
}

public class ClassVersusInstanceInitDemo {
    public static void main(String[] args) {
        new Widget();
        new Widget();
    }
}
```

```bash
javac ClassVersusInstanceInitDemo.java
java ClassVersusInstanceInitDemo
```

```text
class initialized
instance initialized
constructor
instance initialized
constructor
```

In a normal execution of this program:

- Class Widget is initialized when required by active use, so the static block runs **once for class initialization**.
- Creating two instances → the instance initializer and constructor body run for **each instance**.
- Class initialization is not a synonym for a constructor call.
- Once the class has been initialized, creating objects afterward does not repeat the static initializer.

**Important language exception:** Accessing a compile-time constant static field, referencing a class literal, or various reflection operations have different triggering rules. You should not claim that "whenever a class name is mentioned, its static block runs".

## 6. Default Values of Instance Fields Before Explicit Initialization

For fields, Java guarantees default values such as:

| Field type | Default value |
| --- | --- |
| `byte`, `short`, `int` | 0 |
| `long` | 0L |
| `float` | 0.0f |
| `double` | 0.0d |
| `char` | `'\u0000'` |
| `boolean` | false |
| Reference field | null |

Instance fields have a default initialization phase before source initializers/constructors assign values.

**Do not confuse with local variables:** A local variable in a method does **not** automatically have a default value to be read before definite assignment.

Create **`FieldDefaultsDemo.java`**:

```java
class Data {
    int count;
    boolean ready;
    String title;
}

public class FieldDefaultsDemo {
    public static void main(String[] args) {
        Data data = new Data();

        System.out.println(data.count);
        System.out.println(data.ready);
        System.out.println(data.title == null);
    }
}
```

```bash
javac FieldDefaultsDemo.java
java FieldDefaultsDemo
```

```text
0
false
true
```

These are **default field values**, not evidence that Data has an explicit zero-argument constructor written by the author. The compiler can generate a default constructor if the class declares no constructors and syntactic conditions are valid.

## 7. Constructor Chain and Superclass/Subclass Initialization Order

When creating a subclass instance, the corresponding superclass portion is initialized before the subclass portion, according to Java's constructor invocation rules.

Create **`InheritanceInitializationDemo.java`**:

```java
class Parent {
    int parentField = announce("parent field");

    {
        announce("parent block");
    }

    Parent() {
        announce("parent constructor");
    }

    static int announce(String text) {
        System.out.println(text);
        return 1;
    }
}

class Child extends Parent {
    int childField = announce("child field");

    {
        announce("child block");
    }

    Child() {
        announce("child constructor");
    }
}

public class InheritanceInitializationDemo {
    public static void main(String[] args) {
        new Child();
    }
}
```

```bash
javac InheritanceInitializationDemo.java
java InheritanceInitializationDemo
```

```text
parent field
parent block
parent constructor
child field
child block
child constructor
```

**How to read this:**

- `new Child()` leads to the constructor chain calling the appropriate superclass constructor.
- The Parent field initializer and Parent instance block run before the Parent constructor body.
- After the superclass initialization path finishes, the Child field initializer and Child instance block run in source order before the Child constructor body.
- All of these parts apply to the same Child object being created; **no independent Parent object** is created and placed inside Child.

If constructors have `this(...)` chaining, check the constructor invocation rules so you do not conclude that every constructor body runs all instance initializers once. A class's initializers execute strictly according to the constructor chain rules.

## 8. The Risk of Calling an Overridable Method in a Constructor

A superclass constructor can call a method overridden by a subclass **before the subclass field initializers run**. In that case, the overriding method observes the subclass fields at their default values.

Create **`ConstructorDispatchRiskDemo.java`**:

```java
class Base {
    Base() {
        printState();
    }

    void printState() {
        System.out.println("base");
    }
}

class Derived extends Base {
    private int count = 5;

    @Override
    void printState() {
        System.out.println("count=" + count);
    }
}

public class ConstructorDispatchRiskDemo {
    public static void main(String[] args) {
        Derived object = new Derived();
        object.printState();
    }
}
```

```bash
javac ConstructorDispatchRiskDemo.java
java ConstructorDispatchRiskDemo
```

```text
count=0
count=5
```

The first call to `printState()` happens in `Base()`; dynamic dispatch goes to the Derived implementation, but `count = 5` has not run yet. On the second call after the constructor completes, count is 5.

**Recommendation:** Avoid calling overridable instance methods from a constructor, especially methods that depend on subclass state. A constructor should ensure invariants before the object is published.

## 9. What Happens If a Constructor Throws an Exception?

A constructor can throw an exception during object creation. The `new ...` expression does not return a normal instance to the caller if construction terminates abruptly.

Create **`ConstructionFailureDemo.java`**:

```java
class Ticket {
    Ticket(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException(
                    "negative amount");
        }
        System.out.println("ticket constructed");
    }
}

public class ConstructionFailureDemo {
    public static void main(String[] args) {
        try {
            new Ticket(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }

        new Ticket(3);
    }
}
```

```bash
javac ConstructionFailureDemo.java
java ConstructionFailureDemo
```

```text
negative amount
ticket constructed
```

The object allocated for the failed construction is not returned as a normally usable reference from the new expression. However, saying "it definitely disappears immediately" is too strong: a constructor can **leak `this`** via a static field/listener/callback before throwing an exception, resulting in a partially initialized object still being reachable.

**Design lesson:** Check inputs early, do not publish `this` before invariants are complete, and consider a factory when creation has multiple steps that can fail.

## 10. Using an Object: Calling Methods, Reading/Writing Fields, Holding References

After construction, a client can:

- Call instance methods through a reference.
- Read state through appropriate methods/getters.
- Modify state if the class allows it.
- Store the reference in another variable, instance field, static field, collection, array, or closure.
- Pass the reference into methods/constructors.
- Return the reference to the caller.
- Share the reference with another thread (with thread-safety/safe-publication considerations).

Create **`ObjectUsageDemo.java`**:

```java
class Counter {
    private int count;

    void increment() {
        count++;
    }

    int value() {
        return count;
    }
}

public class ObjectUsageDemo {
    public static void main(String[] args) {
        Counter counter = new Counter();
        counter.increment();
        counter.increment();

        System.out.println(counter.value());
    }
}
```

```bash
javac ObjectUsageDemo.java
java ObjectUsageDemo
```

```text
2
```

The `Counter` object persists across multiple method calls; Java does not create a new Counter when calling `increment()`. The instance field count belongs to **the same object**, so state accumulates.

This example runs in a single thread. If multiple threads call increment concurrently, `count++` is not atomic on its own; lifecycle/reachability does not mean thread safety.

## 11. Pass-by-Value in Java: Objects Are Not Automatically Copied

Java passes the **value** of arguments into parameters. For reference types, the value copied is the **reference value**.

Create **`ReferenceParameterDemo.java`**:

```java
class Counter {
    int count;
}

public class ReferenceParameterDemo {
    static void changeState(Counter parameter) {
        parameter.count = 7;
    }

    static void replaceLocalReference(Counter parameter) {
        parameter = new Counter();
        parameter.count = 99;
    }

    public static void main(String[] args) {
        Counter original = new Counter();

        changeState(original);
        System.out.println(original.count);

        replaceLocalReference(original);
        System.out.println(original.count);
    }
}
```

```bash
javac ReferenceParameterDemo.java
java ReferenceParameterDemo
```

```text
7
7
```

`changeState` uses the copied reference to mutate the shared object. `replaceLocalReference` only reassigns the method's local parameter to a new object; the `original` variable still points to the old object.

**Lifecycle implication:** The new object created in `replaceLocalReference` may no longer be reachable after the method returns if nothing holds onto it. However, leaving the method does not force GC to run immediately.

## 12. Object Identity and State Equality

Two different objects can have the same state and return true for `equals()` if the class defines value equality. `==` between references still compares for the **same object identity**.

Create **`IdentityAndEqualityDemo.java`**:

```java
record Point(int x, int y) {
}

public class IdentityAndEqualityDemo {
    public static void main(String[] args) {
        Point a = new Point(2, 3);
        Point b = new Point(2, 3);
        Point alias = a;

        System.out.println(a == b);
        System.out.println(a.equals(b));
        System.out.println(a == alias);
    }
}
```

```bash
javac IdentityAndEqualityDemo.java
java IdentityAndEqualityDemo
```

```text
false
true
true
```

`a` and `b` are two record objects with different identities even though they are equal by components; `alias` has the same reference as a. To reason about reachability, **reference identity and reference paths** are the central focus, not `equals`.

A HashSet holding records by value may choose to keep one instance out of two equal objects; that does not change GC rules based on the references actually present in the object graph.

## 13. From a Local Variable to Another Object's Field

A reference can "escape" from where it was created by being stored in a field of a live object.

Create **`ReferenceEscapeDemo.java`**:

```java
class Note {
    final String text;

    Note(String text) {
        this.text = text;
    }
}

class Notebook {
    private Note saved;

    void save(Note note) {
        saved = note;
    }

    String read() {
        return saved.text;
    }
}

public class ReferenceEscapeDemo {
    static void createAndSave(Notebook notebook) {
        Note local = new Note("remember");
        notebook.save(local);
    }

    public static void main(String[] args) {
        Notebook notebook = new Notebook();

        createAndSave(notebook);
        System.out.println(notebook.read());
    }
}
```

```bash
javac ReferenceEscapeDemo.java
java ReferenceEscapeDemo
```

```text
remember
```

After `createAndSave` returns, the local variable `local` is no longer in scope. However, the Note object is still reachable through:

```text
notebook reference
      |
      v
  Notebook.saved ----> Note("remember")
```

**Conclusion:** The scope of the variable that created an object and the lifetime of the object are not the same thing.

## 14. A Collection Can Extend an Object's Lifecycle

If a reachable collection holds a **strong reference** to an object, that object generally remains reachable through the collection.

Create **`CollectionRetentionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class CollectionRetentionDemo {
    public static void main(String[] args) {
        List<StringBuilder> items = new ArrayList<>();

        StringBuilder builder =
                new StringBuilder("stored");
        items.add(builder);
        builder = null;

        System.out.println(items.get(0).toString());

        items.clear();
        System.out.println(items.isEmpty());
    }
}
```

```bash
javac CollectionRetentionDemo.java
java CollectionRetentionDemo
```

```text
stored
true
```

After `builder = null`, the List still holds the object. `items.clear()` removes references from the list. If there are no other strong references, the builder object **can become** unreachable; code cannot tell whether GC has reclaimed it immediately or not.

For caches, queues, maps, or listener registries, manage the **removal/eviction policy**. An object that is "no longer used in business terms" but still sits in a live collection will continue to be retained in memory.

## 15. What Is Reachability?

An object is considered reachable if there is an appropriate reference path from sources that the runtime considers live, commonly called **GC roots** in models explaining garbage collection.

Commonly described sources include:

- Live local variables/arguments in running threads.
- Static fields of classes still considered live by the runtime.
- Thread-related objects and references from runtime structures.
- References held through JNI/native handles and other VM mechanisms.
- Object fields/array elements reached from the references above.

This is a **conceptual model**: the exact root set and liveness optimizations are up to the JVM/collector, not a Java API guaranteeing that every local variable remains a root all the way to the `}` brace.

**Key point to remember:** GC cares about **whether an object is reachable through graph references**, not whether the object is "useful to the business".

## 16. Object Graph Diagram and Paths That Keep Objects Alive

```text
GC roots
   |
   +----> AppState
   |          |
   |          +----> UserSession ----> Profile
   |
   +----> live local list ----> Item A
   |                            |
   |                            +----> Item B
   |
   +----> static cache ----> CachedResult
```

If Profile has no direct local variable but still has a path from AppState → UserSession → Profile, it is reachable. If Item A and Item B only reference each other and have **no path from a root**, they can be reclaimed by GC.

The presence of a reference inside an already unreachable object **does not turn that object into a root**.

## 17. Assigning `null` Only Removes One Reference Path

Create **`NullDoesNotDestroyDemo.java`**:

```java
class Item {
    final String id;

    Item(String id) {
        this.id = id;
    }
}

public class NullDoesNotDestroyDemo {
    public static void main(String[] args) {
        Item a = new Item("A");
        Item b = a;

        a = null;
        System.out.println(b.id);

        b = null;
        System.out.println("references cleared");
    }
}
```

```bash
javac NullDoesNotDestroyDemo.java
java NullDoesNotDestroyDemo
```

```text
A
references cleared
```

After `a = null`, b still points to Item. After `b = null`, **in the simple model of this program**, no reference remains held that can be used to access Item from those variables.

However, there is no "destructor" that runs automatically right at `b = null`. Java only performs the assignment; the collector independently decides the memory cleanup process.

**Do not add `x = null` at the end of every method out of habit.** When scope/liveness is naturally short enough, pointless assignments only clutter the code; more importantly, avoid retaining unintended references in caches, collections, or long-lived fields.

## 18. Variable Scope Differs from Actual Reachability

A local variable has lexical scope according to the source code, but the VM/JIT can determine that an object is no longer needed before the variable goes out of scope. Conversely, an object can be returned or stored in a field and outlive the method that created it.

Let's distinguish:

| Concept | Question |
| --- | --- |
| Lexical scope | On which lines of code is the variable name still allowed to be used? |
| Definite assignment | Has the variable been validly assigned before being read? |
| Reference liveness | Might the reference value still be needed for use? |
| Object reachability | Is the object still on a reference path from appropriate roots? |
| Garbage collection | Has the VM decided/proceeded to collect the object yet? |

You cannot simply look at the position of a `}` brace in the source code and conclude that GC will destroy the object there. JVM optimizations, thread scheduling, and other references can all have an effect.

## 19. Two Objects Referencing Each Other in a Cycle Can Still Be Collected

In simple reference counting, reference cycles are difficult: each object still has a reference from the other object. Java's garbage collection **does not merely count references to each object**; tracing collectors can identify the entire unreachable group.

Create **`CyclicReferencesDemo.java`**:

```java
class Node {
    Node next;
}

public class CyclicReferencesDemo {
    public static void main(String[] args) {
        Node first = new Node();
        Node second = new Node();

        first.next = second;
        second.next = first;

        System.out.println(first.next == second);
        System.out.println(second.next == first);

        first = null;
        second = null;

        System.out.println("cycle no longer held here");
    }
}
```

```bash
javac CyclicReferencesDemo.java
java CyclicReferencesDemo
```

```text
true
true
cycle no longer held here
```

After the two assignments, if there are no other external references, **both Node objects, even though they point to each other, can become unreachable from roots** and can be reclaimed by GC.

You should not infer that a cycle causes a memory leak just because two objects hold each other. Memory retention occurs if **there is still a path from a root** to the group of objects, for example a static list holding first.

## 20. GC Eligibility and Actual Memory Reclamation Do Not Happen at the Same Time

When an object is no longer strongly reachable, we often say the object can become **eligible for garbage collection**. However:

- The JVM is not required to run GC immediately.
- The JVM is not required to reclaim the object immediately at a specific safepoint.
- Memory usage does not have to drop immediately in observation tools.
- The JVM may retain already allocated heap memory to serve later allocations.
- The time when an object becomes unreachable may not be directly observable through Java application logic.

Set of concepts:

```text
No appropriate strong reference path remains
        !=
GC has run
        !=
heap committed memory has decreased
        !=
OS memory is returned immediately
```

**Therefore:** Do not write unit tests like "assign null → memory must drop immediately" or "`System.gc()` → object must disappear immediately".

## 21. `System.gc()` Is Only a Request/Suggestion

Java provides `System.gc()`, but it should not be viewed as a command guaranteeing that collection completes at the time of the call.

Create **`GarbageCollectionRequestDemo.java`**:

```java
public class GarbageCollectionRequestDemo {
    public static void main(String[] args) {
        byte[] data = new byte[1024];

        System.out.println(data.length);
        data = null;

        System.gc();

        System.out.println("GC was requested");
    }
}
```

```bash
javac GarbageCollectionRequestDemo.java
java GarbageCollectionRequestDemo
```

```text
1024
GC was requested
```

The output only proves that the call and the print line executed. It does **not** prove that byte[] was collected.

Depending on JVM flags/implementation, calling GC explicitly may be ignored or have different behavior. Do not rely on `System.gc()` to close files, socket connections, or precisely control object lifecycles.

## 22. `null` References and the `NullPointerException` Error

`null` is not an object instance. If a `null` variable is used to directly call an instance method/read an instance field, the dereference operation usually causes a `NullPointerException`.

Create **`NullReferenceDemo.java`**:

```java
public class NullReferenceDemo {
    public static void main(String[] args) {
        StringBuilder text = new StringBuilder("hi");
        text = null;

        System.out.println(text == null);

        try {
            text.append("!");
        } catch (NullPointerException ex) {
            System.out.println("cannot dereference null");
        }
    }
}
```

```bash
javac NullReferenceDemo.java
java NullReferenceDemo
```

```text
true
cannot dereference null
```

`text = null` only changes the variable's value. Calling `text.append(...)` afterward is what causes the error because there is no object receiver.

**Do not confuse `null` with an object already reclaimed by GC**. Code cannot hold a valid strong reference pointing to "freed object memory" and use it like an ordinary C pointer; the JVM manages reachability and memory safety.

## 23. Object Lifetime Differs from Java Source Block Lifetime

Create **`ReturnReferenceDemo.java`**:

```java
class Message {
    final String text;

    Message(String text) {
        this.text = text;
    }
}

public class ReturnReferenceDemo {
    static Message create() {
        Message local = new Message("returned");
        return local;
    }

    public static void main(String[] args) {
        Message message = create();

        System.out.println(message.text);
    }
}
```

```bash
javac ReturnReferenceDemo.java
java ReturnReferenceDemo
```

```text
returned
```

The local variable `local` no longer exists after create returns, but the reference is returned to the caller. The object continues to be reachable from `message`.

**Distinguish this:** **Where** an object is created does not necessarily determine **how long** the object lives. A factory that creates and returns an object can produce an object that lives for most of the application's runtime.

## 24. A Static Field Can Keep an Object Alive for a Very Long Time

A static field can hold a strong reference for as long as the associated class/runtime structure remains live.

Create **`StaticRetentionDemo.java`**:

```java
class Registry {
    static StringBuilder current;
}

public class StaticRetentionDemo {
    public static void main(String[] args) {
        StringBuilder local =
                new StringBuilder("cached");

        Registry.current = local;
        local = null;

        System.out.println(Registry.current);

        Registry.current = null;
        System.out.println(
                Registry.current == null);
    }
}
```

```bash
javac StaticRetentionDemo.java
java StaticRetentionDemo
```

```text
cached
true
```

`local = null` does not make the StringBuilder unreachable while `Registry.current` still holds it. When the static field is also cleared, that reference path disappears.

**Common application mistakes:** An unbounded static Map/List, a listener registration that is not unregistered, a cache lacking TTL/eviction, or a ThreadLocal not removed in a thread pool can unintentionally retain a large object graph.

## 25. What Does a Memory Leak Mean in a GC Language?

In Java, a *memory leak* at the application level is usually **keeping objects that are no longer useful yet still reachable**; the collector is not allowed to reclaim them because references have not been released.

Example of a bad pattern:

```java
class History {
    private static final java.util.List<byte[]> ENTRIES =
            new java.util.ArrayList<>();

    static void add(byte[] data) {
        ENTRIES.add(data);
    }
}
```

This is an **illustrative declaration snippet**, not a recommendation. If the program calls add repeatedly without limit, ENTRIES can retain more and more arrays.

Ways to reduce retention usually include:

- Defining cache size/TTL/eviction.
- Removing entries when a workflow completes.
- Unregistering callbacks/listeners when no longer needed.
- Clearing ThreadLocal values in `finally` for reused threads.
- Not holding references to request/session objects in singletons unnecessarily.
- Using a heap dump/profiler when there is evidence to find root → object reference paths.

**GC cannot fix logic that still holds strong references** to data that is no longer useful.

## 26. Object References in Arrays/Collections Also Keep Objects Alive

Not only local variables and single fields: array elements, map keys/values, and list elements are also reference edges.

Create **`ArrayReferenceRetentionDemo.java`**:

```java
public class ArrayReferenceRetentionDemo {
    public static void main(String[] args) {
        Object[] slots = new Object[2];

        Object item = new Object();
        slots[0] = item;

        System.out.println(slots[0] == item);

        item = null;
        System.out.println(slots[0] != null);

        slots[0] = null;
        System.out.println(slots[0] == null);
    }
}
```

```bash
javac ArrayReferenceRetentionDemo.java
java ArrayReferenceRetentionDemo
```

```text
true
true
true
```

After `item = null`, `slots[0]` holds the reference. When `slots[0] = null`, that edge disappears.

**When implementing your own container** such as an array-backed stack, clear unused slots if they hold unneeded objects. Common Java collection implementations handle many cases automatically; the issue is usually keeping the container or elements for too long in business terms.

## 27. Objects Strongly Referenced via Lambdas/Callbacks

A lambda/anonymous object can capture a reference value, keeping the object reachable if the callback is still held in a long-lived place.

Create **`LambdaCaptureDemo.java`**:

```java
class CallbackStore {
    static Runnable callback;
}

public class LambdaCaptureDemo {
    public static void main(String[] args) {
        StringBuilder builder =
                new StringBuilder("hello");

        Runnable saved = () ->
                System.out.println(builder.toString());

        CallbackStore.callback = saved;
        CallbackStore.callback.run();

        CallbackStore.callback = null;
        System.out.println("callback cleared");
    }
}
```

```bash
javac LambdaCaptureDemo.java
java LambdaCaptureDemo
```

```text
hello
callback cleared
```

The lambda captures the `builder` variable as effectively final (without reassigning builder). If the callback is stored in a static field, the callback can also retain builder through the captured reference. Clearing the callback field removes one retention path; other references may still exist.

**Do not conclude** that builder has been GC'd immediately after callback cleared; the example only illustrates a reference path that can be retained or removed.

## 28. Reference Lifecycle Across Multiple Threads

An object can be created in thread A but placed into a queue or field for thread B to use. The object is not lost when the method in thread A ends if thread B still holds a live reference path to the object.

**Separate two concerns:**

- **Reachability:** The object can still be used by a thread through appropriate references.
- **Visibility/thread safety:** Does thread B accurately observe the state updated by thread A? This belongs to the Java Memory Model, synchronization, and safe publication.

An object kept alive by GC **does not mean** that operations on mutable fields are automatically thread-safe.

### Example of Immutable Data Passed Between Threads

Create **`ThreadReferenceDemo.java`**:

```java
record Task(String description) {
}

public class ThreadReferenceDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Task task = new Task("run");

        Thread worker = new Thread(() ->
                System.out.println(task.description()));

        worker.start();
        worker.join();

        System.out.println("worker completed");
    }
}
```

```bash
javac ThreadReferenceDemo.java
java ThreadReferenceDemo
```

```text
run
worker completed
```

The thread lambda holds a reference to task. `join()` makes main wait for worker to complete, making this output stable. A record with a String component is an appropriate example of immutable data; mutable shared state requires its own concurrency policy.

## 29. Weak Reference: Tracking an Object Without Holding Strong Ownership

Java provides `java.lang.ref.WeakReference<T>`. A weak reference does not prevent GC from collecting an object if the object is **only weakly reachable** according to reference processing rules. It is suitable for certain caches/metadata mappings whose lifetimes should not be kept alive solely by the tracking structure.

**However:** `weakReference.get()` can return T or null depending on GC; do not write tests predicting exact GC scheduling.

Create **`WeakReferenceConceptDemo.java`**:

```java
import java.lang.ref.Reference;
import java.lang.ref.WeakReference;

public class WeakReferenceConceptDemo {
    public static void main(String[] args) {
        Object strong = new Object();
        WeakReference<Object> weak =
                new WeakReference<>(strong);

        System.out.println(weak.get() != null);

        Reference.reachabilityFence(strong);

        strong = null;
        System.out.println("strong variable cleared");
    }
}
```

```bash
javac WeakReferenceConceptDemo.java
java WeakReferenceConceptDemo
```

```text
true
strong variable cleared
```

`Reference.reachabilityFence(strong)` ensures the referent remains strongly reachable up to the fence, so the read immediately before it is protected. After `strong = null`, there is no guarantee as to when the weak reference will be cleared.

**Do not do:** `System.gc(); assert weak.get() == null;`. The result is nondeterministic and can fail on a valid JVM.

## 30. Soft, Weak, and Phantom References Solve Different Needs

In `java.lang.ref`, there are reachability concepts and reference objects serving specialized use cases:

| Type | Idea | Notes |
| --- | --- | --- |
| Strong reference | Normal object usage | Can keep the object reachable |
| `SoftReference<T>` | Can be cleared according to memory pressure policy | Should not be relied upon as an exact cache policy |
| `WeakReference<T>` | Does not keep the referent alive when only weak reachability remains | `get()` can transition from a value to null |
| `PhantomReference<T>` | Tracks the phase after the referent is no longer accessible in the normal way | `get()` always returns null; usually paired with ReferenceQueue |
| `ReferenceQueue<T>` | Receives notifications of reference objects enqueued when processed by the JVM | Does not guarantee a fixed timing |

These types are not the default solution for most business classes. They mainly appear in cache designs, resource tracking, reachability-sensitive frameworks, and runtime infrastructure.

**Scope of this lesson:** Recognize reference strengths to understand object lifetime. Do not rush to use `PhantomReference` or write custom cleanup infrastructure when `try-with-resources` already solves resource scoping more simply.

## 31. `WeakHashMap` and Retention: Understanding Key/Value Behavior Correctly

`WeakHashMap<K,V>` has weak keys, so a key is not necessarily kept alive solely because of the map. However:

- The value is usually held by a strong reference in the entry while the entry still exists.
- If the value **indirectly holds a strong reference back to the key itself**, the key may remain strongly reachable via map → value → key, undermining the goal of weak key eviction.
- Entry removal depends on GC/reference processing and map operations, not a precise deadline.
- WeakHashMap does not replace a cache size/TTL policy when an application needs deterministic eviction.

**Do not infer that "using WeakHashMap guarantees no leaks".** Inspect the entire graph and ownership.

## 32. `Reference.reachabilityFence` Solves an Advanced Case

The VM may determine that a referent object is no longer needed before the end of its lexical scope. In resource wrappers or code interacting with native resources, we sometimes need to ensure that the object remains **strongly reachable up to a specific point**, even when there is no more ordinary Java use.

`Reference.reachabilityFence(object)` supports that situation.

**Do not overuse:** For ordinary application code, calling methods on the object and using references in scope is already clear enough. `reachabilityFence` is a specialized tool for reachability/finalization/cleanup interaction semantics, not a command to "keep an object alive forever" or a memory-freeing mechanism.

If used, place the fence **after the last operation that truly needs the object to remain reachable**, and ensure there is a strong reference to the object up to the fence call.

## 33. Garbage Collection Only Handles Memory, Not Closing Every Resource Automatically

A Java object can be a wrapper for resources outside the heap:

- `FileInputStream`/`FileOutputStream` → file descriptors.
- `Socket` → network endpoints.
- JDBC `Connection`/`Statement`/`ResultSet` → connection handles.
- Locks, native allocations, memory-mapped resources, transaction scopes.

If the wrapper object becomes unreachable, GC can reclaim **Java memory**; however, you have no right to infer that the external resource will be closed **in time**. Some libraries have their own cleanup fallback, but you should not depend on that timing.

**Proactive rule:** If a type implements `AutoCloseable` or `Closeable` and the contract requires closing, use `close()`/`try-with-resources` to determine when it is released.

## 34. `try-with-resources` Manages Resource Lifecycle Deterministically

Create **`TryWithResourcesDemo.java`**:

```java
class DemoResource implements AutoCloseable {
    DemoResource() {
        System.out.println("opened");
    }

    void use() {
        System.out.println("used");
    }

    @Override
    public void close() {
        System.out.println("closed");
    }
}

public class TryWithResourcesDemo {
    public static void main(String[] args) {
        try (DemoResource resource = new DemoResource()) {
            resource.use();
        }
        System.out.println("after try");
    }
}
```

```bash
javac TryWithResourcesDemo.java
java TryWithResourcesDemo
```

```text
opened
used
closed
after try
```

`try-with-resources` calls `close()` when the try resource scope ends, even when the body throws an exception according to the rules. It manages **external resource lifetime**, while whether the DemoResource Java object remains reachable depends on other references.

**Core difference:**

- `close()`: cleanup method executed according to deterministic control flow.
- GC: manages memory/reachability without an exact deadline.
- `close()` does not necessarily make the reference null or cause the object to be GC'd immediately.

## 35. Multiple Resources Are Closed in Reverse Order

Create **`MultipleResourcesDemo.java`**:

```java
class NamedResource implements AutoCloseable {
    private final String name;

    NamedResource(String name) {
        this.name = name;
        System.out.println("open " + name);
    }

    @Override
    public void close() {
        System.out.println("close " + name);
    }
}

public class MultipleResourcesDemo {
    public static void main(String[] args) {
        try (NamedResource first = new NamedResource("A");
             NamedResource second = new NamedResource("B")) {
            System.out.println("work");
        }
    }
}
```

```bash
javac MultipleResourcesDemo.java
java MultipleResourcesDemo
```

```text
open A
open B
work
close B
close A
```

Java closes resources in **reverse order** of successful initialization. This is useful when a later resource depends on an earlier resource.

A closed resource does not mean the Java wrapper object disappears. If you keep a reference, you can still call methods on the object, though methods may report "already closed" depending on the contract.

## 36. Exceptions in the Body and in `close()`

When the try body throws an exception and close also throws, Java keeps the main exception and attaches the exception thrown by close as a **suppressed exception**.

Create **`SuppressedExceptionDemo.java`**:

```java
class FailingResource implements AutoCloseable {
    @Override
    public void close() {
        throw new IllegalStateException("close failed");
    }
}

public class SuppressedExceptionDemo {
    public static void main(String[] args) {
        try (FailingResource resource =
                     new FailingResource()) {
            throw new IllegalStateException("body failed");
        } catch (IllegalStateException ex) {
            System.out.println(ex.getMessage());
            System.out.println(ex.getSuppressed().length);
        }
    }
}
```

```bash
javac SuppressedExceptionDemo.java
java SuppressedExceptionDemo
```

```text
body failed
1
```

Do not equate a resource close exception with GC. This is **exception handling defined by the Java language** during control flow, helping manage resources when errors occur.

## 37. `finalize()` Is Not a Reliable Destructor

Java used to have a finalization mechanism (`Object.finalize()`). However, it has been deprecated for a long time and is **deprecated for removal** in modern Java versions. It has serious issues:

- There is no guarantee about when a finalizer will run.
- It may not run before the program exits.
- There is a risk of the object being **resurrected** if the finalizer republishes the reference.
- Threading, concurrency, and errors are hard to control.
- It is unsuitable for ensuring critical resources are closed.
- It has security and performance impacts.

**Do not write** a new class relying on `finalize()` to print "object destroyed" or to close a file. Test programs waiting for finalizer output are nondeterministic.

For resources, use `AutoCloseable`/`try-with-resources`. For advanced fallback cleanup of certain native allocations, consider `Cleaner` according to the Java contract and careful design, though a cleanup fallback still has no deadline to replace explicit close.

## 38. `Cleaner` Also Does Not Replace Explicit Cleanup

`java.lang.ref.Cleaner` allows registering a cleanup action tied to an object's reachability. It is suitable for certain library/native resource abstractions.

However:

1. The cleanup action should not hold a strong reference to the referent itself, preventing cleanup from ever being triggered.
2. Cleanup timing depends on reference processing and runtime scheduling.
3. Cleanup may not occur before the process terminates.
4. The cleanup task should be idempotent and manage errors.
5. If users need to reliably close the resource at the end of a block, provide an explicit `close()`.

**Practical design:** `Cleaner` is a fallback for resource safety in specialized libraries; **`try-with-resources` is the primary path** when resource lifetime can be determined by application scope.

## 39. Unreachable Objects Have No Reliable "Destruction Callback"

Some languages have deterministic destructors called when scope ends; Java does not follow that model for ordinary objects.

Create class:

```java
class Message {
    Message() {
        System.out.println("created");
    }
}
```

With only a constructor, the "created" output does not bring a symmetric "destroyed" output when the variable leaves scope. There are no destructors automatically called by Java when a reference count drops to 0.

**Do not try to define lifecycle using logs from GC/finalizers.** Use explicit lifecycle operations like `start()/stop()`, `open()/close()`, or `AutoCloseable` when needed.

## 40. Object Creation Count and Usage Count Are Not the Same

One instance can be used multiple times without creating a new one:

```java
StringBuilder builder = new StringBuilder();
builder.append("A");
builder.append("B");
builder.append("C");
```

This is an **illustrative snippet**. There is only one explicit `new StringBuilder()`; the three append calls mutate the same object.

Conversely, a loop:

```java
for (int i = 0; i < 3; i++) {
    new Object();
}
```

has three class instance creation expressions evaluated under source semantics. The JVM may apply optimizations that do not change observable behavior; do not directly guess the number of physical heap allocations or GC actions from the number of occurrences of the `new` keyword.

**Profiling rule:** If performance truly matters, use an appropriate benchmark/profiler rather than guessing object allocation cost from syntax.

## 41. Escape Analysis and Stack Allocation: Avoid Absolute Claims

Modern JVMs can optimize object creation through escape analysis, scalar replacement, or other techniques. This means:

- You must not assume every `new` is definitely a physically existing heap allocation in a simple way.
- You must not claim a Java object "always lives on the stack" just because the reference is local.
- The Java Language Specification defines behavior; implementations have the right to optimize as long as observable semantics are preserved.
- JVM flags, compiler tiers, and workload affect optimization capability.

**Sensible learning model:** Picture objects on the heap and references pointing to them to understand reachability; when discussing performance/GC implementation, acknowledge that the VM may handle things differently internally.

## 42. An Object's Lifecycle May End for One Owner but Not for the Whole App

For example, a request handler drops its reference after processing; however, a global cache, an event bus, or a background task keeps a reference to the request object. To the request handler, the work is complete; to GC, the object is still reachable.

Ask questions about **ownership**:

- Who creates the object?
- Who is permitted to hold the reference?
- Is there an ownership transfer or shared ownership?
- When finished, which structure must clear/remove the reference?
- Is there a callback/task/closure holding the resource owner?
- Can the object close the resource even though the object itself stays alive?

You should not use `null` assignment as an **ownership protocol**. A good API should clarify who is responsible for closing or releasing logical associations.

## 43. Example of Managing an Owner via `close()` Separate from Reachability

Create **`ResourceOwnerDemo.java`**:

```java
class ResourceOwner implements AutoCloseable {
    private boolean closed;

    void work() {
        if (closed) {
            throw new IllegalStateException("already closed");
        }
        System.out.println("working");
    }

    @Override
    public void close() {
        closed = true;
        System.out.println("closed");
    }
}

public class ResourceOwnerDemo {
    public static void main(String[] args) {
        ResourceOwner owner = new ResourceOwner();

        owner.work();
        owner.close();

        System.out.println(owner != null);

        try {
            owner.work();
        } catch (IllegalStateException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

```bash
javac ResourceOwnerDemo.java
java ResourceOwnerDemo
```

```text
working
closed
true
already closed
```

After `owner.close()`, the object **is still reachable via the owner variable**, but the logical resource state is closed. Java object lifetime and resource usable lifetime are two different axes.

### Two-Axis Model

| Object reachable? | Resource open? | Possible? |
| --- | --- | --- |
| Yes | Yes | Yes, while in use |
| Yes | No | Yes, after close |
| No | Yes | Can occur due to forgetting to close; unsafe |
| No | No | Yes, if the resource is closed before the object loses reachability |

Do not use GC as a way to transition resource state from open to closed when a deadline is required.

## 44. When Should `try-with-resources` Be Used?

Use it when the resource type implements `AutoCloseable` and **the party holding resource ownership** needs to close it when the scope ends:

```java
try (java.io.BufferedReader reader =
         java.nio.file.Files.newBufferedReader(path)) {
    String line = reader.readLine();
    // Process line.
}
```

This is an **illustrative code snippet** that requires an appropriate Path-typed `path` variable in the method; it is not a standalone example.

**Do not close an object you do not own** just because it is AutoCloseable. For example, a stream/socket managed by the caller might be passed into a method; there must be an agreed contract on who closes it.

Avoid both mistakes:

1. Failing to close a resource that is your responsibility.
2. Closing a resource owned by someone else and causing subsequent callers to fail.

## 45. Object Pooling and Reuse: Do Not Confuse a Reused Object with a Newly Created One

A pool can return an existing instance instead of creating a new instance. Therefore, a "borrow resource" operation does not automatically create a new Java object.

```java
Connection connection = dataSource.getConnection();
```

This is a **conceptual example snippet**, requiring appropriate declarations/imports. A DataSource implementation may use connection pooling and return a wrapper handle; you should not infer the exact number of Java objects or network connections created from a single line of code.

**Even with pooling**, you must obey the API's `close()` contract; in many pools, closing the wrapper may return the connection to the pool instead of closing the physical connection. What must be ensured is **releasing ownership according to the API**, not guessing whether it corresponds to GC.

## 46. `WeakReference.get()` Returning null Does Not Prove a File Has Closed

If a weak reference to a resource wrapper becomes null, it tells you the referent can no longer be obtained through the weak reference. It does **not** prove that prior external resources were released on time or that a transaction was committed/rolled back.

Similarly:

- `System.gc()` does not replace `commit()/rollback()/close()`.
- `finalize()` is not a reliable destructor.
- `Cleaner` does not replace an explicit close deadline.
- Having a field `closed = true` on a class is only logical state; you must ensure the close implementation actually does the necessary work.

**Evaluate correctness according to the resource contract**, not according to indirect evidence of heap reachability.

## 47. Arrays Are Also Objects with a Lifecycle

In Java, arrays are objects. Example:

```java
int[] values = new int[3];
```

`values` is a reference to an array object. An array has a length and elements; array references can be stored, aliased, passed, and assigned null just like class instances.

Create **`ArrayLifecycleDemo.java`**:

```java
import java.util.Arrays;

public class ArrayLifecycleDemo {
    public static void main(String[] args) {
        int[] values = new int[3];
        int[] alias = values;

        alias[0] = 7;
        System.out.println(Arrays.toString(values));

        values = null;
        System.out.println(Arrays.toString(alias));
    }
}
```

```bash
javac ArrayLifecycleDemo.java
java ArrayLifecycleDemo
```

```text
[7, 0, 0]
[7, 0, 0]
```

After `values = null`, the array is still reachable via alias. Even though the elements are primitives, the array itself is still a reference object with identity.

For an array of objects such as `Person[]`, each element is a reference field holding another object (or null) and affects the reachability of the entire object graph.

## 48. Both Immutable Objects and Mutable Objects Are Subject to Reachability Management

A record or immutable class helps prevent state changes after construction. However, immutability **does not change GC rules**.

Example:

```java
record Coordinate(int x, int y) {
}
```

Two Coordinate instances can be equal by values yet have different object identities. If a strong reference from a root remains, an immutable instance is still reachable; if none remains, it can be reclaimed.

**Keep distinct:**

- **Immutability**: whether state can change after construction.
- **Reachability**: whether the object is still accessible through appropriate references.
- **Resource lifecycle**: when an external resource needs to be released.
- **Equality**: according to what contract two objects are considered equal.

These concepts are related in design, yet do not replace one another.

## 49. Diagnostic Questions for Memory Retention

When you observe the heap growing and suspect objects are not being released, do not immediately add `System.gc()` or null assignments. Check:

1. Are there collections/maps/static caches holding references?
2. Are cache TTL/eviction/lifecycle rules correct?
3. Was any listener/observer forgotten to be unregistered?
4. Are there thread pool tasks/queues holding captured references?
5. Is there a `ThreadLocal` that was not removed when threads are reused?
6. Are session/request objects attached to a singleton?
7. Is the live object count actually increasing across GC cycles?
8. Is there an external resource leak not directly related to the heap?
9. Are soft/weak references being used with the right semantics?
10. Is there a root → object path in a heap dump that explains the retention?

**Common diagnostic tools:** Java Flight Recorder (JFR), heap dumps, memory profilers, GC logs, Java Mission Control, or JVM-appropriate diagnostic utilities. Usage depends on the environment and access permissions.

Do not judge solely from a single observation of the process's memory footprint: committed heap memory can be retained for reuse even when the object count drops.

## 50. Common False Conclusions

| False claim | Correct understanding |
| --- | --- |
| "Leaving the block destroys the object" | A variable leaving scope does not mean the object has lost all references |
| "Assigning null immediately runs GC" | Null only removes one reference edge |
| "An object only has one variable pointing to it" | Multiple references can alias the same object |
| "`==` and `equals()` both check the same object" | `==` is identity; equals depends on contract |
| "Java passes objects by reference" | Java passes the **reference value** |
| "Every `new` definitely allocates a physical object on the heap" | The VM can optimize while preserving semantics |
| "A static field only holds small data" | A static field can retain an entire object graph |
| "Collections do not affect GC" | Strong element references can keep objects alive |
| "Reference cycles always leak" | Tracing GC can collect an unreachable group containing a cycle |
| "GC collects immediately when an object is unreachable" | There is no timing guarantee |
| "`System.gc()` guarantees memory is returned" | Only a request/hint, depends on the VM |
| "No references left means the file is definitely closed" | Resource cleanup is a separate contract |
| "`finalize()` is Java's standard destructor" | Unreliable and deprecated for removal |
| "`Cleaner` always runs before the app exits" | There is no timing guarantee |
| "`close()` makes the object disappear" | The object can still be reachable after close |
| "A reachable object means resources are definitely open" | It can be reachable yet already closed |
| "Immutable objects do not need GC" | Immutability is independent of reachability |
| "WeakReference keeps an object alive forever" | A weak reference does not guarantee strong reachability |
| "WeakHashMap solves every memory leak" | Values and other reference paths can still retain keys |
| "Lexical scope determines GC roots precisely" | JVM liveness/optimization is more complex |
| "Thread-safe because the object has not been GC'd" | Reachability differs from synchronization |
| "Logging in a finalizer is the standard way to measure lifetime" | Finalizer scheduling is nondeterministic |
| "Heap committed memory not decreasing means an object leak" | Heap memory can be retained for reuse |

## 51. Comprehensive Example: Create, Alias, Store, and Drop References

Create **`LifecycleWalkthroughDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

class Message {
    private final String text;

    Message(String text) {
        this.text = text;
        System.out.println("constructed:" + text);
    }

    String text() {
        return text;
    }
}

public class LifecycleWalkthroughDemo {
    public static void main(String[] args) {
        List<Message> inbox = new ArrayList<>();

        Message original = new Message("hello");
        Message alias = original;

        inbox.add(original);

        System.out.println(original == alias);
        System.out.println(inbox.get(0).text());

        original = null;
        alias = null;

        System.out.println(inbox.get(0).text());

        inbox.clear();
        System.out.println(inbox.isEmpty());
        System.out.println("no GC timing claim");
    }
}
```

```bash
javac LifecycleWalkthroughDemo.java
java LifecycleWalkthroughDemo
```

```text
constructed:hello
true
hello
hello
true
no GC timing claim
```

Chronological explanation:

1. `new Message("hello")` creates an instance and the constructor prints a line.
2. `original` and `alias` point to the same instance, so `==` is true.
3. `inbox.add(original)` creates a strong reference path from the List to the instance.
4. Both variables are assigned null, yet inbox still holds the message.
5. `inbox.clear()` removes the reference path from the list.
6. The program does **not** assume GC runs/has run after clear.

This is how to describe **observable application behavior** without fabricating a destructor timing.

## 52. Self-Test: Checking Reference Semantics Without Depending on GC

Create **`ObjectLifecycleSelfTest.java`**:

```java
import java.util.ArrayList;
import java.util.List;

class Payload {
    final int id;

    Payload(int id) {
        this.id = id;
    }
}

public class ObjectLifecycleSelfTest {
    static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        Payload original = new Payload(7);
        Payload alias = original;

        check(original == alias, "shared identity");

        List<Payload> holder = new ArrayList<>();
        holder.add(original);

        original = null;

        check(alias.id == 7, "alias still valid");
        check(holder.get(0) == alias, "list keeps same object");

        holder.clear();
        check(holder.isEmpty(), "holder cleared");

        alias = null;

        System.out.println("reference semantics PASS");
    }
}
```

```bash
javac ObjectLifecycleSelfTest.java
java ObjectLifecycleSelfTest
```

```text
reference semantics PASS
```

The checks are deterministic: identity, aliasing, and list ownership in the source code. The test does not need `-ea` enabled because `check` explicitly throws AssertionError.

**Do not use weak-reference disappearance as a PASS condition** for an ordinary unit test; GC scheduling is not an input controllable by calling System.gc.

## 53. Exercise 1: Draw the Graph and Mark Reachability

Given the code snippet:

```java
class Box {
    Box next;
}

Box a = new Box();
Box b = new Box();
Box c = new Box();

a.next = b;
b.next = c;

Box root = a;
a = null;
b = null;
c = null;
```

This is an **illustrative snippet** in a method with an appropriate Box declaration.

**Question:** Have the three Box objects become unreachable yet?

**Answer:** Not necessarily. `root` still references the original object a; through `root.next` and `root.next.next`, all three still have a reachable path in the model. Only when the path from root is lost (and there is no other root) can the group become unreachable.

**Advanced:** Change `root.next = null` before dropping root. Then b and c can become a separate unreachable group if there is no other path to them, even though root still holds a.

## 54. Exercise 2: Find the Resource Lifecycle Design Flaw

The following code has an issue:

```java
void read() throws java.io.IOException {
    java.io.BufferedReader reader =
            java.nio.file.Files.newBufferedReader(path);
    String line = reader.readLine();
    System.out.println(line);
}
```

This is an **illustrative method snippet** with a `path` variable assumed to be valid.

Issue: reader may not be closed in time, especially when readLine or print throws an exception. You cannot rely on GC of reader to ensure the resource is closed promptly.

### Fixed Version

```java
void read() throws java.io.IOException {
    try (java.io.BufferedReader reader =
                 java.nio.file.Files.newBufferedReader(path)) {
        String line = reader.readLine();
        System.out.println(line);
    }
}
```

Use `try-with-resources` to close according to control flow. This is still a **method snippet**; running it requires an actual class and Path field/parameter.

## 55. Exercise 3: Distinguish Three Lifecycle Milestones

Name the following milestones:

1. `new Widget()` starts creating an instance.
2. `Widget w2 = w1` copies the reference value.
3. `w1 = null` removes one reference.
4. `w2 = null` removes another reference.
5. GC can reclaim the object at some point.
6. `resource.close()` returns the resource to the closed state.

**Answer:**

1. Object creation/initialization.
2. Reference aliasing.
3. Reference reassignment; cannot yet conclude the object is unreachable.
4. Can become unreachable if there is no other reference path.
5. Garbage collection without a fixed deadline from the source.
6. Explicit resource cleanup; does not mean memory is freed.

## 56. Exercise 4: Analyze the Constructor Chain

Predict the output:

```java
class A {
    A() {
        System.out.println("A");
    }
}

class B extends A {
    B() {
        System.out.println("B");
    }
}

class C extends B {
    C() {
        System.out.println("C");
    }
}
```

If `new C()`:

```text
A
B
C
```

Superclass constructors run before subclass constructor bodies along the chain. There are not three independent objects A, B, and C; all of them are the construction path of **one C instance**.

## 57. Object Lifecycle Review Checklist

- [ ] Clearly distinguish between an **object instance** and a **reference variable**?
- [ ] Understand that `new`, constructor, and class initialization are not identical?
- [ ] Know the default values of fields before initializers?
- [ ] Know that superclass initialization precedes subclass initialization?
- [ ] Avoid calling overridable methods from a constructor when subclass state is not ready?
- [ ] Constructor validation protects invariants?
- [ ] Do not publish `this` too early during construction?
- [ ] Understand that Java passes references **by value**?
- [ ] Identify alias references to an object?
- [ ] Distinguish `==` and `equals()` when drawing an object graph?
- [ ] Know that an object can escape local scope through return/field/collection?
- [ ] Do not tie an object's lifetime to a single local variable?
- [ ] Recognize that static caches, ThreadLocal, listeners, and background tasks can hold references?
- [ ] Know that a cycle does not cause a leak on its own if no path from GC roots remains?
- [ ] Do not rely on `null` assignment to force GC to run?
- [ ] Do not rely on `System.gc()` to guarantee freeing?
- [ ] Do not write deterministic tests relying on a weak reference having to be cleared immediately?
- [ ] Understand soft/weak/phantom references to the degree needed?
- [ ] Do not use finalize as a destructor?
- [ ] Use `AutoCloseable`/`try-with-resources` when owning a resource?
- [ ] Do not close a resource owned by the caller without a contract?
- [ ] Distinguish between a closed resource and an unreachable object?
- [ ] Do not infer absolute physical runtime heap allocations from `new`?
- [ ] For shared mutable objects, evaluate safe publication/thread safety independently of reachability?
- [ ] When suspecting a memory leak, check root → object paths with appropriate tools?
- [ ] Do runnable examples have a file/public class, `javac`/`java` commands, and verified stdout?

## 58. Review Questions with Answers

**1.** Are a reference variable and an object the same thing?

*No. A reference variable holds a reference value (or null); the object is the referenced instance.*

**2.** Does `Person b = a` create a new Person?

*No, it only copies the reference.*

**3.** Does `a = null` destroy the object immediately?

*No, it only reassigns the reference variable.*

**4.** If `b` still points to the object after `a = null`, is the object reachable?

*Yes, if b is a live strong reference still used by the program.*

**5.** Does leaving the method that created an object force the object to be GC'd?

*No. The reference can be returned or stored outside the method.*

**6.** If an object no longer has a path from roots, is GC guaranteed to collect it immediately?

*There is no timing guarantee.*

**7.** Does `System.gc()` guarantee that an object is freed?

*No.*

**8.** How many references can a created object have?

*There is no limit of one reference; multiple variables/fields/array elements can point to it.*

**9.** Is a cycle A → B → A always a memory leak?

*No. Tracing GC can collect the entire group when it is no longer reachable from roots.*

**10.** Can a static field keep an object alive longer than a local scope?

*Yes.*

**11.** Does a subclass's constructor body run before the superclass?

*No; the superclass initialization path runs first.*

**12.** What initial value does an instance field int that has not been explicitly initialized have?

*0.*

**13.** Can an unassigned local variable int be read as 0?

*No; definite assignment is required.*

**14.** What can calling an overridable method from a superclass constructor cause?

*The subclass override sees subclass fields that have not been explicitly initialized, only in their default state.*

**15.** If a constructor throws an exception, does the new expression return an object normally?

*No. However, if this escaped, a reference to the partially initialized object may still exist.*

**16.** Can an immutable object be GC'd?

*Yes; immutability does not determine reachability.*

**17.** Does `equals()` true mean the same object identity?

*No; `==` compares reference identity.*

**18.** Does `WeakReference` hold a strong reference to its referent?

*No; a weak reference does not guarantee the object stays alive when strong reachability no longer exists.*

**19.** Should you assert weak.get()==null after System.gc?

*No; GC is not deterministic.*

**20.** What is `Reference.reachabilityFence` for?

*To ensure the referent remains strongly reachable up to a point in control flow when needed, especially in resource/native scenarios.*

**21.** Does `close()` mean the object is GC'd?

*No; close releases the logical/external resource according to the contract, and the object may still be reachable.*

**22.** When `AutoCloseable` is present, what is the recommended pattern?

*Try-with-resources with an appropriate ownership contract.*

**23.** In what order are multiple resources in a try closed?

*In reverse order of successful initialization.*

**24.** Is finalization a reliable destructor?

*No; it is deprecated for removal and has no timing guarantee.*

**25.** Does `Cleaner` replace a close deadline?

*No, it is suitable for specialized fallbacks.*

**26.** Is a list holding an unused object memory retention?

*Possibly; if the list is reachable and still has a strong element reference, GC keeps the object.*

**27.** Why is heap usage not dropping immediately after GC not necessarily a leak?

*The JVM may keep committed heap memory for reuse.*

**28.** Does Thread B using an object created by Thread A make the object outlive A's method?

*Possibly, if a live reference path exists; safe publication is needed for mutable state.*

**29.** Does `new` always mean a measurable physical heap allocation?

*It must not be stated absolutely; the JVM can optimize as long as observable semantics are preserved.*

**30.** What is a one-sentence summary of the Java object lifecycle?

*An object is created and initialized, used through references, can become unreachable when all appropriate strong reference paths are lost, and is reclaimed by GC at a time determined by the JVM; external resources require proactive cleanup.*

## 59. Authoritative References

- *Java Language Specification, Java SE 17 — `12 Execution:* https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html — class initialization, instance creation, and initialization.
- *Java Language Specification, Java SE 17 — `15.9 Class Instance Creation Expressions:* https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9 — `new` semantics and constructor invocation.
- *Java API — `java.lang.ref`:* https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html — reference objects and reachability concepts.
- *Java API — `java.lang.ref.Reference.reachabilityFence`:* https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html — keeping a referent strongly reachable up to a point in code.
- *Java API — `AutoCloseable`:* https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html — resource closing contract and try-with-resources.

---

**End-of-lesson takeaway:** A Java object's lifecycle begins with **instance creation/initialization**, continues with **usage through one or more references**, and can then transition to being **no longer reachable** when no appropriate strong reference path from GC roots remains. **Assigning null**, **exiting a method**, or **clearing a collection** only removes specific reference paths; it does not by itself prove the object has been GC'd. GC can reclaim groups of unreachable objects, including cycles, but **does not promise a reclamation time** or when memory will be returned to the OS. In particular, **closing resources is not GC's responsibility**: use `close()` and `try-with-resources` according to the ownership contract. Clearly understanding identity, aliasing, the object graph, liveness, and resource lifecycle will help avoid leaks, initialization bugs, and false assumptions about the JVM.
