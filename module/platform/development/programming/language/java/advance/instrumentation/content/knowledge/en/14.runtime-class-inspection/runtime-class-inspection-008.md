# Comparing Sizes Under the Same Configuration Without Treating Measurements as Java Constants

During the inspection of a running Java application, we can use `Instrumentation.getObjectSize(Object)` to estimate the size of an object. For example, a measurement might show that `byte[1024]` is larger than `byte[32]`, or that two `Holder` objects containing references to arrays of different lengths have the same *shallow* size.

**The key is how to interpret it**: the returned value is an **implementation- and JVM-state-dependent approximation**, suitable for controlled comparisons within the same environment. It is not a `sizeof` specified by the Java language, nor is it the size of the entire object graph or the amount of memory actually allocated by the operating system to the process.

## 1. What should you be able to answer after this lesson?

- What input does `Instrumentation.getObjectSize` take, what does it return, and why must a Java agent be used to obtain `Instrumentation`?
- Why should objects be compared **within the same JVM configuration**, rather than recording a byte count as the “standard size” of a Java data type?
- How do *shallow size*, *reachable size*, *retained size*, and off-heap memory differ?
- Why can a `Holder` referencing a large array have the same shallow size as a `Holder` referencing a small array?
- Which factors must be kept fixed and which facts must be recorded for comparison results to be meaningful?

This lesson belongs to the **Runtime Inspection** section of Java Instrumentation. The focus is on measurements of **live** objects, not measuring `.class` bytecode, JAR size, or programming a Java agent to alter method behavior.

## 2. The practical contract of `getObjectSize`

The `java.lang.instrument.Instrumentation` interface defines:

```java
long getObjectSize(Object objectToSize);
```

