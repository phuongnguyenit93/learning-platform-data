# Thread-Private Memory and Shared Memory in the JVM Specification

## 1. The Big Picture

The Java Virtual Machine Specification (JVMS) defines several **run-time data areas**. Some areas exist for the entire JVM and are used by all threads, while others are created separately for each Java thread. Distinguishing them accurately helps explain why two threads have independent local variables yet can still modify the same object; why deep recursion is usually related to the stack; and why `OutOfMemoryError` does not necessarily mean the Java heap is full.

**According to JVMS §2.5:**

| Area | Scope | Role |
| --- | --- | --- |
| **`pc` register** | **Per thread** | Stores the address of the current JVM instruction when executing a non-native Java method |
| **JVM stack** | **Per thread** | Holds frames corresponding to active method invocations |
| **Native method stack** | **Typically per thread if used by the implementation** | Supports native methods and VM components that require conventional native stacks |
| **Heap** | **Shared across all JVM threads** | Allocates class instances and arrays, managed by GC |
| **Method area** | **Shared across all JVM threads** | Per-class structures, field/method information, code, run-time constant pools |
| **Run-time constant pool** | **One pool per class/interface**, allocated in the shared method area | Constants and symbolic references for linking |
| **Frame** | **Per method invocation within a thread** | Local-variable array, operand stack, reference to the run-time constant pool |

It is necessary to distinguish the **logical scope** in the JVMS from the **physical location in RAM**. A JVM implementation, JIT compiler, and garbage collector are free to choose different layouts/techniques as long as they preserve the specified behavior. For example, HotSpot Metaspace is an implementation technique for class metadata, **not the name of a mandatory area in the JVMS**.

### Relationship Diagram

~~~text
                         ONE JVM
+---------------------------------------------------------+
|                                                         |
| THREAD A                              THREAD B           |
| +--------------------+                +----------------+ |
| | pc A               |                | pc B           | |
| | JVM stack A        |                | JVM stack B    | |
| |   frame run()      |                |   frame run()  | |
| |   - locals         |                |   - locals     | |
| |   - operand stack  |                |   - operand    | |
| |   - pool reference |                |     stack      | |
| |   frame helper()   |                |   - pool ref   | |
| | native stack (*)   |                | native stack(*)| |
| +--------------------+                +----------------+ |
|                  |                        |             |
|                  v                        v             |
| +-----------------------------------------------------+ |
| | HEAP: objects, arrays                              | |
| |   shared Counter object, int[] results, ...        | |
| +-----------------------------------------------------+ |
| +-----------------------------------------------------+ |
| | METHOD AREA: per-class structures, method code     | |
| |   constant pool of Class X                         | |
| |   constant pool of Class Y                         | |
| +-----------------------------------------------------+ |
+---------------------------------------------------------+

(*) Only if the implementation uses native method stacks.
~~~

In the diagram, two different frames can reference the same pool because they execute methods belonging to the same runtime class; that **does not merge two operand stacks or local arrays into one**.

## 2. pc Register: Per-Thread Control State

According to **JVMS §2.5.1**, each JVM thread has a **logical pc register**. When the thread executes a non-native Java method, the pc holds the address of the JVM instruction currently being executed; when executing a native method, the value of the pc in the JVMS model is **undefined**. Two threads executing the same method can be at two different bytecode offsets. The pc is **not** a source line and does not necessarily match the CPU instruction pointer; `javap -c` and `LineNumberTable` provide related information in the **class file**, not an API to read the exact pc of an arbitrary thread.

## 3. JVM Stack: Per-Thread Chain of Frames

According to **JVMS §2.5.2**, each JVM thread has a **JVM stack** containing the frames of active method invocations. If thread A calls `main → calculate → add`, three logical frames reside on JVM stack A. Thread B has its own stack and frames, even though it might also call `add`.

~~~text
Thread A                      Thread B
pc A                          pc B
JVM stack A                   JVM stack B
  ├── frame add                  └── frame run
  ├── frame calculate
  └── frame main

Shared heap: references in both stacks can point to the same object.
~~~

