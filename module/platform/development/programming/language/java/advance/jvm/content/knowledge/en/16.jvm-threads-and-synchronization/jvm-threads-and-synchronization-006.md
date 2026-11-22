# Java Memory Model Is Different from Heap, Stack, and Physical Memory Diagrams

## 1. Short Answer: JMM Is a Set of Rules About Behavior, Not a Diagram of Where Data Is Placed

The **Java Memory Model (JMM)** is the semantic model in the **Java Language Specification (JLS), Chapter 17**, that defines **which observable outcomes are legal** when threads concurrently read, write, and synchronize data. It describes **read/write behavior, allowed observation orderings, happens-before relationships, data races, volatile, monitors, and final fields**.

In contrast, the **JVM heap/stack** diagram in the **Java Virtual Machine Specification (JVMS) §2.5** describes the **runtime data areas** of the virtual machine: the shared heap, each thread's JVM stack, frames/local variables/operand stacks, the method area, the runtime constant pool, the PC register, and native method stacks.

Meanwhile, **physical memory** is how the CPU, OS, virtual machine, and HotSpot implement the program: registers, CPU caches, RAM, virtual memory, memory pages, allocation buffers, GC barriers, compiler optimizations, etc.

The three layers answer **different questions**:

| Layer | Main Question | Specification Source |
| --- | --- | --- |
| **JMM** | Which value is thread B allowed to see from thread A? When is a write safely published? Is there a data race? | JLS `17.4–`17.5 |
| **JVM runtime data areas** | What are the roles of the heap, JVM stacks, frames, local-variable slots, and method area? | JVMS `2.5–`2.6 |
| **Implementation/hardware** | Which bits are in a CPU register/cache/RAM at a given moment? What instructions/barriers does the JIT use? How is an object laid out? | HotSpot, OS, and CPU architecture |

**Do not infer the Java Memory Model solely from the picture "local variables on the stack, objects on the heap."** A thread can have its own local variable **pointing to a shared object**. Moreover, even if a Java field resides in the heap according to the language model, the JIT can keep the value in a register, eliminate the allocation via scalar replacement, or reorder instructions in ways that still comply with the JMM.

### 1.1. Three-Tier Diagram

```text
JAVA PROGRAM                    JVM MODEL                    IMPLEMENTATION
--------------                  ----------------            ----------------------
Thread A, Thread B              Heap/shared fields          CPU registers
read/write shared state         Per-thread frames           L1/L2/L3 caches
synchronized, volatile          JVM stacks                  DRAM / virtual memory
final fields, Thread.start      Class metadata              HotSpot JIT, GC, barriers
        |                              |                            |
        v                              v                            v
        JMM: what observations        JVMS: what data areas         CPU/OS: how is it
        are allowed?                  exist?                        implemented?
        |                                                           |
        +--------------- SEMANTIC CONSTRAINTS ----------------------+
```

This diagram **does not equate** the JMM with a pre-existing block of RAM/caches. An implementation is free to optimize as long as the program performs **a legal execution under the JMM**.

## 2. Heap and Stack in JVMS: Accurate at the Architectural Level, Insufficient for Concurrency

According to **JVMS §2.5.3**, the JVM has a **heap shared among all JVM threads** for allocating class instances and arrays. Heap storage is managed by a garbage collector; the specification does not mandate a specific memory management technique.

According to **JVMS `2.5.2**, **each JVM thread has its own JVM stack**, used to store frames for method invocations. According to `2.6, each frame contains a **local variables array**, an **operand stack**, and related information.

```text
              THREAD A                      THREAD B
        +--------------------+        +--------------------+
        | JVM stack A        |        | JVM stack B        |
        | frame: local ref p |        | frame: local ref q |
        +---------+----------+        +----------+---------+
                  |                              |
                  +---------------+--------------+
                                  v
                        SHARED JVM HEAP
                        +-------------------+
                        | Payload object    |
                        | value = 42        |
                        +-------------------+
```

Variables `p` and `q` are **two different local variables**, each belonging to its own method frame. However, both can hold a **reference to the same object** on the heap. If two threads concurrently read/write `Payload.value`, **conflicting accesses** on a shared field can occur.

### 2.1. A Private Stack Does Not Make the Referenced Object Private

Conceptual example:

```java
class Box {
    int value;
}

Box shared = new Box();
Thread t1 = new Thread(() -> shared.value++);
Thread t2 = new Thread(() -> shared.value++);
```

This is a **snippet**, without full creation/start/join. Even though the parameter/local references in the two threads are not the same local variable, both can access the **`value` field of the same `Box`**. `value++` is not an atomic increment operation under the JMM; without appropriate synchronization, there will be a data race and updates can be lost.

**What matters:** whether threads are accessing the **same shared variable**, not which frame holds the reference.

### 2.2. Local Variables Are Not JMM Shared Variables

**JLS §17.4.1** explicitly states that local variables, formal method parameters, and exception handler parameters are **never shared between threads** and are unaffected by the shared-variable memory model.

However, the **value of a local variable can be a reference to a shared object**. It is **instance fields, static fields, and array elements** that constitute the shared variables studied in JLS §17.4.

Therefore, the statement "every local variable is thread-safe" is **overly broad and wrong**: a private local reference can lead to unsafe shared mutable state.

### 2.3. The JVM Stack Does Not Necessarily Match the Physical Stack Frame You Imagine

The JVMS describes runtime concepts such as frames/local-variable slots. On actual HotSpot, the JIT can:

- Place certain values in CPU registers.
- Inline methods so that source frame boundaries no longer exist physically as assumed.
- Eliminate allocations or scalar-replace object fields.
- Reuse/rearrange slots according to optimizations.
- Store additional metadata to support safepoints, deoptimization, and GC roots.

**Do not tie every Java local to a fixed physical stack address** or assume every Java object must be materialized in the heap at all times.

### 2.4. A Shared Heap Does Not Mean Every Heap Object Is Actually Shared

A Java object may be accessed only by thread A, even though the Java heap is architecturally a shared area. The compiler can prove that an object does not escape and optimize it, but **this is a conclusion from reference flow**, not because the heap turns into private memory.

## 3. Why Is the Java Memory Model Needed?

