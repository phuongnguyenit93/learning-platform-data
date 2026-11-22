# Final Field Rules, Initialization Completion, and Safe Object Publication in the Java Memory Model

## Lesson Objectives

One thread creates an object, assigns its fields in the constructor, and then passes that object's reference to another thread. Is the reading thread **guaranteed to see all assigned fields**? This cannot be answered merely with "the constructor has finished running". In the Java Memory Model (JMM), whether a reading thread is guaranteed to see the writes of the creating thread depends on **happens-before**, the form of **publication**, and **special rules for final fields**. If the `this` reference leaks out before the constructor finishes, even the special guarantee of `final` can be broken.

This lesson focuses on three distinct questions:

1. **Initialization completion:** did the constructor establish invariants and complete properly before the object is observed from another thread?
2. **Reference publication:** by what mechanism does another thread receive the reference: racy ordinary field, `volatile`, synchronized, class initialization, thread start, concurrent collection, or Future?
3. **Post-publication usage:** is the object truly immutable? If it remains mutable, what synchronizes the writes/reads that occur later?

After this lesson, you will be able to:

- Accurately interpret §17.4 and §17.5 of the **Java Language Specification**, especially `happens-before`, `synchronizes-with`, `freeze action`, and the concept of **properly constructed**.
- Distinguish `final`, `volatile`, and `synchronized`; recognize that **final-field initialization safety differs from full safe publication**.
- Avoid `this`-escape via a static field, registry, listener, callback, thread started in a constructor, or overridable method.
- Understand why `final List<T>` or `final byte[]` does not make the elements immutable; know how to use defensive copies and snapshots.
- Safely publish an object using `volatile`, a monitor lock, `AtomicReference`, class initialization, `Thread.start()`, `BlockingQueue`, `Future.get()`, or an appropriate concurrent tool.
- Correctly write **double-checked locking** with `volatile`, or choose the initialization-on-demand holder when appropriate.
- Verify runnable Java 17+ code, distinguishing **deterministic stdout** of synchronized examples from **non-deterministic results** of programs intentionally containing a data race.
- Use code review, stress testing, and OpenJDK **jcstress** to study memory ordering, without relying on `Thread.sleep()` as a correctness test.

## 1. How is an object created?

When running:

~~~java
Profile p = new Profile("Lan", 20);
~~~

this is an **illustrative snippet** requiring an appropriate `Profile` class. HotSpot/JVM must implement the exact Java semantics, typically involving:

1. Allocating or representing the object with instance fields initially having **default values** per the JLS, e.g. `0`, `false`, `null`.
2. Executing instance field initializers / instance initializers and the constructor chain in the order specified by Java.
3. Executing statements in the constructor to assign fields and establish invariants.
4. The constructor completes normally, after which the `new Profile(...)` expression returns the reference to the caller.

At the implementation level, the JIT can optimize aggressively, such as **escape analysis/scalar replacement** eliminating physical allocation in valid cases. However, optimizations must preserve JMM behavior, including the special guarantee of `final`.

**Two things must not be conflated into one:**
- The constructor **completes** in thread A.
- Thread B **is guaranteed to see the writes** that thread A performed.

If A writes the reference into an ordinary shared field and B reads it without synchronization, there can be a **data race**. Even if the code on A runs in source order, Java does not by default provide a happens-before edge from writes in A to reads in B just because wall-clock time at B comes later.

## 2. Happens-before, program order, and synchronizes-with

According to JLS §17.4.5, if action X **happens-before** action Y, X is ordered/visible to Y under the JMM. This is a relation built from program order within a single thread and **synchronizes-with** edges, along with appropriate transitivity.

Commonly used edges:

| Event | Guarantee in the JMM |
| --- | --- |
| Program order within a single thread | Earlier action happens-before later action in the same thread |
| Monitor `unlock` then subsequent `lock` on the same monitor | Unlock synchronizes-with subsequent lock |
| `volatile write` then subsequent `volatile read` of the same variable | Write synchronizes-with read according to volatile synchronization order |
| `Thread.start()` | Actions before start happens-before actions in the started thread |
| Thread termination detected by a successful `join()` | Actions in the worker happens-before actions after join in the waiting thread |
| `java.util.concurrent` APIs | Additional memory consistency effects depending on class/method contract |
| Class initialization | JVM performs necessary synchronization for initialization safety when the class is used |

Example of volatile publication:

~~~text
THREAD A (writer)                       THREAD B (reader)

obj = new Config(...);
  constructor writes
shared = obj;                 <---      Config c = shared;
  volatile write                         volatile read
                                            |
                                            v
                                        reads c.fields

                 happens-before chain
          constructor writes -> volatile write
            -> volatile read -> field reads
~~~

The diagram requires `shared` to be declared **volatile**, and the reader to actually read that variable and observe the published reference in the proper sequence. Merely having the `volatile` keyword on an unrelated field does not make every object/field in the program safe.

### Happens-before is not just "coming earlier in time"

If two threads access an ordinary field without proper ordering, thread A running earlier in wall-clock time does not create happens-before. OS cache coherence, CPU scheduling, and test runs that print the expected value are **not proof** that publication has a JMM guarantee.

Conversely, if properly synchronized, the JVM/JIT and hardware may reorder optimizations underneath, but **must not break** Java-level observable guarantees.

### Data race and visibility

Example:

~~~java
final class Data {
    int a;
    int b;
}

static Data shared; // ordinary, not volatile
~~~

These are class/field snippets. The writer can run `shared = new Data(); shared.a=1; shared.b=2;` and the reader can run `Data d=shared; if(d!=null) print(d.a,d.b);` without HB. The reader may see the reference along with unexpected field values, or encounter timing errors. Moreover, fields written **after being published** are even less protected by any final-constructor guarantee.

**Do not write benchmarks expecting a fixed output for a data race.** A single run always printing 1,2 does not prove it is guaranteed.

## 3. final field: special guarantee from JLS §17.5

Example class:

~~~java
final class Point {
    final int x;
    final int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }
}
~~~

If `Point` is **properly constructed** — specifically, the reference to the object **is not made visible to another thread before the constructor completes** — the JMM provides special guarantees for reads of `final` fields, **even when the object reference is passed through a racy ordinary field**.