**The JVM stack is not the operand stack.** The JVM stack holds multiple frames; each frame in turn contains its own operand stack. The JVMS does not require all frames to have a fixed native RAM layout, and an implementation may apply JIT/deoptimization or other representations while preserving the exact semantics. Excessively deep recursion can cause `StackOverflowError`; insufficient resources to allocate/expand the stack can cause `OutOfMemoryError`. Neither by itself proves that the Java heap is full.

## 4. Frame: Locals, Operand Stack, and Reference to the Pool

According to **JVMS §2.6**, a frame has a **local variables array**, an **operand stack**, and a reference to the **run-time constant pool** for dynamic linking. Each invocation keeps its own locals; a local holding a reference can point to an object on the **shared heap**.

| Method | Local slot 0 | Subsequent slots |
| --- | --- | --- |
| `static int add(int a,int b)` | `a` | `b`, then possibly local result |
| `int add(int a,int b)` | `this` | `a`, `b` |
| `static long sample(long x)` | first part of `x` | `x` occupies two slots in total |

`iload` loads a local value onto the operand stack; `iadd` pops two `int` values from the top and pushes the result; `ireturn` returns to the caller. `long`/`double` occupy two local-variable slots or two units of depth on the operand stack. `max_locals` and `max_stack` in the `Code` attribute are parameters of **a single method**, not a limit on the number of frames on the stack. `LocalVariableTable` is optional debug metadata; `StackMapTable` supports bytecode verification rather than being a snapshot of a running stack.

The upcoming deep-dive article on pc/JVM stack will cover **call/return, exception unwinding, recursion, and StackWalker**; the goal of this overview is to identify the **boundary between per-thread memory and shared memory**.

## 5. Native Method Stacks: Typically Per-Thread, Not Necessarily Present on Every JVM

**JVMS §2.5.6** allows an implementation to use conventional native stacks to support native methods (usually written in C/C++) or certain parts of the VM/interpreter. If present, they are **typically allocated per thread**.

However, the specification **does not require every JVM to have native method stacks**. A JVM implementation that does not support native methods and does not rely on conventional native stacks may omit them.

When native stacks are present:

- If a computation requires a larger native stack than permitted, the VM may throw **`StackOverflowError`** according to the rules.
- If a native stack cannot be allocated or expanded under the described conditions, **`OutOfMemoryError`** may be thrown.
- How Java frames and native frames are mapped to native memory is an implementation detail.

Java syntax illustration:

~~~java
public class NativeDeclaration {
    public native int transform(int input);
}
~~~

This is **not a program that can be called successfully** without the corresponding native implementation and library. Do not take an `UnsatisfiedLinkError` caused by unimplemented native code as evidence that the JVM stack is insufficient.

## 6. Heap: Shared Objects/Arrays, While References Can Be Private

According to **JVMS §2.5.3**, the JVM creates the heap at startup. The heap is **shared among all JVM threads** and allocates **class instances and arrays**. The garbage collector automatically manages reclaiming storage when appropriate; Java source has no `free(object)` operation like C.

~~~text
Thread A frame                         Thread B frame
 local[1] = ref ------+       +------ local[0] = ref
                      v       v
                  HEAP OBJECT
                +----------------+
                | Counter        |
                | count=2        |
                +----------------+
~~~

Two reference locals **reside in two separate frames** yet can point to the same Counter object. If Counter has a mutable field, both threads can access that field.

Consider:

~~~java
Counter c = new Counter();
int number = 7;
~~~

If this snippet is inside a method:

- Local `number` holds a **primitive value** of that invocation.
- Local `c` holds a **reference value**, not the entire object itself.
- `new Counter()` creates a **Counter object on the heap** according to the JVM model.
- When the frame exits, losing the local reference **does not mean the object is immediately reclaimed by GC**; there may be other references/roots or runtime liveness.

**Do not infer** that “any object created inside a method resides on the JVM stack” or “an unused object will be reclaimed at the exact moment the method returns”.

### A Shared Heap Does Not Mean Thread-Safe

Example (illustrative snippet inside a class):

~~~java
class UnsafeCounter {
    int count;
    void increment() {
        count++; // read + add + write: not an atomic increment
    }
}
~~~