Because a multithreaded program needs to know **which results thread B is allowed to see** when thread A writes data.

Example:

```java
class Message {
    int data;
    boolean ready;
}
```

Suppose A does:

```java
message.data = 42;
message.ready = true;
```

and B does:

```java
if (message.ready) {
    System.out.println(message.data);
}
```

The snippets above **have no synchronization**. Even though A writes `data` before `ready` in source program order, if there is a data race, **you cannot conclude that when B sees `ready == true`, it is guaranteed to read `data == 42`**. The compiler, runtime, or processor is allowed to perform transformations compliant with the JMM that single-threaded intuition does not anticipate.

### 3.1. What the JMM Describes Is Legal Executions

According to **JLS §17.4**, the memory model examines an execution trace and checks which write action a read action can observe under the validity rules.

It does not provide a diagram like:

```text
volatile write == copy bytes immediately to RAM
volatile read  == fetch bytes directly from RAM
```

The two equations above are **not the definition of the JMM**. The compiler/hardware has many ways to maintain visibility/ordering without performing "RAM flushes" as in the simplified description.

### 3.2. The Issues Lie in Visibility, Ordering, and Atomicity

- **Visibility:** under what conditions a thread is guaranteed to observe writes from another thread.
- **Ordering:** how actions can be seen in an ordering relationship.
- **Atomicity:** how an operation is treated as a single indivisible step with respect to interleavings between threads.

These three properties are related, but **not equivalent**. `volatile` provides visibility/ordering guarantees for the appropriate variable; it **does not make `counter++` atomic**.

## 4. Key Conceptual Components of the JMM

The JMM uses the following concepts:

1. **Actions:** reads/writes and synchronization actions of threads.
2. **Program order:** the order of actions of **a single thread** according to language execution.
3. **Synchronization order:** a total order over all synchronization actions in an execution, consistent with program order for each thread.
4. **Synchronizes-with:** synchronization edges defined by the JLS, e.g., volatile write → subsequent read of the same volatile variable, unlock → subsequent lock of the same monitor.
5. **Happens-before (HB):** a partial order built from program order, synchronizes-with, and transitivity.
6. **Conflicting accesses:** two accesses to the **same shared variable**, where at least one access is a write.
7. **Data race:** two conflicting accesses that are not ordered by happens-before.
8. **Well-formed execution/causality rules:** rules ensuring the values observed by reads are valid, limiting inferences from racy programs.

**Not every event in the JMM is a single CPU instruction.** They are **semantic actions**; an implementation may realize them using multiple instructions or optimize them into no corresponding instruction if observable behavior remains valid.

### 4.1. What Specifically Are Shared Variables?

According to §17.4.1:

- **Instance fields**.
- **Static fields**.
- **Array elements**.

Do not exclude array elements from data-race analysis just because they do not have a field name like `count`. Two threads concurrently writing `array[0]` can race; writing to **different array elements** involves different shared variables, though higher-level concurrency issues may still need to be considered.

### 4.2. Local Primitives Differ from Object References

```java
int local = 7;
Box box = sharedBox;
local++;
box.value++;
```

This is a **snippet**; `sharedBox` needs to be defined.

- `local`: a local primitive in the frame, not directly shared under the JMM.
- `box`: a private local reference; the reference value may be a JVM-implemented address/handle.
- `box.value`: a field of an object that may be shared; if updated by multiple threads without synchronization, it can race.

Do not conclude "`box` is local, so `box.value` is local."

## 5. Program Order Is Not a Promise About Physical Instruction Order

A thread according to source code:

```java
a = 1;
b = 2;
```

has a **program order** between the two actions under the JMM when they appear in the corresponding execution. However, the compiler and CPU can reorder or eliminate operations when doing so does not change the allowed behaviors of the program.

In a multithreaded program lacking synchronization, another thread **has no right to infer** from source order alone that seeing `b == 2` means it must see `a == 1`.

### 5.1. As-If-Serial Is Not Enough for Shared-Variable Races

On a single thread, optimizations generally must preserve intra-thread semantics. However, other threads can observe seemingly surprising orderings if there are no HB edges.

JLS §17.4 includes examples of legal **reordering** even when it appears contrary to source code.

### 5.2. CPU Caches Are Not Grounds to "Prove" a Read Is Valid

CPUs have different cache coherence protocols, store buffers, and memory-ordering rules. However, the correct way to understand a Java program must rely on the **JMM**, not on guessing whether thread A's `L1 cache` has flushed or not.

Two CPUs running the same Java program can have different hardware memory ordering; **the JVM/JIT must implement Java's synchronization semantics on both**.

### 5.3. Wall-Clock Order Differs from Happens-Before

A write that "actually happened earlier" according to an observer's clock **does not automatically create an HB edge** to another thread's read. HB is a **relationship within an execution under the JMM** constructed from program order/synchronization rules.

Conversely, the JMM allows an implementation to perform certain physical reorderings as long as the result remains consistent with legal executions; **HB does not mean every memory instruction must physically complete on the same absolute timeline**.

## 6. Happens-Before: The Most Important Reasoning Tool

Write `hb(A, B)` when action A **happens-before** action B.

JLS §17.4.5 builds HB from:

- **Program order:** an earlier action in the same thread happens-before a later action.
- **Synchronizes-with:** a source synchronization action happens-before a target synchronization action.
- **Transitivity:** if `hb(A,B)` and `hb(B,C)`, then `hb(A,C)`.

Some important rules:

| Source | Target | Meaning |
| --- | --- | --- |
| Unlock monitor `M` | Subsequent lock of monitor `M` in synchronization order | Publishes writes through the same monitor |
| Write volatile `v` | Subsequent read of volatile `v` in synchronization order | Publishes prior writes to the thread reading the flag/reference |
| `Thread.start()` | Actions of the started thread | Publishes state prepared before starting |
| Actions in thread `T` | Another thread successfully returning from `T.join()` | The joining thread sees effects before `T` terminated |
| Default initialization of an object | Subsequent actions per JLS rules | Fields have default values before appropriate usage |
| `Thread.interrupt()` | Another thread detecting the interruption per rules | Has a corresponding synchronization edge |