The JLS describes `final` fields:
- Initialized once in the normal way, the compiler is allowed to optimize reads more aggressively than an ordinary mutable field.
- There is a **freeze action** associated with a final field when the constructor that writes that field **ends**.
- A thread reading a reference to an object that has completed initialization is guaranteed to see the **correct value of final fields** per final-field semantics.
- For an object/array referenced by a final field, writes performed appropriately before the freeze have a special visibility guarantee **through that dereference path**.

**This is not a general full happens-before edge from the constructor to every arbitrary field read.** The JLS specifies a **dereference chain** and **memory chain** mechanism for final fields; the special HB is used in a specific value-determination rule, and cannot be applied transitively as an arbitrary global synchronization edge.

### Illustration of the pattern in the JLS

~~~java
final class Example {
    final int finalized;
    int ordinary;

    Example() {
        finalized = 42;
        ordinary = 17;
    }
}
~~~

If the constructor completes, and then the reference is published **racily**:

~~~java
static Example shared; // ordinary field, illustrative example
// writer:
shared = new Example();
// reader in another thread:
Example e = shared;
if (e != null) {
    int a = e.finalized;
    int b = e.ordinary;
}
~~~

**Careful interpretation:**
- If the reader has seen a reference to the properly initialized instance, final-field semantics guarantee `a == 42`.
- There is no ordinary HB from writer to reader, so **there is no equivalent guarantee for `b`**; default `0` or `17` may be observed in JMM-compliant executions.
- There is no guarantee the reader will **promptly or ever see `shared != null`**, because the reference is passed through a data race.
- If the constructor has a `this`-escape before assigning `finalized`, the conclusion above cannot be used.

**Engineering recommendation:** even though `final` has special initialization safety, **use safe publication for the entire object** so readers have a clear happens-before, rather than intentionally relying on racy publication.

## 4. What is a freeze action? Not freezing the entire heap

A model:

~~~text
Thread A creates Object O

ALLOCATE O (default fields)
        |
        v
constructor:
    write final x = 42
    write ordinary y = 17
        |
        v
constructor exit  ---> FREEZE of final x
        |
        v
O is passed where another thread can see it
        |
        v
Thread B reads O.x via an appropriate reference
    -> final field is protected by JMM 17.5
~~~

**Freeze is a Java Memory Model concept**, not calling a public API or forcing HotSpot to lock all CPU cache lines. JLS 17.5.1 specifies a freeze when the constructor that has a write to a final field finishes (including constructor delegation details; the specification also considers abrupt completion). Do not generalize freeze into "all fields become volatile".

### If a constructor calls another constructor

~~~java
final class Pair {
    final int a;
    final int b;

    Pair(int a) {
        this(a, 0);
    }

    Pair(int a, int b) {
        this.a = a;
        this.b = b;
    }
}
~~~

Constructor delegation with `this(...)` has freeze rules tied to the constructor performing the writes. When designing a class, it is still necessary **not to let `this` escape along the entire construction path**, because another thread could see the object before initialization of the entire hierarchy completes.

### Is a final field assigned at declaration different?

~~~java
final class Status {
    final int code = 200;

    Status() {
        // Additional initialization can be performed.
    }
}
~~~

This is an **instance final constant-variable-like expression**, but what matters for this lesson is final field initialization semantics when the object is properly constructed. The compiler can inline the literal very early; do not use `Status.code==200` in every test to conclude safe publication for other mutable fields.

### final fields modified via reflection/Unsafe

JLS §17.5.3 has special cases for deserialization/reflection, but normal application code **must not rely on modifying a final field after construction**. Such changes can have visibility/optimization surprises; strong encapsulation, records, and newer JDKs continue to restrict deep reflection or unsafe mutation.

Safe mindset: treat final fields as **only set in the constructor/instance initializer**; do not use reflection to change them after publication.

## 5. Properly constructed: why must `this` not escape?

An object can leak out of a constructor through:
- Assigning `this` to a static/shared field.
- Registering `this` as a listener/callback in an external registry, where another thread can run the callback immediately.
- Starting a thread in the constructor where the Runnable captures `this`.
- Submitting a task to an executor in the constructor, where the task references fields of the object being created.
- Putting `this` into a concurrent collection before the constructor completes.
- Calling an overridable instance method from the constructor, where a subclass override publishes the object or reads uninitialized fields.
- Calling a third-party method and passing `this` when you do not control what that method does.

### Anti-pattern: early registration

~~~java
final class UnsafeListener {
    final int id;

    UnsafeListener(Registry registry) {
        registry.register(this); // this can be seen by another thread
        id = 42;
    }
}
~~~

This is an **illustrative snippet**, requiring an appropriate `Registry` definition. If the registry makes the object visible before `id=42`, another thread may read `id=0` (default value) in an execution schedule, and the final-field initialization guarantee for this instance **no longer applies as a properly constructed object**.

A registry using `volatile`, `ConcurrentHashMap`, or `synchronized` **cannot save** an object published **before its fields are assigned**. Safe publication can publish an object **that has not finished construction** clearly and validly in terms of ordering, but the result still lacks data if published too early.

### Anti-pattern: calling an overridable method in a constructor

~~~java
class Base {
    Base() {
        initialize(); // dynamic dispatch can call subclass
    }

    void initialize() { }
}

class Child extends Base {
    final int value = 42;

    @Override
    void initialize() {
        // value may not yet be initialized when Base() calls this.
        System.out.println(value);
    }
}
~~~

These are **two class fragments**. The key point: in Java, dynamic dispatch occurs even while executing the base constructor, when subclass field initializers have not yet completed. Besides the risk of publishing `this`, this is also a source of observing **partially initialized subclass state**.

With a final constant initialized by a compile-time literal, the compiler can inline the value, causing the printed example not to clearly reflect the issue. To demonstrate the real situation, use a subclass instance field that is not a compile-time constant and organize the code carefully; do not promise the output of the fragment above.

### Fix: factory that registers after the constructor completes

~~~java
final class Listener {
    final int id;

    private Listener(int id) {
        this.id = id;
    }

    static Listener createAndRegister(Registry registry, int id) {
        Listener listener = new Listener(id);
        registry.register(listener);
        return listener;
    }
}
~~~

This is a code snippet requiring `Registry`. When `new Listener(id)` returns, the constructor completes before `register` is called. The registry still needs **appropriate publication semantics** for other readers, and mutable state must not be modified without synchronization afterward.

## 6. final reference is different from deep immutability

Consider:

~~~java
final class Bag {
    final int[] values;

    Bag() {
        values = new int[] {4, 5};
    }
}
~~~

