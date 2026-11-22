# How the JVM Runs a Java Program: Class Loader, Execution Engine, Memory, and Garbage Collector

When running `java Main`, the JVM does not just “read the `.class` file and run it”. It must **find and create a representation of the class**, **execute the bytecode instructions**, **manage data in memory areas with different roles**, and **reclaim heap memory that is no longer needed**. These four parts collaborate throughout the program's lifecycle.

This lesson focuses on the roles, responsibility boundaries, and relationships between the **Class Loader**, **Execution Engine**, **Runtime Data Areas**, and **Garbage Collector (GC)**. Descriptions of Metaspace, tiered JIT, and diagnostic flags use **HotSpot on JDK 17+** as an example; another JVM implementation may organize its internals differently.

## 1. The Big Picture

```text
.java source code
    │ javac (the JDK compiler)
    ▼
.class bytecode
    │
    ▼
[Class Loader] ── load / link / initialize class ──► [Runtime class information]
    │                                                           │
    └───────────────────────────┬───────────────────────────────┘
                                ▼
                       [Execution Engine]
                    interpret / JIT bytecode
                                │
                 read, create, update data
                                ▼
                          [JVM Memory]
                  heap, stack, method area, PC...
                                ▲
                                │ track reachable references
                       [Garbage Collector]
                 reclaim unreachable heap objects
```

The diagram is a **conceptual model**, not implying that every arrow is a sequential step or that GC runs after every statement. While the JVM is executing a method, it can continue loading other classes, allocating new objects, optimizing frequently executed code, and performing GC phases.

| Component | Question it answers | Primary role |
| --- | --- | --- |
| Class Loader | “What is this class, and where are its code and metadata?” | Find/load class definitions, coordinate linking and initialization |
| Execution Engine | “How are the instructions in a method carried out?” | Run bytecode using interpretation, JIT compilation, and machine code |
| Runtime Data Areas | “Where do data and execution state reside?” | Provide the heap, stack, and other runtime areas |
| Garbage Collector | “Which heap objects no longer need to be kept?” | Determine reachability and reclaim memory automatically |

`javac` belongs to the **JDK**; the JVM is the bytecode execution environment. **GC is a memory management service inside the JVM**, not a class loader or execution engine.

## 2. Class Loader: Bringing Class Definitions into the JVM

### 2.1. Why is class loading necessary?

A `.class` file contains bytecode, the constant pool, and descriptions of fields and methods. The JVM needs a runtime representation to identify types, look up methods, check access, and execute instructions. Class loading usually happens **on demand**, rather than loading every class on the classpath at program startup.

In the JVM, a class's identity is tied to **the class's binary name and its defining class loader**. Two different class loaders defining the same name `com.example.Plugin` can produce two different types; therefore, casting or communicating across plugins may encounter `ClassCastException` or `LinkageError` even though the class names look identical.

### 2.2. Three commonly mentioned phases

1. **Loading:** the class loader finds the bytes of the class definition and the JVM creates the corresponding representation.
2. **Linking:** consists of **verification** (checking bytecode constraints), **preparation** (allocating/setting default values for `static` fields), and **resolution** (turning symbolic references in the constant pool into actual references; may be done lazily depending on the JVM).
3. **Initialization:** executes `static` field initialization logic and `static { ... }` blocks according to language rules, usually triggered by the first **active use**.

Do not equate **loaded** with **initialized**. For example, obtaining the literal `SomeType.class` does not necessarily run the `static` initializer block. Conversely, reading a `static` field that is not a compile-time constant usually requires initializing the class that declares that field. Referencing a `static final` constant of a primitive/`String` type that has a constant value at compile time may be inlined and **not** trigger class initialization.

### 2.3. Common loaders in HotSpot

| Loader | Typical responsibility |
| --- | --- |
| Bootstrap | Loads Java's core platform classes; with `Class.getClassLoader()` it may be represented as `null` |
| Platform | Loads platform classes handled by the platform class loader |
| Application/System | Loads most application classes from the appropriate classpath/module path |
| Custom | Loads classes for specialized needs, such as plugins, containers, or isolation mechanisms |

Built-in loaders typically use **parent delegation**: asking the parent loader before looking up a definition themselves. Custom mechanisms have exceptions; “the parent always loads first” must not be assumed to apply to every custom loader.