APIs in `java.util.concurrent` also define their own **memory consistency effects**. Read the API documentation to see why enqueue/dequeue, `CountDownLatch`, `Future.get`, or atomic operations establish appropriate observation relationships.

### 6.1. Transitive Linear Example

```text
Thread A:                   Thread B:
  payload.value = 84          local = published  [volatile read]
  published = payload         print(local.value)
      [volatile write]

Program order: A.value write -> A.volatile write
Synchronizes-with: A.volatile write -> B.volatile read
Program order: B.volatile read -> B.value read

=> A.value write happens-before B.value read
   (when B reads the reference published via volatile)
```

This is a **semantic proof**, not a diagram of "copying 84 from L1 to DRAM."

### 6.2. `happens-before` Does Not Mean Every Read Will See the "Latest Value by Wall Clock"

An HB edge constrains the writes that a read can observe. However, to deduce the **specific value** a read sees, you must consider **other writes to the same variable**, the relevant ordering, and the full semantics of the program.

Do not say "having HB means immediately reading every latest value across the system" — the JMM does not provide a global memory snapshot by physical timestamp.

## 7. `volatile`: Publication and Ordering, Not "Forcing Direct Writes to RAM"

A field declared as:

```java
private static volatile boolean done;
```

is a **volatile variable**. Under the JMM, a **volatile write** and a **volatile read** are **synchronization actions**. A write to `done` **synchronizes-with** subsequent reads of the same volatile variable in synchronization order.

### 7.1. Stop Flag Example

```java
class Flag {
    volatile boolean done;
}

static void worker(Flag flag) {
    while (!flag.done) {
        Thread.onSpinWait();
    }
}
```

This is an **illustrative code snippet**, not a standalone program. `Thread.onSpinWait()` is a **performance hint**; it does not replace `volatile` or create a special HB edge.

If `done` is **non-volatile** and there is no other synchronization, the JVM may optimize the read, or the program may never observe changes from another thread. Do not use `Thread.sleep`/`onSpinWait` as a substitute for `volatile`.

### 7.2. Safe Publication via Volatile Reference

```java
class Data {
    int value;
}

static volatile Data published;

static void producer() {
    Data data = new Data();
    data.value = 84;
    published = data;
}
```

When a consumer observes the **published reference** through a volatile read, writes preceding the volatile write have an HB path to subsequent reads. Thus, the consumer can rely on the state safely initialized in that order.

### 7.3. A Volatile Reference Does Not Make the Entire Object Graph Synchronized

After publication:

```java
Data snapshot = published;
snapshot.value++;
```

If multiple threads concurrently increment `value` without synchronization, **the `value` field can still race**. `volatile Data published` makes accesses to the reference volatile; **it does not turn every field of `Data` into volatile/atomic**.

### 7.4. Volatile Increment Is Not Atomic

```java
volatile int counter;

void increment() {
    counter++;
}
```

This is an **illustrative snippet**; `counter++` consists of a read, a computation, and a write. Two threads can read the same value and both write back the result, causing a **lost update**, even though each individual access has volatile semantics.

Use `AtomicInteger.incrementAndGet()` or `synchronized` when an atomic increment is needed.

### 7.5. Volatile Does Not Necessarily Always Emit a Full Hardware Fence

The JIT can implement volatile using instructions/ordering/barriers appropriate for each CPU architecture. There is no guarantee that **every volatile read emits a specific memory fence instruction** or **forces the CPU cache to flush completely to main memory**.

**The JMM guarantees observable effects**, not a specific instruction-set implementation.

## 8. `synchronized`: Both Mutual Exclusion and Publication

```java
private static final Object LOCK = new Object();
private static int count;

static void increment() {
    synchronized (LOCK) {
        count++;
    }
}
```

If all threads modifying `count` lock **the same monitor `LOCK`**, the read-modify-write operation is protected by mutual exclusion.

### 8.1. Unlock → Lock HB

Thread A:

```java
synchronized (LOCK) {
    count = 42;
}
```

Thread B:

```java
synchronized (LOCK) {
    System.out.println(count);
}
```

When B acquires the same monitor after A releases it, the JMM provides the appropriate synchronization for B to see the preceding writes. However, **do not look only at these two snippets and declare B's output is always 42** if B can run before A; the order of monitor acquisition matters.

### 8.2. Two Different Locks Do Not Create the Same Relationship

```java
synchronized (new Object()) {
    count++;
}
```

If each thread creates a new lock, they **do not share a monitor**. That synchronized block does not protect `count` from other threads doing the same thing. The JIT can even eliminate the lock if it proves the monitor does not escape.

**Monitor identity** is what governs synchronization, not identical-looking source code.

### 8.3. Who Does a Synchronized Method Lock?

- A `synchronized` instance method locks **`this`**.
- A `static synchronized` method locks the **`Class` object** representing the class.
- A `synchronized(lock)` block locks **the exact object reference returned by the expression**.

Do not interpret running `synchronized` as "locking the entire heap" or "freezing RAM."

### 8.4. Synchronized and Hardware Instructions

HotSpot may implement uncontended/contended lock paths using different mechanisms depending on the version. The JIT may perform lock elision optimizations when safe. The JMM only requires **valid monitor and memory ordering behavior**; it does not mandate exact bytes in the object header or a fixed instruction.

## 9. A Standalone Java 17+ Example: Volatile Publication and Synchronized Counter

Create the file **`MemoryModelDemo.java`**:

```java
public final class MemoryModelDemo {
    private static final class Payload {
        final int id;
        int value;

        Payload(int id, int value) {
            this.id = id;
            this.value = value;
        }
    }

    private static volatile Payload published;
    private static final Object LOCK = new Object();
    private static int count;

    private static void increment() {
        synchronized (LOCK) {
            count++;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Thread producer = new Thread(() -> {
            Payload localReference = new Payload(42, 84);
            published = localReference;
        });

        Thread consumer = new Thread(() -> {
            Payload localReference;
            do {
                localReference = published;
            } while (localReference == null);

            System.out.println("published id=" + localReference.id);
            System.out.println("published value=" + localReference.value);
        });

        consumer.start();
        producer.start();
        producer.join();
        consumer.join();

        Thread first = new Thread(() -> {
            for (int i = 0; i < 20_000; i++) {
                increment();
            }
        });

        Thread second = new Thread(() -> {
            for (int i = 0; i < 20_000; i++) {
                increment();
            }
        });

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("synchronized count=" + count);
        System.out.println("expected count=40000");
    }
}
```