What `final` forbids under normal Java language rules is **reassigning the reference field**:

~~~java
// bag.values = new int[] {1, 2};  // compile-time error
bag.values[0] = 99;               // valid
~~~

These are snippets, requiring an appropriate `bag` variable.

Diagram:

~~~text
[Bag object]
    final values -------+
                        |
                        v
                    [int array]
                    [4][5]
                        |
                    element 0 mutable

FINAL: reference field cannot be reassigned in Java source
NOT FINAL: array elements are mutable data
~~~

### Guarantee when arrays are initialized before freeze

JLS §17.5 explains that for an array/object referenced through a final field, appropriate writes that occurred **before the freeze** have a special visibility guarantee when another thread dereferences through that final field. Therefore, if the constructor creates an array and populates its elements before finishing, a reader reading through the final reference can be protected for the initial state.

However, **after the object has been published**, if one thread modifies `values[0]` while another thread reads it without synchronization, that can still be a **data race on the array element**. The guarantee of a final reference does not turn every future mutation into a volatile write.

Nor can one arbitrarily infer "every object reachable at multiple levels is automatically immutable" from a single final reference. With nested mutable graphs and external aliases, one must examine the exact write/read paths and ownership.

### Defensive copying

If a class needs an immutable snapshot of an array provided by the caller:

~~~java
final class ByteMessage {
    private final byte[] payload;

    ByteMessage(byte[] incoming) {
        this.payload = incoming.clone();
    }

    byte[] payload() {
        return payload.clone();
    }
}
~~~

Without cloning in the constructor, the caller still holds `incoming` and can modify the array after passing it into the object. If returning the raw `payload` in the getter, the caller can modify internal state. **Cloning both on the way in and on the way out** avoids aliasing at the level of a primitive array. For nested arrays or mutable element objects, deep copying or appropriate ownership/immutability design is needed.

**`List.copyOf`, `Map.copyOf`, and `Collections.unmodifiableList` do not automatically deep-copy mutable objects inside.** An immutable container does not mean an immutable element graph.

## 7. Standalone runnable Java 17+ example: immutable snapshot and defensive copy

Create file **`ImmutableSnapshotDemo.java`**:

~~~java
import java.util.Arrays;

public class ImmutableSnapshotDemo {
    static final class Message {
        private final String id;
        private final byte[] payload;

        Message(String id, byte[] source) {
            this.id = id;
            this.payload = source.clone();
        }

        String id() {
            return id;
        }

        byte[] payload() {
            return payload.clone();
        }

        int firstByte() {
            return Byte.toUnsignedInt(payload[0]);
        }
    }

