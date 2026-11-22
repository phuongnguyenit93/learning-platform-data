# getObjectSize Returns an Implementation-Specific Size Estimate

In a Java agent, **`Instrumentation.getObjectSize(Object)`** returns a `long` representing an **estimate of the amount of storage consumed by a specific object**. The Java SE 17 documentation calls this result an *implementation-specific approximation*: **it is not an exact byte count according to a fixed formula of the Java language**. The estimate may include some or all of the object's overhead, and is typically useful for comparisons **within the same JVM implementation and configuration**, but should not be used for absolute comparisons across different JVMs. The specification also states that **the estimate may change even during a single invocation of the JVM**.

A second common point of confusion: `getObjectSize(holder)` **does not automatically traverse references** to include arrays, lists, trees, or the object graph kept alive by `holder`. If Holder only contains a reference to a `byte[8192]` array, Holder's shallow size can be very small while the array is a separate object larger than 8 KiB.

This lesson focuses on the API contract, shallow/deep/retained size, object headers, array layout, compressed references, alignment, empirical Java 17+ results across different HotSpot configurations, and how to avoid misinterpreting measurements in runtime investigations.

## 1. The `Instrumentation.getObjectSize` Contract

Signature:

```java
long getObjectSize(Object objectToSize);
```

According to the official Java SE 17 documentation:

- The method takes **an object** to measure, not a `Class<?>` or a class name.
- It returns an **implementation-specific approximation** of the amount of storage consumed by the **specified object**, in bytes.
- The result may include some or all of the **object overhead**; it is useful for comparisons **within a single implementation**, not across implementations.
- **The estimate may change during a single invocation of the JVM**. There is no guarantee of an invariant value.
- If the argument is `null`, it throws **`NullPointerException`**, rather than returning `0`.

**The API does not guarantee** how many bytes the header layout uses, at what offset a field is placed, how many bytes a reference takes, how much padding is added, nor does it guarantee that the result is the total heap/native/retained memory the application is consuming.

Example call:

```java
// Illustrative code inside a method that already has Instrumentation inst.
Object target = new Object();
long estimate = inst.getObjectSize(target);
System.out.println("estimated shallow bytes=" + estimate);
```

This is an **illustrative code snippet**, not a standalone program: a normal Java program cannot instantiate `Instrumentation` with `new`. The JVM provides this interface to a Java agent via `premain` or `agentmain`.