### 9.1. Running the Program

```bash
javac --release 17 MemoryModelDemo.java
java MemoryModelDemo
```

**Exact stdout when the program completes normally:**

```text
published id=42
published value=84
synchronized count=40000
expected count=40000
```

The example was **compiled with `javac --release 17`** and run on HotSpot in three modes: default, `-Xint`, and `-Xmixed`. All three produced this same logical result.

### 9.2. Why Are `published id` and `published value` Stable?

The producer creates `Payload(42,84)` and **writes the volatile reference `published` after the constructor completes**.

The consumer reads `published` **via a volatile read** until it receives a non-null reference. From the volatile write to the subsequent volatile read there is a **synchronizes-with edge**; by transitivity of HB, the fields initialized by the producer before publication can be safely read by the consumer.

**It is not because the object "resides on the heap so both threads automatically see the same state instantaneously."** A field on the shared heap without publication may lack the corresponding HB guarantee.

### 9.3. Why Does Using a Local Variable in Each Thread Still Result in a Shared Object?

The producer has `localReference` in its own frame. The consumer also has a **local variable with the same name** in its own frame. They are not the same local variable. The producer puts the **reference to the Payload object** into `published`, and the consumer reads that reference.

It is the referenced object that is shared; **the JMM analyzes the volatile field and object fields**, not an operation of "moving a local variable from stack A to stack B."

### 9.4. Why Is the Counter Always 40,000?

Two threads execute 20,000 calls to `increment()`, and each call locks **the same `LOCK`**. Thanks to mutual exclusion, increments do not suffer lost updates. `join()` in `main` establishes a completion/happens-before relationship for `main` to read `count` after the workers finish.

`count` does not need to be declared volatile because all updates are protected by the monitor and `main` only reads after successful joins. If the code were extended with a third thread reading `count` while workers are running, an appropriate synchronization mechanism would need to be established for the reader.

### 9.5. Why Is a Spin-Loop Not a Recommended Production Pattern?

The demo's consumer waits for a volatile reference using a continuous read loop. It helps isolate the volatile example, but it can **waste CPU** and lacks timeout/cancellation. In production, prefer `CountDownLatch`, `BlockingQueue`, `Future`, `CompletableFuture`, or appropriate APIs to coordinate thread lifecycles.

### 9.6. Why Do `-Xint` and `-Xmixed` Produce the Same Logic?

The JMM belongs to **Java semantics**; the JIT can arrange instructions/barriers depending on the architecture, but it must not cause a properly synchronized program to observe invalid results. The execution mode can change timing, not break HB guarantees.

## 10. Data Race: A Property of an Execution, Not a "Faulty CPU Cache"

A **data race** under JLS §17.4.5 occurs when there are two **conflicting accesses** to the same shared variable that are not ordered by happens-before. Example:

```java
static int total;

static void add() {
    total++;
}
```

If two threads call `add()` concurrently without synchronization, the accesses can race. Each `total++` consists of a read, an addition, and a write, so the final number can be **smaller** than the expected number of increments.

### 10.1. You Cannot Prove Safety by "Testing 100 Times and Getting the Right Result"

Thread scheduling and optimizer decisions are not required to produce lost updates on every run. A program with a race is still a program lacking JMM constraints, even if a test machine often produces the desired output.

### 10.2. A Data Race in Java Is Not Like Unbounded "Undefined Behavior" in C/C++

The Java Memory Model **still places constraints** on legal executions of racy programs (read-from legality and causality constraints). You should not say "a data race lets the JVM do anything, including inventing arbitrary values" as an oversimplification borrowed from another language.

However, **racy behavior can be very surprising** and is unsuitable for building software correctness.

### 10.3. "Data-Race-Free ⇒ Sequential Consistency" Under Appropriate Conditions

JLS §17.4 states that a **correctly synchronized program**—meaning all of its sequentially consistent executions are free of data races—will have behaviors that appear **sequentially consistent (SC)**. This is the **DRF–SC guarantee** of the JMM.

The intuition of sequential consistency: an execution can be understood as a total order of actions consistent with each thread's program order, where reads observe the appropriate writes in that order.

**Caution:** "DRF–SC" **does not mean** every action is actually executed physically instruction-by-instruction according to a global clock. It is a **guarantee about observable behaviors**.

## 11. Reordering Litmus Test: Why Can Both Reads Equal 0?

Consider two shared ints initially equal to 0:

```java
int x = 0;
int y = 0;
```

Two threads execute the operations:

```text
Thread A               Thread B
--------               --------
x = 1;                 y = 1;
r1 = y;                r2 = x;
```

If `x`/`y` are shared non-volatile fields and there is no synchronization establishing an appropriate ordering, some executions of the program can yield **`r1 == 0` and `r2 == 0`**, even though each thread's source code writes before reading.

### 11.1. Do Not Infer "Both Writes Ran Before Both Reads" from the Two-Column Layout

Program order only gives:

```text
A: write x -> read y
B: write y -> read x
```

There are no HB edges between threads to force each read to see the other thread's write. A legal execution can correspond to the reads observing the initial values. This is the *store buffering* example commonly used to discuss memory models.

### 11.2. Does Changing x and y to Volatile Change the Allowed Outcomes?

With volatile reads/writes belonging to the synchronization order and corresponding semantics, **`r1 == 0 && r2 == 0` is excluded from the legal outcomes in this litmus test**: for both reads to see zero in a global order would require ordering the writes/reads in contradiction with program order and synchronization order.

**Do not generalize that volatile makes every concurrent program completely sequential.** This conclusion applies to a specific operation pattern; compound actions, multiple variables, and other objects still require analysis.

### 11.3. Why Not Write a Unit Test "Run 1 Million Loops and Expect to See 0,0"?

Legal outcomes do not mean they must be observed in a finite number of runs. The CPU, VM, JIT, and OS scheduling can make that outcome rare or absent during testing. To study concurrency litmus tests, use frameworks like **JCStress** instead of writing your own loops and making false assertions.

## 12. `final` Fields: Initialization Safety Is Not "Everything Is Immutable"