    public static void main(String[] args) {
        byte[] input = {1, 2, 3};
        Message message = new Message("m1", input);

        input[0] = 9;
        byte[] externalCopy = message.payload();
        externalCopy[1] = 8;

        System.out.println("id=" + message.id());
        System.out.println("first=" + message.firstByte());
        System.out.println("snapshot=" +
                Arrays.toString(message.payload()));
        System.out.println("input=" + Arrays.toString(input));
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 ImmutableSnapshotDemo.java
java ImmutableSnapshotDemo
~~~

**Exact stdout:**

~~~text
id=m1
first=1
snapshot=[1, 2, 3]
input=[9, 2, 3]
~~~

Explanation:
1. `Message` has final reference fields and does not let `this` escape.
2. `payload` is cloned in the constructor, so the caller modifying `input[0]` does not affect the snapshot.
3. The getter returns a new clone, so the caller modifying `externalCopy[1]` does not affect the internal array.
4. There are no writes to the internal array after construction, so this is an object with **effective immutability** at the API boundary shown above.
5. The code only demonstrates copy/encapsulation semantics; it **does not trigger or observe a freeze event** directly. Freeze is a JMM model implemented by the JVM.

If the data is `List<MutableUser>`, copying the list of references does not automatically snapshot each mutable user. An immutable element type or deep-copying as needed must be designed.

## 8. final field visibility is not equal to safe publication

Comparison table:

| Scenario | final fields of a properly constructed object | ordinary fields initialized before publication | updates after publication |
| --- | --- | --- | --- |
| Reference via **ordinary field, data race** | Has **final-field guarantee** when reader sees the object properly | No full happens-before guarantee solely from final | No guarantee if continuing racy |
| Reference via **volatile field** | Guaranteed if properly constructed | Writes before volatile publish are ordered to subsequent volatile read | Needs synchronization for post-publish updates |
| Reference under **the same monitor lock** | Guaranteed | Writes before unlock are ordered to subsequent lock/read | Must protect mutable access with proper lock/discipline |
| Reference in **safely initialized class** | Guaranteed | Initialization visibility per class init | Mutable fields afterward still need synchronization |
| Reference via **BlockingQueue/Future** per contract | Guaranteed | Handoff memory consistency per API | Post-publication can still have races if mutated |
| Reference via **Thread.start()** before worker actions | Guaranteed | Actions before start HB worker actions | Concurrent writes after start do not automatically HB |
| Reference escapes **before constructor exit** | No normally constructed guarantee | Risk of seeing partial state | Continues to need synchronization |

**Important:** outside the clause "reader sees the object/reference", racy publication can also suffer visibility/liveness issues on **the reference itself**. Final-field semantics do not force the publisher to publish the reference promptly or make every reader eventually see non-null.

### Useful review questions

1. When does the constructor complete? Can the object be seen by a registry/callback before that?
2. Is the reference in an ordinary field, volatile field, or concurrent container?
3. Through what path does the reader read the reference, and does it share the same synchronization protocol?
4. Which fields are final; which fields are mutable; which elements/referents are mutable?
5. Are there writes after publishing? What mechanism protects each write/read?
6. Does a getter return an alias to an internal mutable graph?
7. Is there a subclass override/callback from the constructor?
8. Is there a dependency that is a native/reflection/serialization framework modifying final fields?

## 9. Safe publication with volatile

Example of a snapshot object containing both final and ordinary fields, with a **volatile** reference variable:

~~~java
final class Settings {
    final String region;
    int timeoutMs;

    Settings(String region, int timeoutMs) {
        this.region = region;
        this.timeoutMs = timeoutMs;
    }
}

static volatile Settings current;
~~~

These are class/field snippets; `current` needs to be declared in a valid class.

Writer:

~~~java
current = new Settings("ap-southeast", 300);
~~~

Reader:

~~~java
Settings snapshot = current;
if (snapshot != null) {
    use(snapshot.region, snapshot.timeoutMs);
}
~~~

The above are snippets; the `use` method is only illustrative. If the reader observes the published reference via a **volatile read**, all constructor writes before the volatile write have HB to subsequent reads. Thus the ordinary field `timeoutMs` also has a visibility guarantee **for the value written before publication**.

**However:** if the writer thread later runs `current.timeoutMs = 500;` while the reader continues reading `timeoutMs` without synchronization, the volatile nature of the **reference field `current`** does not automatically make `timeoutMs` volatile. Instead of mutating the snapshot, one can publish **a new immutable object** through the same volatile reference.

### Read volatile once when snapshot consistency is needed

~~~java
Settings snapshot = current;
if (snapshot != null) {
    // use all fields from the same snapshot
}
~~~

Use a local `snapshot` to ensure the same instance across logical reads. If reading `current` multiple times in between and another thread replaces the reference, the code could take `region` from instance A and `timeout` from instance B, causing a "mixed configuration", even though each individual volatile read is valid.

## 10. Standalone runnable Java 17+ example: publishing an immutable snapshot with volatile

Create file **`VolatilePublicationDemo.java`**:

~~~java
public class VolatilePublicationDemo {
    static final class Config {
        final String label;
        final int port;

        Config(String label, int port) {
            this.label = label;
            this.port = port;
        }
    }

    private static volatile Config published;

    public static void main(String[] args)
            throws InterruptedException {
        Thread writer = new Thread(() -> {
            Config next = new Config("READY", 8080);
            published = next; // volatile publication
        });

        writer.start();
        writer.join();

        Thread reader = new Thread(() -> {
            Config snapshot = published; // volatile read
            System.out.println("label=" + snapshot.label);
            System.out.println("port=" + snapshot.port);
        });

        reader.start();
        reader.join();
    }
}
~~~

Compile/run JDK 17+:

~~~bash
javac --release 17 VolatilePublicationDemo.java
java VolatilePublicationDemo
~~~

**Exact stdout:**

~~~text
label=READY
port=8080
~~~

In this example:
- The writer creates and completes `Config` before assigning volatile `published`.
- `writer.join()` also creates an HB path to main, making the example **deterministic**; the reader is started after join so it is guaranteed to see the object. **This is not a benchmark isolating only the volatile mechanism** because there is also HB from join/start.
- Volatile on `published` provides a clear publication mechanism if extended to a design where writer/reader run concurrently and read the proper volatile variable.
- `Config` has final fields; in this code both the final guarantee and safe publication are maintained.

Do not delete `join()` and write a reader with a single read and assume it is guaranteed to see non-null immediately. A reader may run before the writer publishes. **Ordering/visibility** does not automatically mean **scheduling/arrival time**.

## 11. Safe publication with a synchronized monitor

Writer:

~~~java
synchronized (lock) {
    shared = new Settings("ap-southeast", 300);
}
~~~

Reader:

~~~java
Settings copy;
synchronized (lock) {
    copy = shared;
}
~~~

These are snippets, requiring `lock` and `shared` in a valid class. If the writer **unlocks the monitor** after the assignment and the reader **subsequently locks that same monitor**, the JMM establishes a synchronizes-with edge. Writes in the constructor before publication can be observed via HB at the reader.

Two common mistakes:
- Writer locks object A, reader locks object B: **not the same monitor**, so the desired edge is not obtained.
- Writer uses synchronized, reader reads `shared` directly outside the lock: the reader may **not** receive the visibility guarantee from the monitor protocol.

### synchronized is not just mutual exclusion

It provides **atomicity** for the critical section via mutual exclusion and **visibility/ordering** when locking/unlocking the matching monitor pair. However, it does not automatically solve an object escaping from a constructor or returning raw aliases to a mutable array after the lock is released.

## 12. Safe publication via class initialization

The initialization-on-demand holder is a simple idiom:

~~~java
final class Service {
    final int id;

    private Service(int id) {
        this.id = id;
    }

    private static final class Holder {
        static final Service INSTANCE = new Service(42);
    }

    static Service instance() {
        return Holder.INSTANCE;
    }
}
~~~

The JVM coordinates class initialization according to JLS §12.4.2, so the instance created in the static initializer and published through `Holder` has proper initialization visibility for threads using the class. There is no need to write `volatile` or `synchronized` in the accessor every time.

### Eager static final

~~~java
final class Constants {
    static final Service INSTANCE = new Service(42);
}
~~~

Creating an object from a static field initializer also benefits from the corresponding class initialization mechanism. One must distinguish a **static final reference** from a **JLS constant variable**: `Service` is a reference type, so it cannot become a compile-time constant variable like `static final int ANSWER=42`.

### Enum singleton

~~~java
enum GlobalService {
    INSTANCE;
}
~~~

Enum initialization is also managed by the JVM and is often useful for creating a safe singleton with built-in serialization semantics. However, if an enum singleton holds mutable fields, operations on those fields must still be thread-safe.

## 13. Standalone runnable Java 17+ example: holder singleton and thread join

Create file **`HolderPublicationDemo.java`**:

~~~java
public class HolderPublicationDemo {
    static final class Service {
        final int id;
        final String name;

        private Service() {
            id = 42;
            name = "single";
        }
    }

    static final class Holder {
        static final Service INSTANCE = new Service();
    }

    public static void main(String[] args)
            throws InterruptedException {
        Service[] observed = new Service[4];
        Thread[] workers = new Thread[observed.length];

        for (int i = 0; i < observed.length; i++) {
            final int index = i;
            workers[i] = new Thread(
                    () -> observed[index] = Holder.INSTANCE);
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }

        boolean same = true;
        for (Service service : observed) {
            same &= service == observed[0];
        }

        System.out.println("same=" + same);
        System.out.println("id=" + observed[0].id);
        System.out.println("name=" + observed[0].name);
    }
}
~~~

Commands:

~~~bash
javac --release 17 HolderPublicationDemo.java
java HolderPublicationDemo
~~~

**Exact stdout:**

~~~text
same=true
id=42
name=single
~~~

Threads may touch `Holder.INSTANCE` simultaneously, but the JVM performs the appropriate class initialization **only once** per class loader/class instance. `join()` makes main wait and provides HB to read the elements of the `observed` array. This code does not crudely measure synchronization cost; it illustrates a way of publication **without manually writing double-checked locking**.

## 14. Double-checked locking: why is volatile needed?

**Double-checked locking (DCL)** aims to reduce synchronized overhead after the singleton has been created:

~~~java
final class LazyService {
    private static volatile LazyService instance;

    static LazyService get() {
        LazyService result = instance;
        if (result == null) {
            synchronized (LazyService.class) {
                result = instance;
                if (result == null) {
                    result = new LazyService();
                    instance = result;
                }
            }
        }
        return result;
    }
}
~~~

This is a class snippet. An appropriate constructor needs to be declared.

**Why are there two checks?**
- The outer check avoids entering the monitor when the instance already exists.
- The inner check ensures that after acquiring the lock, if another thread has already created the singleton, it is not created a second time.

**Why is `volatile` important?**
- A thread can observe the reference outside the synchronized block.
- Without volatile or an equivalent publication mechanism, the reference read/write outside the lock has a data race and does not guarantee proper visibility for all constructor writes.
- Volatile publication creates ordering/visibility: readers seeing the reference after publication will see the prior initialized state.
- A `final` field in the singleton **does not automatically make ordinary fields or the singleton's mutable graph safely published**, and does not turn non-volatile DCL into a recommended idiom.

### Reading to avoid a race between two volatile reads

Use a local `result` to read volatile once per check level; also suitable when the value is changed in other patterns. For a singleton initialized only once, the main goal is correct publication and avoiding unnecessary reads.

### DCL is not needed everywhere

If the singleton does not need lazy creation, use a static final field. If lazy is desired with less complexity, use an **initialization-on-demand holder**. DCL is useful when lazy initialization with lifecycle/constructor args or special logic is needed, but it increases review cost.

## 15. Standalone runnable Java 17+ example: correct DCL singleton

Create file **`DclSingletonDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class DclSingletonDemo {
    static final class Service {
        private static final AtomicInteger CREATED =
                new AtomicInteger();
        private static volatile Service instance;

        final int value;
        final String label;

        private Service() {
            value = 42;
            label = "ready";
            CREATED.incrementAndGet();
        }

        static Service get() {
            Service result = instance;
            if (result == null) {
                synchronized (Service.class) {
                    result = instance;
                    if (result == null) {
                        result = new Service();
                        instance = result;
                    }
                }
            }
            return result;
        }

        static int creationCount() {
            return CREATED.get();
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Service[] results = new Service[8];
        Thread[] threads = new Thread[results.length];

        for (int i = 0; i < threads.length; i++) {
            final int index = i;
            threads[i] = new Thread(
                    () -> results[index] = Service.get());
            threads[i].start();
        }

        for (Thread thread : threads) {
            thread.join();
        }

        boolean allSame = true;
        for (Service result : results) {
            allSame &= result == results[0];
        }

        System.out.println("same=" + allSame);
        System.out.println("created=" + Service.creationCount());
        System.out.println("value=" + results[0].value);
        System.out.println("label=" + results[0].label);
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 DclSingletonDemo.java
java DclSingletonDemo
~~~

**Exact stdout:**

~~~text
same=true
created=1
value=42
label=ready
~~~

Why it is correct:
- Only one thread can create the instance in the critical section if `result` is still null.
- `volatile instance` provides release/acquire semantics for publication and the lock-free read path.
- Final fields are set before the constructor returns.
- `AtomicInteger` counts one constructor invocation in the valid example, but is **not a necessary condition** for DCL; it only serves for demonstration.
- `join()` allows main to read the `results` elements assigned by the threads.

**Do not remove `volatile` and use the output on one machine as proof that DCL is still correct.** Failure can be rare on specific hardware/tests while the JMM still does not promise correctness.

## 16. Safe handoff via Thread.start and Thread.join

Initializing an object on main and then starting a worker is a valid JMM handoff:

~~~java
final class WorkData {
    int ordinary;
    final int fixed;

    WorkData() {
        ordinary = 17;
        fixed = 42;
    }
}
~~~

In main:

~~~java
WorkData data = new WorkData();
Thread worker = new Thread(() -> {
    System.out.println(data.ordinary);
    System.out.println(data.fixed);
});
worker.start();
worker.join();
~~~

These are **two illustrative snippets**, needing to be wrapped in a class/method, with checked exception `InterruptedException`. Actions before `start()` happen-before actions of the worker. Therefore, in this situation **both ordinary and final fields** are initialized and visible to the worker; no extra volatile is needed just to pass the reference before start.

However, if main mutates `data.ordinary` **after start** concurrently with the worker read, thread-start HB does not automatically order that new write. Appropriate synchronization is needed.

### Thread.join returns results in the opposite direction

Worker writes before termination happen-before main actions after a successful `join()`. This is why multi-thread examples can collect results into different slots and only print from main after joins.

**Both platform threads and virtual threads** (JDK 21+) obey the corresponding Java Memory Model rules; carrier mapping does not change final-field semantics.

## 17. Handoff via BlockingQueue, Future, and concurrent collections

Several Java concurrency APIs specify clear memory consistency effects.

### BlockingQueue

The writer creates and completes an immutable message and then calls `put(message)` into a `BlockingQueue<Message>`. The reader calls `take()` on the same queue to receive the message. Actions prior to placing the object into the queue happen-before actions subsequent to the access/removal of it from the queue in another thread per API memory consistency properties.

~~~text
Producer                        Consumer
  new Message(...)
  fields initialized
        |
  queue.put(message) ----------> queue.take()
                                     |
                               message fields read
~~~

This is a **safe handoff** model, provided the producer does not mutate a shared mutable payload without synchronization after put.

### ConcurrentHashMap

Use `ConcurrentHashMap` to put **fully initialized objects** into the map, and have the reader use corresponding retrieval per the API. The map's memory visibility guarantee does not make an object published in the constructor before init finishes "complete again".

### Future / ExecutorService

Actions prior to task submission happen-before task execution per the `ExecutorService` contract; task actions happen-before **the result retrieved via `Future.get()`** per package/API memory consistency rules.

**Do not confuse** "submitting a task to an executor" with "the task has completed". The reader needs `Future.get()`, join, latch, or an equivalent mechanism to wait for the result and proper ordering.

### AtomicReference

An `AtomicReference<T>` using `set`/`get` provides visibility semantics similar to a volatile reference for the corresponding operation. However, an atomic reference does not turn the entire state of T into immutable or every field access into an atomic transaction.

## 18. Standalone runnable Java 17+ example: safe publication with BlockingQueue

Create file **`QueuePublicationDemo.java`**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class QueuePublicationDemo {
    static final class Payload {
        final String name;
        final int code;

        Payload(String name, int code) {
            this.name = name;
            this.code = code;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        BlockingQueue<Payload> queue =
                new ArrayBlockingQueue<>(1);

        Thread producer = new Thread(() -> {
            Payload payload = new Payload("TASK", 27);
            try {
                queue.put(payload);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        });

        producer.start();

        Payload received = queue.take();
        producer.join();

        System.out.println("name=" + received.name);
        System.out.println("code=" + received.code);
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 QueuePublicationDemo.java
java QueuePublicationDemo
~~~

**Exact stdout when the program completes normally:**

~~~text
name=TASK
code=27
~~~

The constructor finishes before the producer enqueues. The queue ensures safe handoff to the consumer. `producer.join()` only waits for the thread to finish for a clean lifecycle; visibility between put/take is already guaranteed by the API. If the producer is interrupted before put, the example will wait on `take()`; this simple program has no dedicated timeout/cancellation policy, so production code should design a timeout or an appropriate result/error channel.

## 19. final reference does not make mutable data thread-safe

Example:

~~~java
final class Stats {
    final int[] counts = new int[1];

    void increment() {
        counts[0]++;
    }

    int read() {
        return counts[0];
    }
}
~~~

`counts` always references the same array, but `counts[0]++` is a non-atomic read-modify-write. Two threads calling `increment()` simultaneously can lose updates. `final` **does not** guarantee that element reads/writes have new visibility/happens-before after initialization.

This can be fixed with:

~~~java
final class StatsSafe {
    private final java.util.concurrent.atomic.AtomicInteger count =
            new java.util.concurrent.atomic.AtomicInteger();

    void increment() {
        count.incrementAndGet();
    }

    int read() {
        return count.get();
    }
}
~~~

This is a complete class snippet with a fully qualified class name. `AtomicInteger` has thread-safe operations per its contract. The reference field `count` is final so the reference is not reassigned after the constructor, while the **atomic state** of `AtomicInteger` itself is synchronized per the API.

An alternative is `synchronized` on both `increment()` and `read()`; or designing immutable snapshots republished on each update via `volatile`/AtomicReference.

### AtomicReference does not turn multiple field updates into an atomic snapshot

If an object has mutable `name` and `timeout`, writing two fields and letting readers read through an `AtomicReference` does not automatically create atomicity across the two field assignments. It is better to create **a new immutable Config** containing both values and then swap the reference with an atomic/volatile store. The reader grabs **one snapshot** and uses both of its fields.

## 20. Records and immutable classes

JDK 17 supports stable records. Record components correspond to private final fields, providing concise syntax for value aggregates.

~~~java
record Endpoint(String host, int port) { }
~~~

If `host` is an immutable String and `port` is a primitive, this record is an easy-to-use value carrier in an immutable style. However, a record with a `byte[]` component **is not deep immutable**:

~~~java
record Packet(byte[] bytes) { }
~~~

The caller can modify the array passed into the canonical constructor or the array returned by the getter. The record compiler generates a final reference field, **it does not automatically clone** the array.

### Record with defensive copy

~~~java
record Packet(byte[] bytes) {
    Packet {
        bytes = bytes.clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }
}
~~~

This is a **record snippet**, compilable on Java 17+ when placed in a proper file/package. The compact canonical constructor allows normalizing the parameter before automatically assigning the component field; cloning in the accessor prevents returning an alias. For nested mutable graphs, deep copying or immutable elements must be designed.

### Immutability is a design contract

A class with `final int x` whose getters arbitrarily hand out raw references to mutable internal state does not automatically become an immutable class. Safety across multiple threads requires **no observable mutation after construction** or mutations must be synchronized. Java's final-field rules help build **thread-safe immutable objects**, they do not replace API design.

## 21. Mutable singleton and limits of class initialization

A holder singleton creates an object safely once, but if the singleton contains mutable state:

~~~java
final class CounterService {
    static final CounterService INSTANCE =
            new CounterService();

    int count;

    void increment() {
        count++;
    }
}
~~~

`INSTANCE` being safely published **does not** make `count++` atomic or thread-safe. Class initialization only guarantees initialization visibility per the rules, not turning all subsequent method calls into synchronized.

One must combine:
- AtomicInteger/LongAdder for counters depending on workload.
- Synchronized/locks for compound invariants.
- Immutable snapshots via AtomicReference if state has multiple fields needing consistency.
- Appropriate concurrent collections.
- Thread confinement or message passing if shared mutable state is not desired.

**Key takeaway:** *safe initialization + safe publication ≠ automatic safe mutation forever.*

## 22. Constructor escape via Thread.start: why is it dangerous?

Anti-pattern:

~~~java
final class EarlyWorker {
    final int port;

    EarlyWorker() {
        new Thread(() -> System.out.println(port)).start();
        port = 8080;
    }
}
~~~

This is an **illustrative class**; Java source can compile when the blank final is assigned properly. The Runnable captures `this`; start occurs **before** `port=8080`. The thread may read `0` if it runs early or `8080` depending on actual scheduling and memory effects; there is no properly constructed publication guarantee for the final field at the time of start.

**Do not make a demo that automatically prints `0` with `Thread.sleep()` to "prove the JMM"**: schedulers and JITs differ, and timing does not determine memory model legality.

Fix:

~~~java
final class ReadyWorker {
    final int port;

    ReadyWorker(int port) {
        this.port = port;
    }

    Thread startWorker() {
        Thread t = new Thread(() ->
                System.out.println(port));
        t.start();
        return t;
    }
}
~~~

The caller only calls `startWorker()` **after `new ReadyWorker(...)` completes**, avoiding escape in the constructor. If there is superclass/subclass inheritance, the arrangement of constructors/callbacks still needs to be checked. A static factory can be used to ensure the lifecycle.

### Is calling start at the end of the constructor enough?

This should not be done. Even if `start()` is on the last line of source, the constructor has not actually completed; the object can escape before constructor exit/freeze. With subclassing, a superclass constructor can start a thread when subclass fields have not yet been assigned. The simplest solution is **not to publish `this` from the constructor**, instead separating start/register out after factory/construction.

## 23. Wrong publication: cannot be fixed with sleep, yield, or misplaced join

A wrong pattern:

~~~java
static Example shared;

static void writer() {
    shared = new Example();
}

static void reader() {
    while (shared == null) {
        Thread.yield();
    }
    use(shared);
}
~~~

These are snippets requiring appropriate `Example`/`use`. `Thread.yield()` is only a scheduling hint; it **does not** form a volatile/monitor HB and does not promise a thread will see the reference change. The compiler/JMM may not provide progress/visibility as the code expects.

Similarly:
- `Thread.sleep(10)` does not create a proper memory barrier that you are entitled to use to publish fields.
- Many successful runs do not prove there is no data race.
- `Thread.join()` only has a memory effect when **the waiting thread actually detects termination** per the contract; one cannot sprinkle a meaningless `join` into another execution path and assume all writes from all threads are visible.
- Writing to the console sometimes changes timing/internal synchronization making races harder to reproduce, but **does not fix correctness**.
- `synchronized` on the writer while the reader does not synchronize on the same lock is not a safe publication protocol.

**Solution:** create a clear HB path between writes before publication and reads after publication, or properly use final-field semantics of an immutable constructed object combined with an appropriate publication design.

## 24. JMM stress testing: do not use normal run counts as proof

A concurrency bug may only appear when:
- The JIT optimizes long enough, reordering/hoisting reads.
- A CPU architecture allows different memory behavior than a dev machine.
- Thread scheduling changes under high load.
- Class initialization/safepoint/GC timings differ.
- Testing across multiple CPU cores and compiler tiers.
- Publication occurs right when the constructor has not completed.

A test trying to "measure how many times a field equals 0" with a short loop can return 0 failures **even when the code has a data race**. That is not proof of safety.

### jcstress

OpenJDK **jcstress** is a framework for researching observable outcomes in concurrent programs via memory-model litmus tests. It executes actors concurrently over many iterations, collects outcomes, and classifies expected/acceptable/interesting/forbidden states as defined by the test.

**What it helps with:** increasing the chance of detecting rare outcomes, testing multiple JVM modes/hardware, learning about visibility/ordering.

**What it does not promise:** that a valid race will always occur on your machine; not observing outcome X does not prove X is forbidden by the JMM; stress testing does not replace happens-before/JLS reasoning.

Project pages: https://openjdk.org/projects/code-tools/jcstress/ and https://github.com/openjdk/jcstress.

### Do not use JMH instead of jcstress

**JMH** measures microbenchmark performance and controls JIT warmup/forks; **jcstress** tests concurrency outcomes. They serve different questions. Using JMH to check JMM correctness or jcstress to compare p99 REST latency are both misuses.

## 25. Production diagnosis: look at ownership, publication, and API contract

Tools such as JFR, thread dumps, `jcmd`, or profilers are useful for seeing locks, thread states, CPU, GC, and class loading, but they **do not by themselves prove** a program is free of data races. A JMM bug must be evaluated through code review and the happens-before graph.

An investigation checklist:
1. Find fields that can be read/written by multiple threads. Distinguish immutable snapshots and mutable shared state.
2. Find every place an object reference is stored into shared static/instance fields, registries, maps, or queues.
3. Determine when the constructor completes relative to places where the reference is published.
4. Check callbacks/listeners/overridable methods that cause `this` to escape early.
5. For the reader, identify the acquire operation corresponding to the writer's release.
6. Draw the concrete happens-before chain; do not stop at "used synchronized somewhere".
7. For a final reference containing an array/collection, check defensive copies and post-publication mutations.
8. Check DCL `volatile`, lock monitor identity, and class-init holder.
9. When suspecting a race, design a jcstress test to see what outcomes the JMM allows.
10. Fix ownership/synchronization, then check regressions on both Java 17 and the actual deployment JDK.

### Observability and limitations

`jcmd PID Thread.print` or JFR can help see thread stacks and lock contention; a race on an ordinary field does not necessarily have lock contention or an obvious event. Thread dumps are usually only point-in-time snapshots; racy code does not necessarily show up in the snapshot.

Diagnostic commands take PIDs from real processes; do not expose sensitive production data externally without authorization.

## 26. Common misconceptions

| Misconception | Reality |
| --- | --- |
| "Constructor finishes means other threads definitely see every field." | Only when there is safe publication/HB or special guarantees like final-field semantics. |
| "final and volatile are the same." | final provides initialization safety/immutability of the field; volatile provides ordering/visibility for accesses to the variable. |
| "final ref makes the array/list immutable." | Only the reference field cannot be reassigned; the referent and elements can be mutable. |
| "final-field rules publish the reference to all threads." | No; ordinary racy publication still has visibility/liveness issues on the reference. |
| "Constructor freeze creates a general HB for all fields." | §17.5 has specific conditions and dereference semantics; not equivalent to volatile publish. |
| "If using ConcurrentHashMap, publishing mid-constructor is fine." | It can safely publish a **partial object**; must construct completely before put. |
| "Running new Thread in constructor is a convenient and always safe way to start." | The Runnable capturing `this` may observe an uninitialized object. |
| "Assigning final field at the end of constructor is enough even if this escaped earlier." | Proper construction has been violated; cannot rely on the special guarantee. |
| "static final singleton does not need synchronization on any method." | Safe initialization does not make subsequent mutations automatically thread-safe. |
| "volatile ref makes object fields volatile." | Only publication before the write is guaranteed; post-publication mutable writes need synchronization. |
| "Once a thread sees a volatile ref, all reachable objects are immutable." | Visibility of pre-publication writes differs from immutability of graphs with aliases/mutations. |
| "Non-volatile DCL is still correct because the constructor has final fields." | Non-volatile DCL lacks proper safe publication for ordinary state and the reader path. |
| "Running on x86 without reproducing the bug means JMM guarantees it." | One execution does not prove portable correctness. |
| "Thread.sleep creates a memory barrier." | Sleep is not a safe-publication protocol. |
| "volatile write means compound action is atomic." | Volatile on a single field does not turn multi-step read-modify-write into a transaction. |
| "Record is always deep immutable." | A record component can be a mutable array/collection object. |
| "Immutable list always deep-copies elements." | CopyOf/unmodifiable wrappers can hold mutable element references. |
| "jcstress finding no error means the program is definitely safe." | Stress outcomes do not replace JLS reasoning. |
| "GC/JIT automatically fixes races missing synchronization." | The JVM preserves memory-model semantics; it does not supply guarantees the program lacks. |

## 27. Self-check questions with answers

**1. When does final-field freeze occur?**

According to JLS 17.5.1, a freeze action occurs when the constructor that writes the final field ends. One must understand constructor delegation details and not let the reference escape early.

**2. An object is properly constructed and published via an ordinary racy field; a reader sees the reference. How is the field `final int x=42` guaranteed?**

The properly constructed final-field guarantee allows the reader to see the correct initialized value of x. However, publication via an ordinary field still does not provide full HB for arbitrary non-final fields and does not guarantee the reader promptly sees the reference.

**3. Why does the ordinary field `int y=17` of the same object not receive the same guarantee as final x when published racily?**

Because special final-field semantics do not automatically become a general synchronization HB edge for all ordinary fields.

**4. If `this` is put into a registry before assigning final x, is the reader guaranteed x=42?**

No. The object was not properly constructed before publication; partial state may be observed.

**5. Does `final byte[] payload` make `payload[0]++` atomic?**

No. Final applies to the reference field; array elements are mutable and increments are not atomic.

**6. Cloning in the constructor but having the getter return the raw internal byte[] — is it immutable?**

No. The caller can mutate the internal array through the getter. Defensive copies are needed at both appropriate boundaries.

**7. The writer stores a fully initialized object into a volatile field; the reader reads that field. What is guaranteed?**

Writes before the volatile publication HB reads after the volatile acquire, so readers see the initial state per HB. Subsequent mutable updates still need synchronization.

**8. Writer locks monitor A, reader locks B — is there safe publication?**

Not from two different locks alone. There must be a matching synchronization protocol.

**9. Does a holder singleton need synchronized on every accessor call?**

No; class initialization provides initialization safety for `static final INSTANCE`. Mutable state inside the instance must still be made thread-safe separately.

**10. Why does DCL need volatile?**

The fast path reads the reference outside the monitor; volatile provides ordering/visibility for publication and avoids a data race on the reference.

**11. If main creates data and then calls Thread.start(worker), is the worker guaranteed to see writes before start?**

Yes; start happens-before actions in the worker.

**12. If the worker writes output and then main calls join(worker), does main see the writes?**

Yes after join succeeds, per termination/join HB.

**13. If volatile `current` changes to a new reference, can a reader reading current twice see two different snapshots?**

Yes, if the publisher replaces the reference between the two reads; capture a local snapshot if coherence on one object version is needed.

**14. Does a ConcurrentHashMap containing a fully initialized object need final on every field for proper visibility?**

Not as a condition of publication; the map API provides memory consistency for insertion/retrieval. However, final is still useful for immutable design and fields mutated afterward need synchronization.

**15. Why does sleep not prove there is no data race?**

Sleep changes timing but does not automatically create the necessary volatile/monitor/thread handoff edge.

**16. Can JMH prove the JMM forbids an outcome?**

No. JMH measures performance; JLS reasoning, code review, and tools like jcstress for stress outcomes are needed.

**17. Does a final field in an object whose constructor threw an exception have the same meaning as a valid published object?**

Do not design publication from failed constructors. The JLS describes freeze details even for abrupt exit, but an object that did not build complete invariants should not be handed to application threads for use.

**18. Is a record with an int[] component whose accessor returns the original array deep immutable?**

No. The record's final field only fixes the reference, it does not prevent mutations of the array.

**19. Is a final `AtomicInteger` a fixed counter value?**

No. The reference to AtomicInteger is fixed, but the internal atomic value can be updated thread-safely.

**20. What should be asked first if a thread sometimes reads config timeout=0?**

Check the constructor, publication timing, the volatile/lock/queue/handoff path between writer and reader, and whether timeout is assigned before or after publish. Do not conclude "compiler reorder bug" when HB is missing.

## 28. Mind map

~~~text
                CREATE OBJECT O
                       |
              DEFAULT FIELD VALUES
                       |
                  CONSTRUCTOR
                       |
            +----------+----------+
            |                     |
        NO this ESCAPE       this ESCAPES EARLY
            |                     |
       fields initialized      possible partial view
            |                     |
      CONSTRUCTOR EXIT         final guarantee may fail
            |
      FINAL FIELD FREEZE
            |
            v
          PUBLICATION
            |
       +----+---------------------------+
       |                                |
  RACY ORDINARY FIELD              SAFE PUBLICATION
       |                                |
  final-field special              volatile/lock/start/
  guarantee only                   class init/queue/Future
       |                                |
  non-final not fully              constructor writes
  ordered; ref liveness            happen-before reads
  not guaranteed                        |
       +----------------+---------------+
                        |
                   AFTER PUBLISH
                        |
                IS OBJECT MUTABLE?
                     /      \
                    NO       YES
                    |         |
             final + deep   locks/atomic/
             immutability   volatile/snapshot/
                    |       ownership discipline
                    +---------+
                              |
                    THREAD-SAFE DESIGN
                              |
                  Verify with JLS HB graph
                  and targeted jcstress tests
~~~

**Conclusion:** `final` fields have special **initialization safety** thanks to **constructor freeze**, provided the object is **properly constructed** and the reference does not escape early. However, a final field **does not automatically create full safe publication for all non-final fields**, nor does it make a mutable referent graph deep immutable. For reliable concurrent code, **complete construction before publication**, establish a **clear happens-before path** using appropriate volatile/locks/class initialization/Thread.start/concurrent handoff, and protect **all subsequent mutations** with a dedicated ownership/synchronization protocol.

## Official References

- [Java Language Specification SE 17 — §17.4 Memory Model](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4).
- [Java Language Specification SE 17 — §17.4.5 Happens-before Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5).
- [Java Language Specification SE 17 — §17.5 final Field Semantics](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5).
- [Java Language Specification SE 17 — §17.5.1 Semantics of final Fields](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5.1).
- [Java Language Specification SE 17 — §12.4.2 Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2).
- [Java Language Specification SE 17 — §15.29 Constant Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.29).
- [Java SE 17 API — Thread.start, join, and interrupt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html).
- [Java SE 17 API — BlockingQueue memory consistency](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html).
- [Java SE 17 API — ExecutorService memory consistency](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html).
- [Java SE 17 API — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html).
- [Java SE 17 API — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).
- [OpenJDK jcstress — Java Concurrency Stress tests](https://openjdk.org/projects/code-tools/jcstress/).
- [OpenJDK jcstress source repository](https://github.com/openjdk/jcstress).