Source: [Oracle Java SE 17 — Instrumentation#getObjectSize](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#getObjectSize(java.lang.Object)).

## 2. Shallow Size Differs from Deep Graph Size and Retained Size

Suppose a Holder is created as follows:

```java
// Code describing an object graph, not a standalone program.
final class Holder {
    Object value;
}
Holder h = new Holder();
h.value = new byte[8192];
```

Model:

```text
  object h: Holder                    object h.value: byte[8192]
+-------------------------+         +---------------------------+
| header + reference slot | ------> | header + 8192 bytes      |
+-------------------------+         +---------------------------+
          object 1                            object 2
```

| Metric | Meaning | Provided by `getObjectSize(h)`? |
| --- | --- | --- |
| **Shallow size of h** | Storage of Holder itself, header/instance fields/padding per the JVM | **Yes, as an estimate**. |
| **Shallow size of the array** | Header and 8192 `byte` elements inside the array object | **Not automatically included**; measure the array separately with `getObjectSize(h.value)`. |
| **Deep/reachable-graph size** | Total size of objects reachable via references, according to a traversal policy | **No**; requires traversing the graph and avoiding duplicate/cyclic objects. |
| **Retained size** | The portion of the graph kept alive solely by the object/root under consideration, per reachability/dominator | **No**; requires heap graph analysis. |
| **Used heap, committed heap, RSS** | Heap-level or process-level memory, with other overhead/GC/native components | **No**; requires tools appropriate for each scope. |

**Do not equate deep size with retained size.** Suppose:

```text
   Holder A -----\
                  +----> shared byte[8192]
   Holder B -----/
```

The shared array is in the graph of both A and B. If you add the array for **each** reference, it will be double-counted. If A is dropped while B still holds the array, the array **does not become garbage** just because A was freed. Therefore, the retained size of A does not automatically include the entire array.

**Distinguish between a reference and the content it points to:** a field of type `Object` only stores a **reference slot** in Holder's layout. The array's contents reside in **another array object**. Changing the reference from `null` to an 8 KiB array does not require Holder to add a field containing 8192 bytes.

## 3. Why Does Size Depend on the JVM Implementation?

The Java language defines the behavior of fields, arrays, classes, and methods; it does not fix a physical layout for every object across every VM. Parts that may differ:

| Component | Impact |
| --- | --- |
| **Object header** | The JVM stores object management data and class/metadata information per its implementation; the size is not fixed in Java SE. |
| **Array header** | Arrays typically have additional length information, even when they have no elements. |
| **Field layout** | The JVM may arrange/order instance fields and padding based on implementation, inheritance, and access rules. |
| **Reference width** | References may use a compressed or uncompressed format, changing the storage used by a slot. |
| **Object alignment** | The VM may round object sizes up to an alignment multiple, resulting in padding. |
| **Primitive array payload** | A `byte[]` array stores `byte` elements inside the array itself; `long[]` and other types have different slot sizes. |
| **Object reference array** | `Object[n]` has n reference slots; it **does not automatically contain n child objects**. |
| **JVM version/vendor/flags** | Layout and allocation strategies may change even with identical classfiles. |

A model **for visualization**, **not a standard Java SE formula**:

```text
estimated array bytes ~= roundUp(
    arrayHeaderBytes + length * elementSlotBytes,
    alignmentBytes)
```

Do not hard-code `arrayHeaderBytes = 16` or `referenceSlotBytes = 4` as Java constants. With different JVM configurations, those values can change; some implementations also have special layouts.

### 3.1. Compressed Ordinary Object Pointers

On some 64-bit HotSpot VMs, **compressed oops** allow many object references to be represented with a smaller width than a full pointer under certain conditions. This is especially noticeable in `Object[]` arrays with many reference slots. If compressed oops are disabled, the same array may have a larger estimate.

Do not infer that "every 64-bit JVM has 8-byte references" or "every Java 17 JVM has 4-byte references." The VM configuration itself determines this. Related documentation: [Java 17 HotSpot Performance Enhancements — compressed oops](https://docs.oracle.com/en/java/javase/17/vm/java-hotspot-virtual-machine-performance-enhancements.html).

### 3.2. Alignment and Padding

An object with a small field payload can still be rounded up to a multiple. `byte[0]` typically has a non-zero estimate because it is still an array object with overhead. A `byte[8192]` array has a payload of exactly 8192 bytes, but may need header and padding.

Changing object alignment within the same HotSpot VM can change `getObjectSize` even when **source and classfiles are unchanged**. Sometimes an object already has a size that is a multiple of the new alignment, so its estimate does not change.

### 3.3. Conditional Comparisons

For a meaningful comparison, you should at minimum know the VM vendor/version, architecture, flags, object type, and the timing of the inspection. Even when all of these match, the API still only provides an **approximation** — you should not build billing/resource allocation logic based on absolute assumptions.

## 4. Obtaining `Instrumentation` via a Java Agent

A normal Java program cannot write:

```java
// NOT valid code to obtain Instrumentation from the JVM.
Instrumentation inst = new Instrumentation();
```

`Instrumentation` is an interface, and the JVM provides an instance through a **Java agent** entry point.

For a startup agent, the JAR needs to declare:

```text
Manifest-Version: 1.0
Premain-Class: demo.size.SizeAgent

```

When launching:

```bash
java -javaagent:size-agent.jar -cp out demo.size.SizeDemo
```

The JVM reads the main manifest and invokes `public static void premain(String, Instrumentation)` before the application `main`. The agent holds the `Instrumentation` reference so the test application can call the measurement method.

**You do not need `Can-Redefine-Classes: true` or `Can-Retransform-Classes: true`** just to call `getObjectSize`. Those flags relate to redefining/retransforming loaded classes, not a separate capability required for the size measurement method.

For agents dynamically loaded using the Attach API, the entry point is `Agent-Class`/`agentmain` if the environment supports it, but the experiment below uses `premain` to be self-contained and easy to reproduce.

## 5. Java 17+ Experiment: Same Holder, Different Referent Sizes

The experiment has **two Java files** and one manifest; it does not use Maven, JOL, or external libraries. We measure:

1. A Holder holding `null`, a `byte[0]` array, and a `byte[8192]` array.
2. The two array objects `byte[0]` and `byte[8192]` themselves.
3. Two reference arrays `Object[0]` and `Object[100]`, containing no element objects yet.
4. Verifying that `getObjectSize(null)` throws an exception per the contract.
5. Re-running with HotSpot flags to see that the estimate can differ.

### 5.1. File Structure

```text
object-size-demo/
├── src/demo/size/
│   ├── SizeAgent.java
│   └── SizeDemo.java
└── agent.mf
```

The manifest file is given in section 4; remember to save it as `agent.mf` with a trailing newline.

### 5.2. `src/demo/size/SizeAgent.java`

```java
package demo.size;

import java.lang.instrument.Instrumentation;

public final class SizeAgent {
    private static volatile Instrumentation instrumentation;

    private SizeAgent() {}

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;
        System.out.println("[agent] ready");
    }

    public static long shallowSize(Object value) {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Run with -javaagent:size-agent.jar");
        }
        return inst.getObjectSize(value);
    }
}
```

Explanation:

- `premain` receives `Instrumentation` directly from the JVM; the program does not guess the layout manually.
- A `static volatile` variable is a safe way to publish the reference when other threads access it. It does **not** make heap measurements an atomic snapshot.
- `shallowSize` calls `inst.getObjectSize(value)` directly per the API. It does not traverse field references.
- If `-javaagent` is forgotten, the code reports a clear error. For `null`, it passes `null` to the API and the API throws `NullPointerException`.

### 5.3. `src/demo/size/SizeDemo.java`

```java
package demo.size;

public final class SizeDemo {
    private SizeDemo() {}

    static final class Holder {
        final Object value;

        Holder(Object value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        byte[] empty = new byte[0];
        byte[] large = new byte[8192];

        long holderNull = SizeAgent.shallowSize(new Holder(null));
        long holderEmpty = SizeAgent.shallowSize(new Holder(empty));
        long holderLarge = SizeAgent.shallowSize(new Holder(large));
        long arrayEmpty = SizeAgent.shallowSize(empty);
        long arrayLarge = SizeAgent.shallowSize(large);
        long refsEmpty = SizeAgent.shallowSize(new Object[0]);
        long refsHundred = SizeAgent.shallowSize(new Object[100]);

        System.out.println("[size] holder-null=" + holderNull);
        System.out.println("[size] holder-empty-array=" + holderEmpty);
        System.out.println("[size] holder-large-array=" + holderLarge);
        System.out.println("[size] byte[0]=" + arrayEmpty);
        System.out.println("[size] byte[8192]=" + arrayLarge);
        System.out.println("[size] Object[0]=" + refsEmpty);
        System.out.println("[size] Object[100]=" + refsHundred);
        System.out.println("[check] holder-estimates-equal=" +
                (holderNull == holderEmpty && holderEmpty == holderLarge));
        System.out.println("[check] long-byte-array-larger=" + (arrayLarge > arrayEmpty));
        System.out.println("[check] long-ref-array-larger=" + (refsHundred > refsEmpty));
        try {
            SizeAgent.shallowSize(null);
            System.out.println("[check] null=unexpected");
        } catch (NullPointerException expected) {
            System.out.println("[check] null=NullPointerException");
        }
    }
}
```

In this program:

- The three Holders are **three objects of the same class**, differing in **reference value**. The difference in the pointed-to array does not change the number of fields in Holder.
- `byte[8192]` is a **separate** array object with 8192 bytes of primitive data, so it is measured independently.
- `new Object[100]` allocates **one array object with 100 `null` reference slots**; it does not allocate 100 `new Object()` objects.
- The `[check]` lines are comparisons on the **experimental JVM**. Even when they print `true` on the test JVM, they must not be extrapolated into a layout formula guaranteed by Java SE for every VM.

### 5.4. Compiling and Packaging

From the `object-size-demo/` directory, with **Bash**:

```bash
mkdir -p out

javac --release 17 -d out \
  src/demo/size/SizeAgent.java \
  src/demo/size/SizeDemo.java

jar --create --file size-agent.jar --manifest agent.mf \
  -C out demo/size/SizeAgent.class

java -javaagent:size-agent.jar -cp out demo.size.SizeDemo
```

On **PowerShell**, put each command on a single line:

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -d out src/demo/size/SizeAgent.java src/demo/size/SizeDemo.java
jar --create --file size-agent.jar --manifest agent.mf -C out demo/size/SizeAgent.class
java -javaagent:size-agent.jar -cp out demo.size.SizeDemo
```

The `\` in Bash is line continuation, not PowerShell line-continuation syntax. Code compiled with `--release 17` uses only Java 17 APIs; it can run on JDK 17+ when the JVM supports Java agents. The `size-agent.jar` file needs to contain `SizeAgent.class` and the manifest, while the app along with nested `SizeDemo$Holder.class` resides on the `out` classpath.

## 6. Empirical Results: Same Code, Different JVM Flags

The stdouts below were **compiled with `javac --release 17` and run on Zulu OpenJDK 24.0.2, HotSpot 64-bit**. They **are not standard byte counts for every Java 17/JVM**. The `-XX:...` options are VM-specific and must be used on a HotSpot VM that supports them.

### 6.1. Default Configuration

```bash
java -javaagent:size-agent.jar -cp out demo.size.SizeDemo
```

Verified stdout:

```text
[agent] ready
[size] holder-null=16
[size] holder-empty-array=16
[size] holder-large-array=16
[size] byte[0]=16
[size] byte[8192]=8208
[size] Object[0]=16
[size] Object[100]=416
[check] holder-estimates-equal=true
[check] long-byte-array-larger=true
[check] long-ref-array-larger=true
[check] null=NullPointerException
```

The results clearly illustrate:

- `Holder(null)`, `Holder(byte[0])`, and `Holder(byte[8192])` **are all estimated at 16 bytes** in this configuration.
- The `byte[8192]` array is estimated at **8208 bytes** when calling `getObjectSize` **on the array itself**.
- The `Object[100]` array has an estimate of **416 bytes** due to reference slots, not because of 100 child objects.
- The empty array `byte[0]` still has an estimate of **16 bytes**, showing object/array overhead.
- Passing `null` throws `NullPointerException` as documented.

### 6.2. Disabling Compressed References on HotSpot

```bash
java -XX:-UseCompressedOops -javaagent:size-agent.jar -cp out demo.size.SizeDemo
```

Stdout on the same OpenJDK 24.0.2:

```text
[agent] ready
[size] holder-null=24
[size] holder-empty-array=24
[size] holder-large-array=24
[size] byte[0]=16
[size] byte[8192]=8208
[size] Object[0]=16
[size] Object[100]=816
[check] holder-estimates-equal=true
[check] long-byte-array-larger=true
[check] long-ref-array-larger=true
[check] null=NullPointerException
```

**Without changing a single line of Java**, `Holder` increases from an estimate of 16 to 24 bytes; `Object[100]` goes from 416 to 816 bytes. In this experiment, `byte[0]` and `byte[8192]` keep the same estimate because they do not have hundreds of reference slots to expand. This is a concrete example of the impact of **reference width**.

### 6.3. Changing Object Alignment on HotSpot

```bash
java -XX:ObjectAlignmentInBytes=32 -javaagent:size-agent.jar -cp out demo.size.SizeDemo
```

Verified stdout:

```text
[agent] ready
[size] holder-null=32
[size] holder-empty-array=32
[size] holder-large-array=32
[size] byte[0]=32
[size] byte[8192]=8224
[size] Object[0]=32
[size] Object[100]=416
[check] holder-estimates-equal=true
[check] long-byte-array-larger=true
[check] long-ref-array-larger=true
[check] null=NullPointerException
```

In this 32-byte alignment configuration, `Holder` and empty arrays are estimated at **32 bytes**; `byte[8192]` is **8224 bytes**. `Object[100]` remains **416 bytes** because its estimate already fits the chosen alignment. **Changing a flag does not force every object to change size.**

### 6.4. Comparison Table

| Object | Default | `-XX:-UseCompressedOops` | `-XX:ObjectAlignmentInBytes=32` |
| --- | ---: | ---: | ---: |
| `Holder(null)` | 16 | 24 | 32 |
| `Holder(byte[8192])` | 16 | 24 | 32 |
| `byte[0]` | 16 | 16 | 32 |
| `byte[8192]` | 8208 | 8208 | 8224 |
| `Object[0]` | 16 | 16 | 32 |
| `Object[100]` | 416 | 816 | 416 |

**Units are bytes.** This is data from **one JVM and three different startups**; do not treat the table as invariant constants. `--release 17` ensures Java 17 target source/API/classfiles at compile time; **it does not freeze object layout** at runtime.

Use these HotSpot flags for research in controlled test environments; do not arbitrarily change production configurations just to reproduce sample byte counts.

## 7. String, Collections, and Off-Heap: Easily Misunderstood Examples

### 7.1. String and Character Data

A `String` has instance fields and may reference a backing array depending on the implementation. Therefore, `getObjectSize(s)` measures the **String wrapper object**, and does not automatically add all character data residing in another object.

```java
// Illustrative code inside a method that already has Instrumentation inst.
String shortText = "a";
String longText = "a".repeat(10000);
long shortEstimate = inst.getObjectSize(shortText);
long longEstimate = inst.getObjectSize(longText);
System.out.println(shortEstimate + " / " + longEstimate);
```

No fixed stdout is provided for this snippet: String content, compact strings, interning, backing representation, and JVM flags can all affect it. **Two shallow estimates can be equal in an implementation even though the storage cost of the character contents of the two values is vastly different.**

### 7.2. List and Map

An `ArrayList<?>` typically holds a backing array. When calling `getObjectSize(list)`, that is an estimate of **the list object itself**, excluding the backing array or the elements it references. Similarly, a `HashMap` may hold a table and nodes/entries as separate objects.

A list with one million elements **cannot** have its total heap footprint quantified by a single `getObjectSize(list)` call. To measure the total, you must understand the object graph, sharing, object reuse, and attribution policies.

### 7.3. Direct ByteBuffer and Native Memory

`ByteBuffer.allocateDirect(...)` can use **native/off-heap storage**. `getObjectSize(buffer)` primarily reflects the storage of the **specific Java object** passed in, and **does not automatically measure the entire native allocation** that the object manages. If the issue is high process RSS with a small heap, look at native memory/tooling separately rather than just the wrapper's size.

### 7.4. Static Fields and Primitives

`static byte[] cache = new byte[100000]` is state associated with the class, not an instance field embedded in every object of that class. `getObjectSize(new MyClass())` does not automatically include that static array.

If you pass a primitive to a method accepting `Object`, Java may **box** it into a wrapper, for example `Integer.valueOf(5)`. In that case you are measuring the **Integer object**, not the size of a primitive `int` variable on the stack/local variable.

## 8. Why You Must Not Extrapolate Total Heap or RSS from Shallow Size

Measuring one object and measuring a JVM process are two different tasks.

- **Heap usage** fluctuates with allocation, GC, fragmentation, heap regions, and concurrent activities.
- **Committed/reserved heap** does not equal the sum of shallow sizes of all live objects.
- Process **RSS** also includes thread stacks, code cache, metaspace/native allocations, mapped files, and regions outside the Java heap.
- **TLAB/allocator overhead** is not fully described by a single `getObjectSize(oneObject)` call.
- **Retained heap** requires considering the object graph, roots, and dominator relationships; naive summation can double-count shared objects.
- **GC** does not guarantee that bytes can or will be freed immediately when you drop a reference; another object may still keep it alive.

Nor should you take `Runtime.totalMemory() - Runtime.freeMemory()` "before and after new" as an exact object size: between the two measurements there can be class initialization, allocations by other threads, GC, JIT, buffers, and VM bookkeeping.

If you need to track down a memory leak, knowing "one object's size is 16 bytes" does not tell you **how many such objects exist**, their creation rate, the roots keeping them alive, or their lifetime.

## 9. Which Tool Fits Which Question?

| Question | Role of `getObjectSize` | Complementary Approach |
| --- | --- | --- |
| Shallow layout of a specific object? | Gives a useful estimate, recording JVM/flags | JOL (Java Object Layout) to inspect headers/fields/padding of a specific JVM |
| How does shallow size differ when changing flags? | Can measure and compare each configuration | Benchmark on a VM with the same vendor/version and clearly specified flags |
| Which object/GC root retains the most heap? | **Insufficient** because it does not traverse the reference graph | Heap dump + Eclipse MAT/VisualVM or a heap profiler with retained size/dominator tree |
| Which allocation type is growing fast? | A single size measurement **gives no allocation rate/provenance** | Java Flight Recorder (JFR), allocation profiler |
| High native memory or RSS? | **Insufficient** | Native Memory Tracking (when supported), process/OS profiler, diagnostics |
| Does an added class/field increase shallow size? | Can compare in a controlled manner | Layout inspection + regression tests on the target JVM |
| How much total memory does Feature A/B use? | Only a very narrow reference point | Allocation sampling, heap graph, GC/heap metrics, load test |

**JOL** is an OpenJDK tooling project, **not** an API automatically included in `java.lang.instrument`. JFR also measures different data: allocation events, GC, JVM activity, and does not replace a retained graph without the corresponding reference information.

## 10. Measuring at Runtime Comparably

### 10.1. Record the Environment and Metric Definition

Each report line should clearly state:

```text
metric: estimated_shallow_object_bytes
source_api: Instrumentation.getObjectSize
vm: vendor/name/version
runtime: Java version, architecture, heap/VM flags relevant to layout
object: class name and defining class loader when relevant
sample: number of objects, time window, selection criteria
not_included: reachable objects, retained heap, native memory
```

You can read some information from `System.getProperty("java.vm.name")`, `java.vm.version`, and `os.arch`, while VM options/GC flags should use appropriate diagnostics (on HotSpot you can use `jcmd <pid> VM.flags`) rather than inferring from class names.

When comparing before/after builds, run under the **same VM configuration**. Do not conclude there is a memory leak just because one HotSpot run has compressed references enabled and another does not.

### 10.2. Do Not Keep an Indefinite Per-Class Constant Size Table

The measured value **is not a language constant**, and the API allows the estimate to change even within the same JVM invocation. You should not use `Map<Class<?>,Long>` as a "permanent source of truth" for the entire runtime if the product requires accuracy.

If an application only needs an estimate used within a specific measurement window, you can cache the result with clear metadata/configuration, but you must document the limits of the inference and verify on the running VM.

### 10.3. Avoid Writing Uncontrolled Reflection-Based "Deep Size"

Traversing references from a root object runs into many issues:

1. **Shared objects**: requires an identity-based visited set; `equals()` may treat two distinct instances as equal.
2. **Cycles**: an object graph can have self-referential cycles, leading to infinite recursion if visited nodes are not tracked.
3. **JPMS encapsulation**: reflection on private fields may be blocked; do not open all packages just to compute size.
4. **Reference types**: weak/soft/phantom references, classloaders, and interned objects require clear policies.
5. **Off-heap/native resources**: do not appear as simple child objects for traversal.
6. **Consistency**: other threads may mutate the graph during measurement.

Even after handling all those issues and summing the shallow sizes of **unique** objects in the graph, you only have a **definition of reachable-graph sum**, **not retained size**. Retained size depends on the reference graph from **all GC roots** and dominator relationships.

### 10.4. Do Not Overload the Application for Measurement

Do not create millions of sample objects on the hot path or request a Full GC just to "stabilize" a shallow measurement. For production, limit frequency, sampling, and agent overhead, and distinguish measurement perturbation from the original application behavior.

## 11. Common Errors and Misconceptions

| Statement/Issue | Correct Understanding |
| --- | --- |
| "`getObjectSize` returns the exact byte count of a class per the Java spec." | False: it is an **implementation-specific approximation**. |
| "Every JVM with the same bytecode must report the same size." | False: layouts and VM flags differ. |
| "Holder points to an 8 KiB array, so Holder's size must be around 8 KiB." | False: that is another object; measure the array separately. |
| "`byte[0]` has no elements, so its size is 0." | False: an array object still has overhead. |
| "`Object[100]` contains 100 child objects." | False: it only allocates 100 reference slots, defaulting to null. |
| "`getObjectSize(list)` includes all list elements." | False: it usually only measures the shallow wrapper object; the backing array and elements are separate. |
| "The larger `String.length()` is, the more String's shallow size necessarily increases." | No; the backing representation may reside in another object. |
| "`getObjectSize(null)` returns 0." | False: it throws `NullPointerException`. |
| "Measuring `Integer.valueOf(1)` is measuring a primitive int." | False: you are measuring a wrapper object. |
| "Seeing Object[100] go from 416 to 816 means there is a leak." | It could just be compressed oops being disabled; it says nothing about object count or retained heap. |
| "You must enable `Can-Retransform-Classes` to use `getObjectSize`." | No: transform/redefine capabilities are separate from shallow measurement. |
| "Measurements from HotSpot today are constants for future HotSpot versions." | The API does not promise that. |
| "`ByteBuffer.allocateDirect` has its native storage measured by `getObjectSize`." | Do not assume this; the wrapper is not the entire off-heap allocation. |
| "Summing across every field reference does not double-count." | False when there are shared objects or cycles. |
| "The sum of shallow estimates equals RSS." | No: RSS includes regions outside the heap. |
| "Calling `System.gc()` and taking the heap delta gives the exact size." | No: GC is not an isolated per-object measurement. |
| "Changing alignment must change the size of every object." | No: a layout that is already a multiple of the new alignment may not change. |
| "The numbers 16/416/8208 in the example are mandatory output for all Java 17." | No: those numbers belong to the experimental JVM/configuration. |

### Steps to Check When Your Stdout Differs from the Example

First check `java -version` and the VM vendor, then layout/heap flags, the JAR manifest, the right classpath, and the app version. Confirm that you are passing the right **object** (Holder vs. array), the right array length, and actually running with `-javaagent`. If the goal is to measure retained memory or native memory, switch to an appropriate tool instead of trying to tweak code to produce a number "matching the example."

## 12. Knowledge Self-Check

**Question 1.** Holder contains a reference to `byte[8192]`. Must `getObjectSize(holder)` add the 8192 bytes of array data?

**Answer:** No. Holder and the array are two separate objects. Measuring Holder only gives Holder's shallow estimate; you can call `getObjectSize(array)` separately if you need the array's shallow estimate.

**Question 2.** With the same Java code, `Object[100]` is measured as 416 bytes in JVM A and 816 bytes in JVM B. Can you conclude that one JVM is wrong?

**Answer:** No. Different VMs/configurations, such as compressed oops, can make reference slot widths differ. The API allows an implementation-specific approximation.

**Question 3.** Why can `byte[0]` occupy non-zero storage?

**Answer:** Because it is a real array object; it must store overhead/header and possibly padding. Having no elements only means the element payload is 0.

**Question 4.** What does `getObjectSize(null)` return?

**Answer:** It does not return a size: it throws `NullPointerException` per the API.

**Question 5.** Does having two `ArrayList` instances with equal shallow estimates prove that the total heap of the two lists is equal?

**Answer:** No. Their backing arrays and element objects can differ greatly; referents are not automatically added.

**Question 6.** If two Holders hold the same array and the first Holder is dropped, must the retained size of the first Holder include the array?

**Answer:** No. The array is still kept alive by the second Holder; retained size depends on the graph/GC roots.

**Question 7.** Can you hard-code `Holder = 16 bytes` for all Java 17 JVMs?

**Answer:** No. The 16-byte value in the lesson belongs to a specific JVM; Java SE does not guarantee header/alignment/reference width.

**Question 8.** When using `-XX:-UseCompressedOops`, must every object increase in bytes by the same ratio?

**Answer:** No. Objects containing many reference slots can change noticeably, whereas primitive arrays may remain unchanged in the tested configuration.

**Question 9.** To investigate a memory leak, is calling `getObjectSize(suspectedObject)` alone sufficient?

**Answer:** No. You need object counts, allocation rate, reachability, GC roots, and potentially retained size via heap dumps/profilers.

**Question 10.** Does an agent need the manifest entry `Can-Redefine-Classes: true` to measure with `getObjectSize`?

**Answer:** No. The basic requirement is having the `Instrumentation` object provided by the JVM; the redefine flag is for replacing definitions of loaded classes.

## 13. Summary and Official Documentation

**Five most important principles:**

1. **`getObjectSize(Object)` only returns an implementation-specific approximation**, which may include object overhead and vary by JVM/configuration, even within a single invocation.
2. **Measure the exact object passed in**, usually shallow storage; it does not recursively count arrays/collections/graphs referenced by the object.
3. **Headers, compressed references, and alignment affect byte counts.** Do not treat example tables as a universal Java formula.
4. **`null` throws `NullPointerException`**; primitive boxing, static fields, backing arrays, and native memory easily cause interpretation errors.
5. When you need **retained heap, allocation hotspots, GC roots, or native memory**, use heap dumps, profilers, JFR, JOL, or appropriate native tools rather than renaming a shallow estimate as total memory.

References:

- [Java SE 17 API — `Instrumentation.getObjectSize(Object)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#getObjectSize(java.lang.Object))
- [Java SE 17 API — `java.lang.instrument` and Java agent manifest](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [JVMTI — GetObjectSize, implementation-specific approximation](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html#GetObjectSize)
- [Java SE 17 HotSpot Performance Enhancements — compressed ordinary object pointers](https://docs.oracle.com/en/java/javase/17/vm/java-hotspot-virtual-machine-performance-enhancements.html)
- [OpenJDK JOL — Java Object Layout](https://openjdk.org/projects/code-tools/jol/)
- [JFR — Java Flight Recorder](https://openjdk.org/jeps/328)