JLS §17.5 defines special **final field semantics**. When an object is **properly constructed**—without allowing `this` to escape the constructor early—final fields have special initialization guarantees that allow other threads to see the final field values set in the constructor even if the publication lacks ordinary synchronization.

Example:

```java
final class Configuration {
    final int port;
    final String name;

    Configuration(int port, String name) {
        this.port = port;
        this.name = name;
    }
}
```

If the constructor does not leak `this`, the final fields `port` and `name` benefit from initialization safety guarantees under the JLS. However, there are important limitations.

### 12.1. `final` Does Not Turn a Reference to a Mutable Object into an Immutable Deep Graph

```java
final class Holder {
    final int[] values = new int[1];
}
```

`values` is a final reference: the reference cannot be reassigned after normal construction. However, **`values[0]` is still mutable**.

If multiple threads concurrently read/write `values[0]` without synchronization, the array element can have a **data race**. Final field semantics do not turn post-constructor mutations into safely synchronized operations.

### 12.2. Constructor Escape Breaks Safety Assumptions

```java
final class BadPublication {
    final int value;

    BadPublication(java.util.List<BadPublication> registry) {
        registry.add(this); // publish this before the constructor completes
        value = 42;
    }
}
```

This is an **illustrative anti-pattern**. If another thread accesses the object via `registry` while the constructor is still running, final field initialization safety guarantees may not apply as they would when an object is properly constructed before publication.

### 12.3. `final` Does Not Replace a Publication Protocol in All Cases

Final fields have their own guarantees, but for ordinary mutable state, thread safety and post-construction visibility should still rely on **safe publication** or an appropriate synchronization mechanism.

## 13. Safe Publication: How to Pass an Object from Thread A to Thread B?

**Safe publication** means having a JMM basis for thread B to observe the state prepared by A, rather than merely "happening to see a non-null reference."

Common mechanisms:

- Writing the reference via a **volatile field** and reading it via a volatile read.
- Writing/reading state inside **`synchronized`** on the same monitor.
- Publishing before `Thread.start()` in accordance with start's happens-before.
- Waiting for completion via `Thread.join()` or `Future.get()` mechanisms that have memory-consistency effects.
- Using `BlockingQueue`/concurrent collections/atomic APIs according to each library's contract.
- Using safe class initialization when applied properly.

### 13.1. Be Careful with Ordinary Static Fields

```java
static Config config;

static void init() {
    config = new Config();
}
```

This is a **snippet**; `Config` is not defined. If another thread reads `config` without synchronization, **you cannot automatically assert** that all normal fields of `Config` have been safely published.

If initialization occurs during **class initialization** coordinated by the JVM under JLS §12.4.2, the situation is different: the JVM provides the appropriate class-initialization synchronization/happens-before. However, a static field **dynamically assigned later** is not inherently safe just because it has the `static` keyword.

### 13.2. Publication and Mutation Are Two Separate Phases

An object being safely published at time T does not mean all writes after T are also safely published. If thread A continues modifying normal fields after publication while thread B reads them, further synchronization is needed.

### 13.3. Concurrent Containers Support HB According to API Contracts

`java.util.concurrent` containers such as `BlockingQueue`, `ConcurrentHashMap`, and concurrency utilities have memory-consistency guarantees. Depending on the API, actions prior to enqueuing/putting an object may happen-before actions after another thread successfully obtains access to the object in the specified manner.

Read the **API docs**; do not infer guarantees solely from the word "Concurrent" in the name.

## 14. `Thread.start()` and `Thread.join()`: HB Edges Without a Volatile Field

### 14.1. Start

```java
class State {
    int value;
}

State state = new State();
state.value = 123;
Thread worker = new Thread(() -> System.out.println(state.value));
worker.start();
```

This is a **snippet**, not a standalone program. Actions before `worker.start()` in the thread calling start happen-before actions in the new thread. Therefore, if there are no other concurrent writes to `state.value`, the worker thread has a JMM basis to read the prepared value.

### 14.2. Join

```java
Thread worker = new Thread(() -> result[0] = 42);
worker.start();
worker.join();
System.out.println(result[0]);
```

This is a snippet that needs `result` and `InterruptedException` handling. When the thread calling join **returns successfully and the worker has completed**, the worker's effects are published to the joining thread under the JMM.

Note: reading the array element **while the worker is writing without another HB edge** is a different question. `join()` does not retroactively make races between threads valid.

### 14.3. Sleep Does Not Replace Start/Join/Synchronization

```java
Thread.sleep(500);
System.out.println(sharedValue);
```

`Thread.sleep` does not create an HB edge to another thread's write merely because 500 ms have elapsed. A timing-based polling approach without volatile/locks/concurrent APIs has no JMM guarantee.

## 15. Atomicity: Variable Type and Operation Type Matter More Than "Being in RAM"

```java
volatile int count;
count++;
```

Individual volatile reads and writes have appropriate atomicity/ordering, but the **read → add → write sequence is not atomic**.

`AtomicInteger` provides operations such as:

```java
java.util.concurrent.atomic.AtomicInteger counter =
        new java.util.concurrent.atomic.AtomicInteger();
int updated = counter.incrementAndGet();
```

`AtomicInteger.incrementAndGet` guarantees an atomic read-modify-write per the API, suitable for an independent counter.

### 15.1. Non-Volatile `long` and `double` Under JLS §17.7

JLS §17.7 historically allows **non-volatile `long` and `double`** accesses to be treated as two 32-bit operations in some implementations; therefore, **non-volatile 64-bit access should not be treated as an absolute language guarantee across all JVMs**.

In many modern HotSpot/JDKs, handling 64-bit aligned values may be atomic in practice due to implementation/architecture. However, **that does not change the nature of the JLS guarantee**. Volatile `long` and `double` reads/writes are atomic according to the specification.

### 15.2. Do Not Equate Atomicity with Visibility

An atomic read/write of a field is not enough to guarantee that another thread sees the same value at the desired time if appropriate ordering/visibility is lacking.

### 15.3. Same Data, Multiple Fields

If an invariant involving `balance` and `version` must change atomically together, simply using two volatile fields does not turn the **pair of updates** into an atomic transaction. You need the same lock, a published immutable snapshot, or an appropriate design mechanism.