If multiple threads call `increment` on the **same object** without proper synchronization, lost updates can occur. The shared heap only enables sharing; visibility/ordering/happens-before rules belong to the **Java Memory Model, JLS §17**, and do not arise automatically just because an object is on the heap.

## 7. Method Area: Shared Class Data

According to **JVMS §2.5.4**, the method area:

- Is an area **shared among all JVM threads**, created at VM startup.
- Stores **per-class structures**: the run-time constant pool, field/method data, and the code for methods/constructors, including special initialization methods.
- May be of fixed size or expand/contract; it is not required to be a contiguous memory area.
- Can throw **`OutOfMemoryError`** if memory cannot be made available to satisfy method area allocation needs.

The JVMS states that the method area is **logically part of the heap**, but **does not mandate a physical location** or a management policy for compiled code. This is not a promise that all method-area structures are always bound by HotSpot's `-Xmx` limit.

### Method Area Differs from Metaspace and PermGen

| Name | Conceptual Level |
| --- | --- |
| **Method area** | Abstract area specified by the JVMS |
| **Metaspace** | Modern HotSpot mechanism for managing class metadata, typically using native memory |
| **PermGen** | Historical mechanism of older HotSpot versions, not a mandatory component of the JVMS |
| **Java heap in HotSpot** | Area managing Java objects, typically configured via `-Xms`/`-Xmx` |

Do not conclude that “the JVMS defines Metaspace” or “every JVM has PermGen”. Nor should you assume that the physical location of every `static` field, `Class` object, or string literal is fixed by JVMS `2.5`.

### Static Fields Are Shared by Runtime Class Identity

A `static` field belongs to a **runtime class**, not to a frame or an individual thread. Threads using the **same runtime class identity** share static state.

~~~java
class Registry {
    static int total;
}
~~~

However:

- `Registry.total++` is **not automatically synchronized** in multi-threaded code.
- If two different defining class loaders both define a class named `Registry`, they create **two runtime class identities**, and each class has its own static state.
- “Shared method area” does not mean static fields of all same-named classes across all plugins are merged.

## 8. Run-Time Constant Pool: Per-Class, Not Per-Thread

**JVMS §2.5.5** describes the run-time constant pool as the runtime representation of the `constant_pool` in a class file. The JVM creates one pool **per class/interface** in the method area when that type is created. The pool contains constants and symbolic references (classes, fields, methods, method handles…).

For example, `javap -c -v` may display:

~~~text
  #N = Methodref ... // Example.add:(II)I
 ...
  invokestatic #N     // calls Example.add(int,int)
~~~

`#N` is a **constant-pool index**, not a stack slot, BCI, or heap address. Dynamic linking uses this symbolic reference to resolve the appropriate runtime entity.

Frames of calls to `Example.calculate` on two threads have **different local arrays/operand stacks**, yet both hold a **reference to the run-time constant pool of the runtime class Example**. There is no need to copy the entire constant pool for each invocation.

**Exact scope:**
- JVM-wide: shared method area.
- Per runtime class/interface: each run-time constant pool.
- Per invocation/thread: frame reference to the pool, locals, and operand stack.

## 9. Java 17+ Example: Two Threads with Private Locals and a Shared Object

Create the file **`MemoryScopeDemo.java`**:

~~~java
public class MemoryScopeDemo {
    static final class Counter {
        private int value;

        synchronized void increment() {
            value++;
        }