**The Class Loader's job ends at class definition/lifecycle; it does not run the entire algorithm in `main` itself.** Once a method's code is established, the execution engine takes over execution.

## 3. Execution Engine: Executing Bytecode

Bytecode describes operations such as loading variables, computing, calling methods, creating objects, branching, and returning. The execution engine makes these operations take effect at runtime.

- **Interpreter:** executes bytecode as the program runs, allowing methods to execute without needing optimized machine code yet.
- **Just-in-Time compiler (JIT):** based on execution information (profiling), compiles suitable code segments/methods into **native machine code** so subsequent runs are generally faster. HotSpot can use tiered compilation, inlining, and many other optimizations.
- **Deoptimization:** when an assumption used for optimization no longer holds, HotSpot can fall back to a less optimized execution state while preserving program semantics.

`JIT` is not `javac`: `javac` turns source code into bytecode **before running**; JIT compiles bytecode into machine code **at runtime**. There is no guarantee that every method will be JIT-compiled, or that every call will run along the exact same execution path. Compiled machine code can reside in HotSpot's **code cache**.

For example, for the call `sum(2, 3)`, the JVM creates/pushes an appropriate method frame, performs the arithmetic operations, and places the result into the caller's context. Frames and the data used in operations relate to the memory areas in the next section.

## 4. Runtime Data Areas: Where Does Data Live?

**Important distinction:** The Java Virtual Machine Specification describes data areas **by function**; actual names and allocation in HotSpot do not always correspond 1-to-1 with how they are drawn in documentation.

| Memory area | Shared or private? | What does it contain and what is it used for? |
| --- | --- | --- |
| **Heap** | Shared across threads | Objects and arrays allocated at runtime; the main area managed by GC |
| **Java Virtual Machine Stack** | One stack per thread | **Frames** for Java method calls: local variables, operand stack, linking/return information |
| **PC Register** | Per thread | Position of the JVM instruction currently executing in the current Java method; content for native methods is specified differently |
| **Method Area** | Shared | Class/type descriptions, method structures, runtime constant pool, and class-level data according to the specification model |
| **Native Method Stack** | Tied to native execution, implementation-dependent | State supporting native methods when the JVM uses this type of stack |

In **modern HotSpot**, most class metadata is stored in a native memory area called **Metaspace** (one way of implementing the information part of the method area); the **code cache** holds compiled machine code. Therefore, **method area is not simply synonymous with “heap”**, and `-Xmx` is not the total memory limit of the process.

### 4.1. A stack frame is not a heap object

Each Java method call creates a frame context with parameters, local variables, and an operand evaluation area. When the call finishes, the frame is no longer active. When a function has a variable `Person p`, that variable's value may be a **reference to an object**, while the object belongs to the **heap** model, not “the entire object lives on the stack”.

This is the programming/specification model. The JIT may place values in registers or eliminate object allocation via escape analysis and scalar replacement; one should not infer exact physical placement from a single line of source code.

### 4.2. Stack and heap lifetimes differ

A local variable going out of scope does not mean GC has run. When **there is no longer any strong reference path from GC roots to the object**, the object becomes eligible for reclamation in a subsequent GC cycle. If the object is still stored in a `static` field, collection, thread-local, or another long-lived object, it can continue to be retained even after the method that created it has finished.

### 4.3. Non-heap memory to distinguish

Direct buffers, native allocations, metadata, and thread stacks can use native memory. Java's Garbage Collector does not replace the obligation to close **files, sockets, database connections**, or release resources with explicit lifecycles. Prefer `try-with-resources` for resources implementing `AutoCloseable`.

## 5. Garbage Collector: Reclaiming Unreachable Objects

GC automatically manages most of the lifecycle of **heap memory**. The core idea is **reachability**, not “setting a variable to `null` immediately deletes the object”.

### 5.1. GC roots and the reference graph

GC starts from **roots** appropriate to the runtime state (for example, active references in threads, class-level references, JNI handles), and follows reference relationships to reachable objects. Objects with no remaining path from roots can be reclaimed. Two objects that only point to each other without connecting to roots **can still be reclaimed**.

```text
GC root ──► A ──► B           C ◄──► D
             │
             └────► E

A, B, E: still reachable from root.
C, D: only point to each other, unreachable from root → can be reclaimed.
```