## 16. The JMM Does Not Allow Speculating About CPU Cache Lines Per Thread

Some simplified articles show:

```text
Thread A -> CPU core A -> L1 cache A
Thread B -> CPU core B -> L1 cache B
volatile -> flush RAM
```

This is a **hardware learning diagram**, not the definition of the JMM. It ignores:

- Two Java threads can **run interleaved on the same core**, or migrate across cores.
- CPUs have multiple cache levels, coherence protocols, store buffers, and their own memory ordering rules.
- The OS can preempt threads; the JVM can execute compiled/interpreted code differently.
- An object can reside in the heap, registers, or be scalar-replaced in an optimized path.
- Volatile/barriers can be implemented differently across x86-64, AArch64, and other platforms.

**The right approach:** rely on the JMM to determine legal outcomes; if optimizing performance at the CPU level, analyze the **implementation** after correctness is established.

### 16.1. "Main Memory" in the JMM Does Not Mean Every Operation Hits Real DRAM

Textbook models may talk about a "thread's working memory" and "main memory" to build intuition. However, the current JLS §17.4 defines the JMM through **actions/executions/happens-before**; it does not promise that every variable has a "master copy" fixed in DRAM and that volatile forces a full flush.

### 16.2. Cache Coherence Does Not Replace Happens-Before

Even when CPU cache coherence guarantees certain properties for single memory locations, **ordering across multiple locations** and compiler transformations remain issues. A Java program with a data race does not become valid just because it runs on a "CPU with coherent caches."

## 17. False Sharing: Related to Hardware Performance, Not the Same Concept as Data Race

**False sharing** occurs when threads modify different variables/fields that happen to sit close together on the same cache line, causing unwanted cache-line traffic.

Conceptual example:

```text
Cache line:
+-------------------+-------------------+
| A's counter       | B's counter       |
+-------------------+-------------------+
       A writes             B writes
   (two different variables, possibly no data race)
       |
       v
  Cache coherence traffic affects throughput
```

It is possible to have **false sharing without a data race** because two threads modify **different variables**. Conversely, a data race can exist even if two fields sit on two different cache lines.

- **JMM correctness:** are there conflicting accesses lacking HB?
- **Hardware performance:** do memory locations on the same cache line cause coherence contention?

**Do not fix a correctness issue by adding cache-line padding**. Padding can help throughput in some situations; it does not create HB edges.

## 18. Reordering and Compiler Optimizations on HotSpot

A JIT compiler can:

- Hoist loads out of a loop if there is no synchronization forcing it to see updates from other threads.
- Inline methods and scalar-replace objects.
- Remove redundant writes/reads if observable behavior allows.
- Coalesce/canonicalize computations.
- Insert barriers to implement volatile/locks/atomic APIs per platform.
- Deoptimize/recompile when an optimization assumption no longer holds.

Example:

```java
boolean done;

void waitUntilDone() {
    while (!done) {
        // no volatile, no synchronization
    }
}
```

If another thread writes `done = true` without synchronization, this loop **has no guarantee of terminating**. You should not conclude "probably after a few milliseconds cache coherence will make it see true."

### 18.1. JIT Optimization Must Not Turn a Correctly Synchronized Program into an Incorrect One

If volatile, monitors, or concurrent APIs are used properly, the implementation must preserve the ordering/visibility constraints mandated by the JMM. C2 can eliminate a lock only when it proves that elimination does not change legal behavior—it must not "drop a lock because it looks expensive on CPU."

### 18.2. Interpreter-Only Still Complies with the JMM

Running:

```bash
java -Xint MemoryModelDemo
java -Xmixed MemoryModelDemo
```

Both execution modes must maintain JMM semantics. Running `-Xint` **is not a fix for a data race**: a racy program still lacks guarantees, even if the interpreter happens to reorder less than an optimizing compiler.

### 18.3. Bytecode Does Not Fix CPU Memory Barriers

In a class file, a `synchronized` block has monitor bytecodes, and a volatile access has field access instructions and metadata flags, but JIT/hardware lowering can vary greatly by architecture.

`javap -c` shows bytecode operations, **not a dump of actual memory instructions** after C2 optimization.

## 19. GC Reachability and the JMM Are Two Separate Issues

GC solves the problem: **which objects are still reachable and when can heap storage be reclaimed?** The JMM solves the problem: **which read/write observations between threads are legal?**

Example:

```java
static Object shared;

static void publish() {
    shared = new Object();
}
```

This is an illustrative snippet. Assigning an object to a static field can keep it reachable; however, if another thread reads `shared` without synchronization, **it does not mean publishing the state complies with the JMM** just because the object "lives on the heap."

### 19.1. A Reachable Object Is Not Safely Published

A static list holding a reference does not automatically prove that reads/writes to the object's mutable fields are thread-safe. Reachability and happens-before must be analyzed separately.

### 19.2. GC Is Not a Visibility Mechanism for Business State

A GC pause/safepoint can affect VM execution, but it **does not replace** synchronized/volatile/concurrent APIs under the JMM. Do not design concurrency on the assumption that "GC will synchronize all caches so the state will be right."

### 19.3. Cleaner and `Reference.reachabilityFence` Do Not Replace Locks

Reachability-related APIs support the lifecycle of objects/native resources; they do not inherently provide atomicity for shared mutable counters or transaction state.