        synchronized int get() {
            return value;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter shared = new Counter();
        Counter alias = shared;
        int[] results = new int[2];

        Thread first = new Thread(() -> {
            int local = 10;
            results[0] = local + 1;
            shared.increment();
        }, "first");

        Thread second = new Thread(() -> {
            int local = 20;
            results[1] = local + 1;
            shared.increment();
        }, "second");

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("first-local=" + results[0]);
        System.out.println("second-local=" + results[1]);
        System.out.println("shared-count=" + shared.get());
        System.out.println("same-reference=" + (shared == alias));
    }
}
~~~

Compile and run:

~~~bash
javac -g MemoryScopeDemo.java
java MemoryScopeDemo
~~~

**Exact stdout during normal execution, without interruption or resource errors:**

~~~text
first-local=11
second-local=21
shared-count=2
same-reference=true
~~~

### Why Is This Result Meaningful?

1. Each lambda body is an execution on its own thread; `int local` belongs to the corresponding invocation. The two local values 10 and 20 are **not a shared slot**.
2. `results` points to **a single int array object on the heap**. The first worker writes index 0; the second worker writes index 1.
3. `shared` and `alias` both point to **a single Counter object**, which is why `shared == alias` is true.
4. `increment` is `synchronized` so the two updates to `value` do not suffer a lost update; after two calls `shared.get()` returns 2.
5. `join` waits for both threads to finish and, under the Java Memory Model, makes the writes performed by both workers visible to main. Only **main prints the results after join**, so **the order of output lines is deterministic** even though thread scheduling varies.

**What must not be inferred:** `local` is forced to reside at a fixed separate native stack address. The compiler/JIT may keep the value in a register or eliminate physical storage during optimization; the JVM must still preserve the semantics of each invocation.

### Inspecting with `javap`

~~~bash
javap -c -v -p MemoryScopeDemo
javap -c -v -p 'MemoryScopeDemo$Counter'
~~~

In class `Counter`, method `increment` carries `ACC_SYNCHRONIZED`; in the outer class, lambdas may be implemented via `invokedynamic`/synthetic methods. `javap` shows **bytecode and class metadata**, rather than dumping the native memory of each Java thread.

## 10. Recursion: Multiple Frames for the Same Method

If `sumDown(3)` calls `sumDown(2)` and then `sumDown(1)`, each invocation has **its own frame and parameter `n`**, even though they execute the bytecode of the same method. A loop within the same invocation does not create additional frames merely by iterating. There is no need to intentionally trigger infinite recursion to observe `StackOverflowError`; the next article presents detailed code and traces for recursion.

## 11. `ThreadLocal` Is Not a Local Variable in a Frame

`java.lang.ThreadLocal<T>` is an **API** that allows each thread to store its own value associated with the same ThreadLocal key, which can persist across **multiple method invocations** on that thread.

| Concept | Scope |
| --- | --- |
| Method local | One invocation/frame |
| `ThreadLocal` value | One thread for the corresponding key, potentially across multiple calls |
| Instance field | One object, potentially accessed by multiple threads |
| Static field | One runtime class, potentially accessed by multiple threads |
| Constant pool | One runtime class/interface, shared when referenced by frames |

Example **`ThreadLocalSample.java`**:

~~~java
public class ThreadLocalSample {
    static final ThreadLocal<String> CONTEXT = new ThreadLocal<>();