According to the [Java 21 Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#getObjectSize(java.lang.Object)), this is an **implementation-specific approximation** of the amount of storage consumed by the object. The value may include some or all of the object's overhead. The documentation explicitly states that the measurement is useful for **comparison within a single implementation**, not for drawing equivalence conclusions across implementations; even **the approximation may change during a single invocation of the JVM**.

Consequences:

1. There is no language rule such as “every `Object` always occupies 16 bytes”, “every reference is always 4 bytes”, or “`String` always occupies 24 bytes”.
2. A JVM may return different numbers when changing versions, architectures, flags related to object alignment/compressed references, object layout, or implementation choices.
3. Even within the same process, the result is an **estimate at the time of invocation**; a previous number should not be treated as a fixed constant for all objects of the same class or at all times.
4. The value is returned for a **specific object**. It does not automatically represent the class, all instances of the same type, the memory held by referenced objects, or the JVM's heap consumption.
5. Passing `null` throws a `NullPointerException`. To call this API, the application needs an `Instrumentation` object provided by the JVM to an agent via `premain` or `agentmain`; `new Instrumentation()` does not exist.

Many popular JVMs express these measurements in bytes and people commonly call them “shallow bytes”, but **do not infer backward from a byte count to a layout constant guaranteed by the Java Language Specification**.

## 3. Measuring the right thing you want to compare

### 3.1. Shallow size of an object

*Shallow size* is the amount of memory of the object/array itself under consideration, as estimated by the JVM. For an object with a reference field, it counts the storage for **that reference inside the object**, rather than following the reference to add the object on the other side. For an array, the measurement includes the array itself and its element storage according to the implementation, but an `Object[]` contains *reference slots*, not all the objects that its elements point to.

Example:

```java
final class Holder {
    final byte[] data;

    Holder(int length) {
        data = new byte[length];
    }
}
```

Both `new Holder(32)` and `new Holder(1024)` have **one `data` reference field**. In a typical HotSpot configuration, the shallow sizes of the two `Holder` objects can be equal; the significant difference lies in the **two separate `byte[]`** arrays they reference.

```text
Holder(32)  ──data──> byte[32]
   └─ part of Holder     └─ separate array

Holder(1024)──data──> byte[1024]
   └─ part of Holder     └─ separate array
```

Therefore, concluding that “Holder 1024 consumes no extra RAM” is wrong. A shallow measurement only speaks about the `Holder` part itself.

### 3.2. Reachable size, retained size, and off-heap resources

| Concept | What part does it measure? | Does `getObjectSize` provide it directly? |
| --- | --- | --- |
| **Shallow size** | A single object/array itself | Yes, as a JVM-dependent approximation |
| **Reachable object graph** | Objects reachable via references from a root | No; estimating requires graph traversal, cycle detection, and avoiding double counting |
| **Retained size** | The amount of memory that would be freed if that object/root no longer kept other objects alive, according to actual retention relationships | No; typically requires heap graph and dominator analysis |
| **Used heap** | Total heap space currently in use at a point in time | No; heap/GC APIs and observability tools have different semantics |
| **Off-heap/native memory** | Memory outside the Java object heap, such as direct buffers/native allocations | No; the Java wrapper itself only reflects the wrapper object |

One should not naively compute “deep size = shallow object + shallow of all referenced objects” when there are reference cycles, sharing, interned objects, or multiple roots holding the same object. And *reachable size* is not synonymous with *retained size*: an object may be referenced from multiple places, so removing one reference does not necessarily free that object.

### 3.3. Class size, object size, allocation, and file size are four different questions

- The size of a `Foo.class` file is the number of bytecode/metadata bytes in the file, not the shallow size of `new Foo()`.
- `getObjectSize(Foo.class)` measures the corresponding `java.lang.Class` object according to the JVM, **not** the size of every `Foo` instance, nor all Metaspace metadata.
- The total number of bytes **allocated across multiple object creations** is an allocation measurement; it does not mean the size of a single existing object.
- A process's resident memory also includes code cache, stacks, native allocations, VM data, and factors beyond shallow size.

## 4. Keeping the same configuration: the foundation of a meaningful comparison

It is necessary to clearly identify **how object A and object B differ**. A minimal experiment should hold the following fixed:

| Factor | How to control |
| --- | --- |
| JVM implementation/vendor and release | Run A and B **in the same process**; record `java.vm.name`, `java.vm.version`, `java.version` |
| Architecture and reference representation | Keep the same architecture, compressed pointers, object alignment, and affecting JVM options |
| Object type | Compare the same type or intentionally measure type/shape differences; do not mix “shallow array” with “deep object graph” |
| Varied parameter | For example, vary only **array length** or only field count; record it accurately |
| Object creation path | Create objects using the same program and allocation path; keep references to them while measuring |
| Measurement method | Use the same `Instrumentation.getObjectSize`, same unit, and same evaluation point |
| Interpretation | Record results as observations on a specific environment, not as a Java rule |

Prefer **measuring both alternatives in a single running JVM**, because then at least the startup settings are kept identical. However, as the Javadoc emphasizes, **even the same JVM does not turn the result into an immutable constant**. If taking multiple measurements, record the observed range rather than assuming the measurement is always stable; if unexpected variation appears, investigate the cause instead of quietly taking a single measurement as truth.

Do not “normalize” a result for another machine by guessing header, reference, or alignment sizes. If you want to compare **two different JVM configurations**, frame that question as a separate experiment and report each environment separately; do not use one environment's numbers as Java's definition.

### Comparing differences and ratios

With the same measurement method and context, you can compute:

```text
delta(A, B) = shallowSize(B) - shallowSize(A)
ratio(A, B) = shallowSize(B) / shallowSize(A), if A is non-zero
```

For example: to know how many more shallow bytes a longer array consumes compared to a shorter array **on the JVM in use**, `delta(byte[32], byte[1024])` is more useful than saying “a byte array always has an X-byte header”. Even so, ratio/delta are still **observations on that implementation**, not universal guarantees. For very small differences, avoid overstating conclusions about the overall impact on the program.

## 5. Runnable Java 17+ example: an agent measuring related objects

The following example runs without third-party libraries. A startup agent obtains `Instrumentation` and provides a shallow size measurement API; the application creates a group of objects in the **same run**, then prints the measurements and differences. No ASM, bytecode transformer, or retransformation is used because the goal here is **size inspection**.

Structure:

```text
size-comparison/
├── agent.mf
├── src/
│   ├── SizeAgent.java
│   └── SizeComparison.java
└── out/                  # created when javac compiles
```

### 5.1. `SizeAgent.java`

File `src/SizeAgent.java`:

```java
import java.lang.instrument.Instrumentation;

public final class SizeAgent {
    private static volatile Instrumentation instrumentation;

    private SizeAgent() {}

    public static void premain(String arguments, Instrumentation inst) {
        instrumentation = inst;
    }

    public static long shallowBytes(Object value) {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Run with -javaagent:size-demo.jar");
        }
        return inst.getObjectSize(value);
    }
}
```

Here:

- The JVM invokes `premain(String, Instrumentation)` before `main` if `-javaagent` is supplied with a valid manifest; that is where the agent receives the `Instrumentation` object.
- `volatile` ensures publication of the `Instrumentation` reference in the example if other threads also use the measurement method. In a single-threaded program, this is a safe and straightforward choice.
- `shallowBytes` measures **only the passed object**. It does not recurse through fields.
- If the application is run without `-javaagent`, the method throws a meaningful error instead of a confusing `NullPointerException`. The underlying API still throws `NullPointerException` if `null` is passed to `getObjectSize`.

### 5.2. `SizeComparison.java`

File `src/SizeComparison.java`:

```java
public final class SizeComparison {
    static final class Holder {
        final byte[] data;

        Holder(int length) {
            data = new byte[length];
        }
    }

    private static void display(String name, Object object) {
        System.out.printf("%-18s %6d bytes%n", name,
                SizeAgent.shallowBytes(object));
    }

    public static void main(String[] args) {
        byte[] shortArray = new byte[32];
        byte[] longArray = new byte[1024];
        Object[] fewRefs = new Object[4];
        Object[] manyRefs = new Object[128];
        Holder smallHolder = new Holder(32);
        Holder largeHolder = new Holder(1024);

        System.out.println("Java=" + System.getProperty("java.version"));
        System.out.println("VM=" + System.getProperty("java.vm.name"));
        display("new Object()", new Object());
        display("byte[32]", shortArray);
        display("byte[1024]", longArray);
        display("Object[4]", fewRefs);
        display("Object[128]", manyRefs);
        display("Holder(32)", smallHolder);
        display("Holder(1024)", largeHolder);

        long arrayDelta = SizeAgent.shallowBytes(longArray)
                - SizeAgent.shallowBytes(shortArray);
        long holderDelta = SizeAgent.shallowBytes(largeHolder)
                - SizeAgent.shallowBytes(smallHolder);
        System.out.println("array delta=" + arrayDelta + " bytes");
        System.out.println("holder delta=" + holderDelta + " bytes");
        System.out.println("holder payload measured separately: "
                + SizeAgent.shallowBytes(largeHolder.data) + " bytes");
    }
}
```

There are three pairs of observations:

1. **`byte[32]` and `byte[1024]`**: same array type, differing only in length. An array's shallow size includes its element data region, so it typically grows with length.
2. **`Object[4]` and `Object[128]`**: the array stores more *reference slots*. Keeping all elements `null` in the example helps focus on the size of the array itself.
3. **`Holder(32)` and `Holder(1024)`**: each Holder stores only one reference to a `byte[]`, so measuring `Holder` does not directly reveal the size of the array it points to.

### 5.3. Manifest and run commands

The `agent.mf` file contains the following content; there is a **trailing blank line** after the attribute:

```text
Manifest-Version: 1.0
Premain-Class: SizeAgent

```

In the `size-comparison` directory, create `out`:

```bash
mkdir -p out
```

On PowerShell, you can create `out` with:

```powershell
New-Item -ItemType Directory -Force out | Out-Null
```

Compile and package using JDK 17 or later:

```bash
javac --release 17 -encoding UTF-8 -d out src/SizeAgent.java src/SizeComparison.java
jar --create --file size-demo.jar --manifest agent.mf -C out .
java -javaagent:size-demo.jar -cp size-demo.jar SizeComparison
```

The `jar` above contains both the agent and application classes to keep the example compact; production typically separates the agent JAR and application artifact. `Can-Retransform-Classes` is not required because the example only uses `getObjectSize`.

### 5.4. An actual output and how to read it

This is **observed output** when compiled with `--release 17` and run on **OpenJDK 21.0.12.1, 64-bit Server VM, in a specific default configuration**:

```text
Java=21.0.12.1
VM=OpenJDK 64-Bit Server VM
new Object()           16 bytes
byte[32]               48 bytes
byte[1024]           1040 bytes
Object[4]              32 bytes
Object[128]           528 bytes
Holder(32)             16 bytes
Holder(1024)           16 bytes
array delta=992 bytes
holder delta=0 bytes
holder payload measured separately: 1040 bytes
```

**The numbers in the output are observations specific to that run**, not invariant stdout guaranteed by the Java specification. Running on a different JDK/JVM, or even the same version with different flags/layout, may yield different numbers. Observe the actual numbers printed by the command and interpret them strictly in context.

In the example run:

- `byte[1024]` is **992 bytes** larger than `byte[32]` **according to this VM's estimate**. Because the lengths differ by 992 `byte` elements, the result matches the array layout at that time. One must not conclude from this that Java specifies a fixed array header size.
- `Object[128]` is **496 bytes** larger than `Object[4]` in this measurement. We can use the result to study reference storage cost, but do not turn `496 / 124` into a definition that Java references are always 4 bytes long.
- Both `Holder` instances report **16 shallow bytes**. This does not prove they have the same total footprint: `largeHolder.data` alone is measured at **1040 bytes**. An object graph may contain many other objects outside the shallow result.

If using these numbers to estimate millions of objects in practice, one must account for how objects are created, the number of live instances, padding, shared references, off-heap memory, GC, and storage structure overhead. Multiplying “16 bytes × object count” is a very limited guess, **not a report of consumed heap**.

## 6. Mechanism analysis: why can observed sizes differ?

Java specifies object and field semantics, **not a fixed byte-level layout** for all JVMs.

An implementation may store:

- **Object header**: information needed for object management/metadata/locking/GC, structured according to the JVM.
- **Instance fields**: primitive fields or reference fields; the implementation may reorder, round, or pad them according to its own rules.
- **Array metadata**: array length information plus the element region; alignment may be required.
- **Alignment/padding**: empty space rounding the footprint to layout boundaries.
- **Reference encoding**: environments with or without compressed ordinary object pointers, compressed class pointers, or other mechanisms; *reference slot* size and related layout may differ.

These factors are **implementation-conditional** explanations, not a contract that every HotSpot/JVM always has the same byte counts at all times.

### Why is “the same configuration” still not a constant?

The Javadoc allows the estimate to change even within a single JVM invocation. The API does not promise that two calls on the same object will always return an invariant value. Therefore, a careful way to state it is:

> On JVM run X with options Y, `getObjectSize` reported A bytes for object P and B bytes for object Q. The measurements allow relative comparison at the time of inspection; they must be re-verified when conditions change.

Do not write:

> Java specifies that `new Object()` is 16 bytes and a single-field `Holder` is 16 bytes.

Even when multiple observations match, repetition only strengthens the conclusion **within the measured environment**, rather than turning the number into language semantics.

## 7. Three practical application scenarios

### 7.1. Increasing cache capacity: thin objects with large inner data

A cache entry has a reference field pointing to a `byte[]`. If you only call `getObjectSize(entry)`, the result may remain nearly unchanged when increasing the payload size. To investigate, measure `entry`, the payload array, and related wrappers separately; when total actual footprint is needed, use heap profiling or an appropriate graph traversal method.

**Permitted conclusion:** the wrapper's shallow size may be insensitive to the payload capacity.

**Disallowed conclusion:** increasing the payload does not increase memory usage.

### 7.2. `ArrayList` growing in element count

`new ArrayList<>(10)` has a list object and typically a separate element storage structure depending on the implementation. `getObjectSize(list)` does not measure the entire backing array or the elements. For a list with 10 elements pointing to a single object, 10 references do not mean 10 independent objects.

To evaluate the cost of a list, one must consider:
- the shallow size of the list object;
- the shallow size of the backing storage if accessible via appropriate tools;
- the number of reference slots;
- the identity and actual count of referenced objects;
- whether objects are shared across multiple structures.

Do not arbitrarily use reflection on JDK private fields just to get shallow sizes: JPMS imposes module/opens restrictions, and implementations can change.

### 7.3. `String` and direct memory

For `String`, the shallow size of the object itself **does not directly reflect** the entire storage for character contents. Different JDK versions may choose different content representations; data sharing and the intern pool also affect graph footprint.

For `ByteBuffer.allocateDirect(...)`, a Java wrapper may reference a native/off-heap region. The wrapper's shallow size **does not include** the native capacity allocated by the JVM/allocator for the buffer. Use Native Memory Tracking or an appropriate observability tool if the question is about native memory.

## 8. Designing a reproducible inspection table

When comparing a group of objects, record them using a structure like the following:

| Field | Meaning |
| --- | --- |
| Time/program | Run timestamp and commit/build of the measurement code |
| JVM/Java/architecture | Vendor, VM name/version, `java.version`, architecture |
| Relevant JVM options | Heap, compressed references, alignment, GC if affecting the target |
| Object | Actual type and initialization; length/capacity/field values |
| Measurement scope | **Shallow object** or another measurement |
| Observed size | Value returned by `getObjectSize`; consistent unit |
| Control object | Same type/creation path or clearly explained difference |
| Delta/ratio | Comparison within the same run or controlled measurement set |
| Limitations | Excludes referents, retained size, off-heap; variation possible |

Example report for the run shown earlier:

| Object A | Object B | A (bytes) | B (bytes) | Delta B − A | Accurate statement |
| --- | --- | ---: | ---: | ---: | --- |
| `byte[32]` | `byte[1024]` | 48 | 1040 | +992 | The longer array measured larger on this VM |
| `Object[4]` | `Object[128]` | 32 | 528 | +496 | More reference slots were counted into the array's shallow size |
| `Holder(32)` | `Holder(1024)` | 16 | 16 | 0 | The shallow sizes of the two wrappers were equal in the measurement |
| `Holder(1024)` | `Holder(1024).data` | 16 | 1040 | Not meaningful as “growth” | The two measurements belong to **two different object types**, not an A/B comparison of the same factor |

The last row of the table compares **the wrapper** and **the referenced array**, solely to illustrate the boundary of shallow size. Do not use that difference as the growth of a single object.

### Avoiding invalid statistical inferences

If the goal is footprint inspection, varying multiple samples (lengths, class shapes, JVM flags) helps find patterns in a specific system. However, do not:
- treat `getObjectSize` as a timer and run a “warmup benchmark” to infer throughput metrics;
- pick a sample with a few bytes' difference, without inspecting layout, and conclude application-wide heap optimization;
- round results to hide differences caused by object alignment;
- average numbers from different JVMs into a meaningless mean;
- assume every instance of a class has an invariant measurement over time, despite the API's warning.

## 9. Comparing measurement methods: choosing the right tool for the question

| Question being asked | Appropriate tool or method | Limitations |
| --- | --- | --- |
| What is this object's estimated shallow footprint? | `Instrumentation.getObjectSize` | Implementation-specific, does not measure the whole graph |
| What is the field/header/alignment layout on this HotSpot? | OpenJDK JOL (Java Object Layout) | Describes the inspected implementation and runtime |
| Who is keeping large objects alive and what is the retained size? | Heap dump + memory profiler/dominator tree | Heap snapshot, has collection/analysis overhead |
| Where in the code is the application allocating many objects? | Allocation profiling/appropriate JFR events | Measures allocation stream, different from live heap inventory |
| Why is native/off-heap memory growing? | Native Memory Tracking/JFR/appropriate native tools | Cannot be inferred from wrapper shallow size |
| How much heap is the JVM currently using? | MXBeans/JFR/GC metrics or profiling | Used heap is not the sum of `getObjectSize` of a few objects |

**Do not try to use one API to answer every memory question.** Each measurement has a different scope. In quick inspection with Instrumentation, a reasonable goal is to distinguish **layout/object candidates** in the running environment, and from there decide whether a heap dump or detailed profiler is needed.

## 10. Common mistakes and fixes

1. **Forgetting `-javaagent` when calling `SizeAgent.shallowBytes`:** the application was not passed `Instrumentation` by the JVM. Run with the proper agent JAR/manifest before calling `getObjectSize`.
2. **Interpreting `getObjectSize(holder)` as the total size of all reachable objects:** measure the referenced objects as well or switch to a heap graph analysis tool.
3. **Copying sample output into documentation as “Java Object = 16 bytes”:** include JVM/version/options and measurement scope; do not call it a constant.
4. **Comparing two applications with different JDK/JVM/flags and concluding class A is better than class B:** first bring the measurements into the same environment or design a separate cross-configuration experiment; do not use raw numbers as a language standard.
5. **Assuming `Object[128]` already contains 128 objects:** a newly created array has 128 reference slots, with elements initially `null`; any referenced objects, if present, are separate allocations.
6. **Confusing allocated bytes with live bytes:** many objects may already have been reclaimed by GC; `getObjectSize` only inspects an object that still has a reference at the time of invocation.
7. **Summing a graph via DFS without deduplication:** cycles or shared references cause overcounting; retained size also has its own semantics.
8. **Confusing `getObjectSize(SomeClass.class)` with instance size:** the argument there is the `java.lang.Class` object, not an instance of `SomeClass`.
9. **Treating a measurement as invariant within a JVM run:** the specification allows the estimated value to change; when accurate comparison is needed, save the data from that measurement run instead of relying on a “default” number.
10. **Using `getObjectSize` on a direct buffer to infer native payload:** it only sees the Java object wrapper; the native part must be measured with the right tool.

## 11. Practice exercises

1. In the same run, add `byte[0]`, `byte[1]`, `byte[7]`, `byte[8]`, and `byte[9]` to the experiment. Tabulate the observed sizes; are any values equal? Relate this to alignment and emphasize that this is an observation on your VM.
2. Replace `Holder` with a class having two references: `byte[] a` and `Object label`. Compare the shallow sizes of two instances differing only in the length of `a`, then measure `a` separately.
3. Add `int[32]` and `long[32]`. Explain the difference by element type in your JVM; do not generalize it into a constant for all implementations.
4. Try an `Object[]` with 128 `null` slots and an `Object[]` of the same length where all slots point to a single object. How does the array's shallow size change? Why does the actual number of reachable objects differ?
5. Re-run under a different controlled JVM configuration (if the JVM supports the required flags). Report the two environments separately, stating clearly when the data is only comparable within each group.
6. Explain why JFR allocation events or a heap dump may still be necessary even after you have measured the shallow size of a `Map.Entry`.

## 12. Key takeaways

- `Instrumentation.getObjectSize` measures **a specific object** and returns an **implementation-dependent approximation**; the measurement may change even within a single JVM invocation.
- The best comparison is **within the same JVM/configuration**, varying only one factor and recording the measurement conditions, delta, and object scope.
- **Shallow size is not deep/reachable/retained size**, nor does it directly measure off-heap memory, total heap, or `.class` file size.
- The result “`Holder(32)` equals `Holder(1024)`” only indicates that the two **wrappers** themselves had equal shallow sizes in that measurement; their payloads can still differ enormously.
- Use numbers as **inspection evidence** for a specific environment, not as “size constants guaranteed by Java”.

## 13. Official documentation and related tools

- [Oracle Java SE 21 — `Instrumentation.getObjectSize`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#getObjectSize(java.lang.Object)): the “implementation-specific approximation” contract and the possibility of change within the same JVM.
- [Oracle Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): API compatible with the Java 17 example.
- [Oracle Java SE 21 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): `Premain-Class` manifest, startup agents, and how the JVM passes `Instrumentation`.
- [OpenJDK — Java Object Layout (JOL)](https://github.com/openjdk/jol): a tool for studying JVM-specific object layout/footprint, complementary when inspecting headers, padding, and reference layout.