## 20. Classic Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| "The JMM is the picture with the heap in the middle and a stack per thread." | That picture describes runtime data areas; the JMM defines legal inter-thread observations. |
| "Local variables are always thread-safe, so every local object is safe." | A local reference can point to a shared mutable object. |
| "Because a field is on the heap, every thread sees the new value immediately." | A shared heap does not automatically create happens-before. |
| "Volatile always flushes all CPU caches to RAM." | The JMM only specifies synchronization/visibility/ordering semantics. |
| "Volatile `counter++` is atomic." | Volatile does not automatically make a compound read-modify-write atomic. |
| "`Thread.sleep` guarantees seeing another thread's write." | Sleep does not create an HB edge with an ordinary write. |
| "Using `synchronized` with two different objects still protects the same static counter." | Synchronization must use the same monitor or an appropriate API. |
| "If code runs correctly 100 times, there is no data race." | A race can be very rare or not manifest during testing. |
| "Every Java program is always sequentially consistent." | DRF-SC requires proper synchronization; racy programs have other behaviors. |
| "A Java data race allows any arbitrary value." | The JMM still has well-formed execution/causality constraints. |
| "A final reference makes the entire mutable graph immutable." | A final field does not prevent mutations of the referenced object. |
| "Seeing a non-null reference means the object is safely published." | An HB path or proper reliance on final-field semantics is required. |
| "Every volatile read requires a full CPU fence instruction." | Machine implementation depends on the architecture/optimizer. |
| "CPU cache coherence automatically replaces the JMM." | Coherence does not replace Java's synchronization semantics. |
| "False sharing is a data race." | Cache-line contention can occur on different variables without a data race. |
| "Heap objects are always materialized in DRAM." | The JIT can scalar-replace or keep data in registers when legal. |
| "`-Xint` allows omitting volatile because the interpreter optimizes less." | The JMM does not change across interpreter/JIT modes. |
| "A class static field is always safely published even when assigned dynamically on any thread." | Class initialization has specific rules; unsynchronized dynamic assignment can still race. |
| "`Thread.join` only waits and has no memory effect." | A successful join has HB semantics with the actions of the terminated thread. |
| "GC acts as a memory barrier for business threads." | GC scheduling does not replace explicit concurrency guarantees. |
| "`long`/`double` are usually atomic on x64, so the Java Specification guarantees all non-volatile 64-bit accesses." | JLS §17.7 permits non-atomic treatment for non-volatile `long`/`double`. |

## 21. Design Scenarios Applying the JMM

### Scenario A — A Request Builds a DTO and Passes It to a Worker Thread

If the entire DTO is constructed before `thread.start()` and there are no improper concurrent mutations, start HB can publish the state to the worker. If using an executor pool, rely on the **memory consistency effects of the executor/queue APIs**; do not assume a new worker thread is created for each request.

### Scenario B — A Service Initializes a Singleton Once

You can use the **class initialization idiom** or safe publication via volatile/locks. Do not write lazy initialization with a normal shared reference and assume "there are only two threads so it's probably fine."

### Scenario C — Shared Counter

If atomic increment is needed, use `AtomicInteger` or a monitor. If contention throughput is high and only a statistical sum with suitable semantics is needed, `LongAdder` is worth considering; however, read the consistency behavior of `sum()` under concurrent updates.

### Scenario D — Producer Sends Messages to Consumer

Use `BlockingQueue` to get ordering/coordination and memory effects per the API instead of writing a non-volatile field + sleep-loop.

### Scenario E — Immutable Value Object

Use final fields and a constructor that does not leak `this`, and avoid exposing mutable internal arrays directly. If the object contains mutable fields, safe publication and mutation discipline are still required as needed.

### Scenario F — Debugging on a Different CPU

Code that "works on x86" but lacks HB can expose bugs on another architecture or another HotSpot/JDK. Fix correctness using proper memory-model rules, **not by adding sleeps or relying on cache layout**.

## 22. Tools and Ways to Verify Concurrency

### 22.1. `javap`

```bash
javap -c -p MemoryModelDemo
```

Used to read bytecode and method structure, but it **does not tell you the exact CPU instructions/barriers** that HotSpot uses after JIT.

### 22.2. Java Flight Recorder and Profilers

JFR has events for thread activity, monitor contention, and certain runtime events depending on configuration. It helps answer "are threads waiting on monitors a lot?" but does not prove a program is data-race-free.

### 22.3. Thread Dumps

Thread dumps show states at a point in time such as `RUNNABLE`/`BLOCKED`/`WAITING`, and stacks/locks depending on the tool. **A thread dump is not proof of JMM safety**: data races are properties of accesses/orderings, not just how many threads are blocked.

### 22.4. JCStress

**JCStress** is an OpenJDK toolset for testing outcomes of concurrency litmus tests under many interleavings/JIT/hardware conditions.

- Use JCStress to study which outcomes the JMM allows or forbids.
- A legal outcome might not appear even after many runs.
- JCStress does not replace a **logical proof** based on JLS §17.4.
- Avoid turning an "unobserved" outcome into a guarantee.

### 22.5. JMH

**JMH** focuses on microbenchmark performance, suitable for measuring the overhead of volatile/locks/atomics in controlled scenarios. **JCStress is for correctness/stress**, **JMH is for performance benchmarking**: the two tools answer two different questions.

### 22.6. Static Analyzers

IDE/static analysis tools can find signs of concurrency bugs: non-volatile flags, unsafe publication, lock misuse. However, the absence of warnings **does not prove the entire program is data-race-free**.

## 23. Self-Check Exercises with Answers

**Question 1.** Are the JMM and the JVM heap the same concept?

**Answer:** No. The JMM defines allowed observations between threads; the JVM heap is the runtime data area used for class instances/arrays under the JVMS.

**Question 2.** Can a local variable `Box b` in thread A reference the same `Box` as local `Box c` in thread B?

**Answer:** Yes. The local variables are private, but the references can point to a shared object.

**Question 3.** Why is `ready = true` after `data = 42` not sufficient publication if both are normal fields?

**Answer:** There is no HB edge between the producer's writes and the consumer's reads; the JMM may allow observations lacking the desired ordering/visibility.

**Question 4.** What relationship does a volatile write → volatile read of the same variable create?

**Answer:** There is a synchronizes-with edge when the read is subsequent in synchronization order, thereby contributing to happens-before.

**Question 5.** Is `volatile int counter; counter++;` atomic?

**Answer:** No. `++` is a compound read-modify-write, which can lose updates with multiple threads.

**Question 6.** Does `Thread.start()` have an HB effect?

**Answer:** Yes. Actions occurring before start in the calling thread happen-before actions of the started thread under JLS rules.

**Question 7.** What effect does a successful `Thread.join()` have?

**Answer:** Actions of the terminated thread happen-before subsequent actions of the thread observing the successful termination/join.

**Question 8.** Does synchronized source code using two different lock objects guarantee an atomic shared counter?

**Answer:** No. Mutual exclusion requires threads to coordinate through the same monitor or an equivalent synchronization mechanism.