    public static void main(String[] args) {
        CONTEXT.set("request-1");
        System.out.println(CONTEXT.get());
        CONTEXT.remove();
    }
}
~~~

~~~bash
javac ThreadLocalSample.java
java ThreadLocalSample
~~~

**Stdout:**

~~~text
request-1
~~~

`ThreadLocal` **must not be equated with a local variable address on the JVM stack**. Especially in thread pools, `remove()` helps avoid retaining context beyond the intended lifecycle. If using virtual threads or other APIs, check the specific guidelines for the Java version in use.

## 12. Shared Memory Must Go Hand in Hand with the Java Memory Model

A shared heap only states that **objects can be accessed by multiple threads**; it does not state that every operation on an object is automatically atomic or immediately visible.

Key principles to remember:

- `synchronized` provides mutual exclusion and memory-visibility ordering via a monitor.
- `volatile` provides guarantees on visibility/ordering of reads/writes, but does not turn `count++` into an atomic increment.
- `AtomicInteger.incrementAndGet()` is a simple choice for atomic counting.
- `Thread.start()` and `Thread.join()` have happens-before rules governing data transfer between threads.
- Immutable objects or confined data can reduce shared mutable state and race risks.

Authoritative source: **JLS §17.4 Memory Model**. Do not replace the entire Java Memory Model with a “private stack / shared heap” diagram: that diagram describes **abstract storage organization**, not the full rules of visibility/synchronization.

## 13. Why `OutOfMemoryError` Does Not Always Mean the Heap Is Full

| Problem | Possible Symptom | Explanation |
| --- | --- | --- |
| Call depth exceeds JVM stack limit | `StackOverflowError` | Deep recursion, non-terminating call chain |
| Unable to allocate/expand JVM stack | `OutOfMemoryError` | Insufficient native/runtime memory for the stack under the given conditions |
| Heap lacks allocation space for object | `OutOfMemoryError` | Garbage collector and heap cannot supply enough storage |
| Method area lacks memory | `OutOfMemoryError` | Insufficient metadata/code/constant-pool allocations |
| Native method stack exceeds limit | `StackOverflowError` | If the implementation uses a native method stack |
| Unable to create/expand native stacks | `OutOfMemoryError` | Native resource exhaustion |
| Too many platform threads/native resources | Possibly `OutOfMemoryError` or thread creation failure | Depends on OS, limits, and JVM |

On HotSpot, messages such as `Java heap space`, `Metaspace`, or `unable to create native thread` are hints about the cause, but the JVMS does not require every implementation to return that exact wording.

**Do not run experiments that intentionally consume unbounded memory/threads** on a workstation or in production; observing statistics and reproducing within bounded limits in a test environment is safer.

## 14. How to Monitor Memory Areas on HotSpot

Some common tools/flags:

~~~bash
java -version
java -XshowSettings:vm -version
java -Xlog:help
~~~

| Configuration/Tool | What It Can Observe or Affect | What Must Not Be Concluded |
| --- | --- | --- |
| `-Xmx512m` | Java object heap limit on HotSpot | Total process memory is limited to exactly 512 MB |
| `-Xss1m` | Thread stack size according to the appropriate runtime/platform | Each Java frame occupies exactly 1 MB |
| `-XX:MaxMetaspaceSize=...` | Manages Metaspace limit on HotSpot | Metaspace is a mandatory area of every JVM |
| `jcmd <pid> GC.heap_info` | Heap/collector information | Detailed run-time constant pool of each class |
| `jcmd <pid> Thread.print` | Call stacks and threads | Contents of every operand stack by slot |
| `jcmd <pid> VM.native_memory summary` | Native Memory Tracking if enabled | Every memory category is an area in JVMS `2.5` |

HotSpot's Native Memory Tracking (NMT) can be enabled at startup with:

~~~bash
java -XX:NativeMemoryTracking=summary MemoryScopeDemo
~~~

**It is normal for the `MemoryScopeDemo` example to finish too quickly to attach.** On a long-running server, identify the PID with `jcmd -l`, then use `jcmd <pid> VM.native_memory summary` when permitted and when tracking is enabled on the JVM. Do not assume NMT commands work on every JVM.

**RSS/Process memory ≠ Java heap limit**: a process also includes metadata, native stacks, code cache, JVM internals… `-Xmx` is not an “absolute RAM limit of the process”.

## 15. Common Misconceptions

| Misconception | Fact |
| --- | --- |
| “There is only one JVM stack for the entire process.” | Each JVM thread has **its own stack**. |
| “The operand stack and the JVM stack are the same thing.” | The operand stack belongs to a **frame**; the JVM stack holds **frames**. |
| “A local reference means the created object resides on the stack.” | The local holds a **reference**; the object is allocated on the **heap** according to the model. |
| “Losing a local reference causes GC to collect the object immediately.” | The object may still be reachable; GC is not bound to run at the exact moment a method returns. |
| “`ThreadLocal` is a frame local variable.” | ThreadLocal is a **per-thread value API**, distinct from the per-invocation local array. |
| “If two threads see the same object, their locals are also shared.” | Locals are private, and can hold references to the same object. |
| “A static field has a single copy for all classloaders.” | Static state belongs to a runtime class identity; same-named classes loaded by different defining loaders remain separate. |
| “Method area = Metaspace in every JVM.” | Method area belongs to the JVMS; Metaspace belongs to HotSpot. |
| “The method area always physically resides inside the `-Xmx` heap.” | The specification only says *logically part of heap*, without mandating an implementation layout. |
| “The run-time constant pool is per-thread.” | **Per-class/interface**, located in the shared method area. |
| “A native method stack is guaranteed to exist on every JVM.” | Implementation-dependent, not always mandatory. |
| “The `pc` of a native method always points to a Java opcode.” | According to the JVMS, the JVM's pc is **undefined** when the current method is native. |
| “A shared heap automatically guarantees thread-safety.” | The Java Memory Model and proper synchronization are required. |
| “`max_stack` is the maximum number of method calls.” | It is the operand stack depth of **a single method**, not the number of frames. |
| “Every OutOfMemoryError means the Java heap is out of space.” | It can also involve metadata, stack/native resources, and other causes. |

## 16. Self-Check

**1.** Which areas are per-thread according to the JVMS?  
**Answer:** `pc`, JVM stack; native method stacks are typically per-thread **if provided by the implementation**.

**2.** Which areas are JVM-wide?  
**Answer:** Heap and method area. The run-time constant pool is **per-runtime-class/interface** but allocated in the method area.

**3.** Do two threads simultaneously executing `add(3,4)` share a single operand stack?  
**Answer:** No. Each invocation creates its own frame with its own operand stack.

**4.** Does a local `Person p` store the entire Person object on the JVM stack?  
**Answer:** No. It stores a reference value; the Person object is allocated on the heap according to the model.

**5.** Why is `static int count` not safe by default when two threads execute `count++`?  
**Answer:** `count++` is a read–modify–write operation that can race; a shared static field does not mean it is atomic.

**6.** Is `ThreadLocal<String>` equivalent to a Java local variable?  
**Answer:** No. A ThreadLocal value is bound to a thread across multiple calls; a method local is bound to a frame/invocation.

**7.** Is the run-time constant pool created anew on every method call?  
**Answer:** No. The pool belongs to the class/interface; the call's frame only holds a reference to the pool.

**8.** Is the method area always implemented by HotSpot Metaspace?  
**Answer:** No. The specification does not mandate a single implementation or physical layout.

**9.** Does returning from a frame immediately destroy an object allocated in the method?  
**Answer:** No. The object may still be reachable from elsewhere and GC does not necessarily run immediately.

**10.** Why does `MemoryScopeDemo` always print `shared-count=2` in normal execution?  
**Answer:** `increment()` is synchronized so updates are not lost; `join()` ensures main waits for both workers to finish before reading.

**11.** Does the `-Xmx` flag set an absolute RAM limit for the JVM process?  
**Answer:** No. There is also native memory, metadata, stacks, and other sources.

**12.** When executing a native method, what address does the JVMS define for the pc?  
**Answer:** The JVM's pc value is **undefined** during a native method.

## 17. Authoritative Sources

- [JVMS Java SE 25 — §2.5 Run-Time Data Areas](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.5): JVM memory structure.
- [JVMS §2.5.1 pc Register](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.5.1).
- [JVMS §2.5.2 JVM Stacks](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.5.2).
- [JVMS §2.5.3 Heap](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.5.3).
- [JVMS §2.5.4 Method Area](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.5.4).
- [JVMS §2.5.5 Run-Time Constant Pool](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.5.5).
- [JVMS §2.5.6 Native Method Stacks](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.5.6).
- [JVMS §2.6 Frames](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.6).
- [JVMS §4.7.3 Code Attribute](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.7.3): `max_stack`/`max_locals`.
- [JLS Java SE 25 — Chapter 17 Threads and Locks](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html): memory model and happens-before.
- [JDK 25 — javap](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html): inspecting bytecode.
- [JDK 25 — jcmd](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): inspecting runtime on a compatible JVM.

**Final takeaway:** `pc`/JVM stack/native stacks (if present) are per-thread; heap/method area are JVM-wide; run-time constant pools are tied to each runtime class; locals/operand stack are tied to each frame. **Per-thread does not mean objects cannot be shared**, and a **shared heap does not automatically create thread-safety**. When studying the JVM, always separate the **specification model**, the **Java Memory Model**, and the **physical memory details of an implementation**.