The exact algorithm and timing depend on the collector: it may mark, copy, move/compact, or work concurrently with application threads. Some operations require a **safepoint/stop-the-world pause**; one should not claim “GC runs completely in the background” or “GC always pauses the entire application in the same way”.

### 5.2. What can and cannot GC guarantee?

- **Can:** find and process unreachable objects according to the collector's policy, enabling heap reuse; modern collectors can also support class unloading when conditions are met.
- **Cannot:** guarantee that a specific object is reclaimed immediately after `obj = null`, guarantee zero latency, or automatically close all OS resources.
- **`System.gc()`:** is essentially a request/hint to the runtime; it may be ignored or handled differently depending on flags and implementation, not a confirmation that objects have been reclaimed.
- **Memory leaks in Java:** can still happen in the sense that objects are **still reachable but no longer useful** (for example, unbounded caches, unregistered listeners).

Collectors such as G1, ZGC, or Parallel GC optimize different throughput, pause, and footprint goals. No single GC algorithm is mandated by the JVM Specification for all JVMs.

## 6. Tracing a Runnable Java 17 Example

Create the file **`JvmFlowDemo.java`**:

```java
public class JvmFlowDemo {

    static class Config {
        static {
            System.out.println("Config initialized");
        }

        static int factor = 7; // Not a compile-time constant.
    }

    static int twice(int number) {
        int result = number * 2;
        return result;
    }

    public static void main(String[] args) {
        System.out.println("main begins");

        int output = twice(Config.factor);
        System.out.println("result = " + output);

        Object sample = new Object();
        System.out.println("object type: " + sample.getClass().getSimpleName());
        sample = null; // Does not prove GC will run immediately.

        System.out.println("main ends");
    }
}
```

Compile and run with JDK 17+:

```bash
javac JvmFlowDemo.java
java JvmFlowDemo
```

**Program stdout:**

```text
main begins
Config initialized
result = 14
object type: Object
main ends
```

Step-by-step explanation:

1. `javac` generates `JvmFlowDemo.class` and `JvmFlowDemo$Config.class` from the source code (the nested class filename is `javac`'s compilation convention).
2. At startup, the JVM loads/links/initializes the classes needed to run `main`. Loading other dependent classes may continue afterward.
3. The first statement in `main` prints `main begins`. The expression reading the `Config.factor` field triggers initialization of `Config` if not already initialized, because it is a **`static` field that is not a compile-time constant**. Therefore, the line `Config initialized` appears before `result = 14`.
4. The call to `twice` needs the method's execution context: parameter `number`, local variable `result`, multiplication, and return value. The interpreter or JIT-generated code performs the operations with the same observable result.
5. `new Object()` creates an object according to Java semantics; the variable `sample` holds a reference to it. The JVM executes `getClass().getSimpleName()` and prints `Object`.
6. After assigning `sample = null`, the program no longer intentionally holds a reference via this variable; if no other strong reference path remains, the object **may become eligible** for GC reclamation. The example **does not demonstrate GC timing at all**, and the output does not depend on whether GC runs.

> Note: The JVM/JIT is permitted to optimize object usage and allocation as long as observable behavior is preserved. The description “object on the heap, reference in the frame” is a useful learning model, not an exact map of every memory cell after optimization.

## 7. Collaboration of the Four Components in the Application Lifecycle

| Event | Class Loader | Execution Engine | Runtime Data Areas | GC |
| --- | --- | --- | --- | --- |
| JVM prepares to call `main` | Loads/links necessary classes | Prepares to execute bytecode | Class metadata, thread/frame state | Not necessarily any activity yet |
| Reaching a new class | Loads/links, initializes when trigger condition is met | Executes initialization code if needed | Updates class-level data | May operate independently |
| Calling a method | May need to load additional dependent types | Interprets/JITs, executes instructions | Frame, PC, accessed objects | May run interleaved with application |
| Creating an object | Needs type properly processed | Executes `new` and constructor | Allocation/logical object, reference management | May be triggered by allocation pressure |
| Losing reference paths | Does not decide object liveness | Continues executing program | Root graph no longer holds object | May reclaim in an appropriate GC cycle |
| Process termination | Class definitions end lifecycle with JVM | Stops execution | Process memory reclaimed by OS | No need to wait for GC per object |

The Class Loader and Execution Engine **do not replace each other**: the loader handles **types and definitions**, the engine executes **behavior**; memory holds state for both to work; GC helps manage the lifetime of heap objects.

## 8. Observing and Diagnosing with HotSpot on JDK 17+

The following commands are examples of observation tools, **not mandatory behavior for every JVM**.

```bash
# Show class loading activity (verbose log; Java 17+ HotSpot)
java -Xlog:class+load=info JvmFlowDemo

# Show GC events (this example may not trigger GC)
java -Xlog:gc* JvmFlowDemo

# Example heap settings for a real application; not total process RAM
java -Xms256m -Xmx512m JvmFlowDemo
```

For a running JVM application, use `jcmd <pid> GC.heap_info` to view heap information supported by the implementation; `jcmd <pid> Thread.print` helps view stacks/threads, while profiling/JFR tools help analyze allocation, pauses, and CPU. Make sure to pick the right PID and read logs according to **actual time/collector**; do not use a short run that triggers no GC to conclude that GC is disabled.

Common symptoms that require pinpointing the right component:

| Symptom | First direction to investigate |
| --- | --- |
| `ClassNotFoundException` / `NoClassDefFoundError` | Classpath/module path, class loader, and the difference between definition not found vs. error during linking/initialization |
| `ClassCastException` between plugins despite identical type names | Class identity by defining loader; dependency/shared API |
| `StackOverflowError` | Deep recursion or cyclic call loops, JVM stack usage |
| `OutOfMemoryError: Java heap space` | Heap limit/demand, allocation rate, retention graph |
| `OutOfMemoryError: Metaspace` | Class metadata, loader retention, Metaspace limit |
| Long pauses or reduced throughput | GC logs, heap pressure, collector choice/configuration; also check application load |
| High CPU in frequently executed methods | Profiling, hotspot methods, JIT, lock contention; do not jump to blaming JIT |

`OutOfMemoryError` has many causes outside the heap; increasing `-Xmx` does not automatically fix class-loader leaks, stack overflows, native memory exhaustion, or thread/resource leaks.

## 9. Common Misconceptions

1. **“When the loader reads a class, it immediately runs the constructor.”** Incorrect. Loading, linking, and initializing a class is different from calling the constructor of an **object instance**.
2. **“All objects live on the stack because local variables are in the stack.”** Incorrect for the JVM model: objects have heap semantics; local variables can hold references. The JIT may also optimize placement.
3. **“Setting a variable to `null` forces GC to delete the object.”** There is no such guarantee. Reclamation is based on reachability and the collector.
4. **“No `free()` means memory leaks are impossible.”** Objects can be retained by caches, listeners, queues, `static` fields, or `ThreadLocal` even when no longer needed.
5. **“GC replaces `close()`.”** GC mainly manages heap memory; files, sockets, and connections should be closed according to their lifecycle.
6. **“Java is run purely by interpretation.”** HotSpot has a JIT; execution strategy can change as the program runs.
7. **“`-Xmx` is the JVM's total RAM limit.”** It only controls the maximum Java heap; there are also thread stacks, Metaspace, code cache, and native allocations.
8. **“The method area is always a Java heap region called PermGen.”** False for modern HotSpot: PermGen was replaced by Metaspace in Java 8; the JVM spec does not mandate HotSpot's internal organization.
9. **“Whenever GC occurs, all threads pause for the same duration.”** Depends on the GC algorithm and phase; some collectors do much of their work concurrently and have specific points where the application must pause.

## 10. Self-Check Your Ability to Explain

- Why does printing `Config initialized` happen after `main begins` in the example, even though `Config` was compiled along with the program?
- When calling `twice(7)`, what role do the frame/local variables play and what does the execution engine do?
- If a `static` cache always holds a list of objects, why can't GC reclaim those objects yet?
- Why might two plugins loading the same class name via two defining loaders not be castable to each other?
- When an application reports a heap, Metaspace, or stack error, why shouldn't the remediation be the exact same?

**Remember:** the loader handles **class definitions**; the execution engine handles **instructions**; runtime memory holds **state and objects**; GC handles **heap objects that are no longer reachable**. Each component has its own responsibility, yet only makes full sense when viewed together along the execution flow.

### Authoritative References for Further Reading

- [Java Virtual Machine Specification 17 — Runtime Data Areas (§2.5)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5)
- [Java Virtual Machine Specification 17 — Loading, Linking, and Initializing (Chapter 5)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html)
- [Java Language Specification 17 — Initialization of Classes and Interfaces (§12.4)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4)