**Question 9.** Does `Thread.sleep` create HB with another thread writing a normal field?

**Answer:** Not merely by sleeping for a duration.

**Question 10.** What is the difference between false sharing and a data race?

**Answer:** False sharing is cache-line contention affecting performance; a data race is conflicting shared-variable accesses not ordered by HB.

**Question 11.** Why does `final int[] values` not make the array immutable?

**Answer:** `final` applies to the reference field; the array elements remain mutable.

**Question 12.** Where is the danger in publishing `this` from a constructor?

**Answer:** Other threads can observe the object before initialization completes; final-field initialization safety may not apply as with proper construction.

**Question 13.** Does an object remaining reachable from a static field mean all normal fields are safely published?

**Answer:** No. Reachability is different from HB/safe publication.

**Question 14.** Does `-Xint` change JMM semantics?

**Answer:** No. Both the interpreter and JIT must obey legal Java executions.

**Question 15.** Does `volatile` force a direct-to-DRAM write on every platform?

**Answer:** No. The JMM specifies ordering/visibility semantics; the JVM chooses the appropriate implementation.

**Question 16.** Do non-volatile `long`/`double` reads/writes have portable 64-bit atomicity under the JLS?

**Answer:** It cannot be guaranteed for every VM. JLS §17.7 allows non-atomic treatment; volatile `long`/`double` have an atomicity guarantee.

**Question 17.** If code has no data races under JMM conditions, what is guaranteed about its behaviors?

**Answer:** Properly synchronized/data-race-free programs have a **sequential consistency guarantee** regarding observable behaviors under the JMM.

**Question 18.** Does seeing the right value 1,000 times prove the code is data-race-free?

**Answer:** No. Outcomes depend on scheduling, JIT, and hardware; HB and synchronization analysis is required.

**Question 19.** How do two threads reading/writing `array[0]` differ from each thread only writing `array[0]` and `array[1]` respectively?

**Answer:** Accessing the same element can be conflicting; different elements are different variables, though algorithmic-level data sharing must still be considered.

**Question 20.** How do JCStress and JMH differ?

**Answer:** JCStress investigates concurrency correctness/allowed outcomes; JMH measures performance using microbenchmark methodology.

**Question 21.** Does "happens-before" mean action A must run before B in physical wall-clock time under every optimization?

**Answer:** No. It is a semantic/outcome-constraining relationship; an implementation can physically reorder as long as it does not produce an illegal execution.

**Question 22.** Why is `synchronized count` in the demo 40,000 without needing `count` to be volatile?

**Answer:** Both worker threads use the same monitor for increments; `main` only reads after successful joins establish the appropriate HB.

## 24. Checklist When Analyzing Real-World Multithreading Bugs

1. Identify **shared variables**: instance fields, static fields, array elements.
2. For each variable, list the threads that can read/write it.
3. Find **conflicting accesses**, checking whether at least one is a write.
4. Draw the **happens-before graph** based on start/join, volatile, monitors, and concurrent APIs.
5. Do not use "local variable on the stack" as proof that data is not shared.
6. Distinguish object **ownership** from physical object location.
7. If multiple threads increment together, check the atomicity of **compound operations**.
8. If publishing an object, check whether the constructor leaks `this`, final field semantics, and the publication path.
9. For immutable objects, check whether internal mutable arrays/lists expose references.
10. For `synchronized`, ensure threads lock **the same object monitor**.
11. For volatile, remember only the volatile variable has ordering semantics; post-publication mutations must be handled separately.
12. Do not use sleep/spin timing as a way to create HB.
13. Do not equate a GC safepoint or heap scan with business synchronization.
14. Do not blame CPU caches before determining legal JMM behaviors.
15. Run concurrency litmus tests with JCStress when needed, but still analyze properly under the JLS.
16. Use JMH if asking about the performance of volatile/locks; do not use it to prove the absence of races.
17. When upgrading the JDK/changing architecture, retest while keeping logic **independent of compiler timing**.
18. Read the authoritative sources **JLS §17.4/§17.5** and **JVMS §2.5** instead of relying solely on heap/stack diagrams.

### Conclusion

```text
JVM DIAGRAM:               JAVA MEMORY MODEL:
  Thread A stack             Actions: reads/writes/sync
  Thread B stack             Program order
  Shared heap                Synchronization order
  Frames/locals              Synchronizes-with
                             Happens-before
          |                        |
          +-----------+------------+
                      |
          Correct Java program behavior
                      |
          Runtime implemented on CPU:
          registers, caches, virtual memory,
          HotSpot JIT, barriers, GC...

A shared heap DOES NOT automatically guarantee safe publication.
A private stack DOES NOT make the referenced object private.
Volatile/synchronized ARE NOT defined by "flushing RAM".
```

**Key takeaway:** **The Java Memory Model is not a heap–stack map or a CPU cache model.** The JMM specifies **which reads/writes threads are allowed to observe**, while JVM runtime areas describe where data is stored at an abstract level, and hardware/JIT decide how it is executed. When evaluating the correctness of multithreaded code, **prove it using happens-before, atomicity, and safe publication**, rather than reasoning from where variables are placed or when "caches flush."

### Authoritative and In-Depth References

- [JLS 17.4 — Memory Model, Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4): actions, shared variables, program order, synchronization order, happens-before, and data races.
- [JLS 17.5 — final Field Semantics, Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5): initialization safety, freeze action, and not publishing `this` before the constructor completes.
- [JLS 17.7 — Non-Atomic Treatment of double and long, Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.7): non-volatile 64-bit access and volatile atomicity.
- [JVMS 2.5 — Run-Time Data Areas, Java SE 17](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5): PC, JVM stacks, heap, method area, and native method stacks.
- [JVMS 2.6 — Frames, Java SE 17](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6): local variables, operand stack, frames.
- [JLS 12.4.2 — Detailed Initialization Procedure, Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2): class initialization synchronization.
- [java.util.concurrent package specification, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html): memory consistency effects of concurrent utilities.
- [AtomicInteger API, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic operations.
- [OpenJDK JCStress](https://openjdk.org/projects/code-tools/jcstress/): testing allowed outcomes of concurrency litmus tests.
- [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/): performance microbenchmarking in Java.
