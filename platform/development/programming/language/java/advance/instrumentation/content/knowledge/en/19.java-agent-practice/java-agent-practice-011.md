# Comparing getObjectSize of Objects Under the Same JVM Configuration

**Context:** Java Advance → instrumentation → **Agent practice**.

`Instrumentation.getObjectSize(Object)` is a useful method in the Java Instrumentation API for **estimating how much memory a specific object occupies under the current JVM's object layout implementation**. It is well suited for an experiment comparing **objects of different types, field structures, and array lengths within the same JVM configuration**. However, it is not a measurement of “how much heap an object graph occupies” or a standard function that returns an exact, invariant byte size across all machines.

The Oracle JDK 17 Javadoc describes `getObjectSize` as an **implementation-specific approximation**, useful only for comparisons **within the same implementation**, which may include some or all of the object's overhead; **the estimate may change even within a single JVM invocation**. The API also specifies that a `null` argument throws `NullPointerException`. This limitation must be noted in any report before reading any numbers.

This practice lab will:

1. Create a **minimal Java startup agent** via `-javaagent` to receive `Instrumentation` in `premain`.
2. Write a **Java 17+ application runnable with `javac`/`jar`/`java`**, using the same JVM to measure a set of sample objects.
3. Compare empty objects, objects with primitive fields, reference fields, records, primitive arrays, reference arrays, strings, and objects with reference graphs.
4. Distinguish an object's **shallow size** from a graph's **deep/reachable/retained heap size**.
5. Establish rules for keeping runtime/JVM flags fixed, checking compressed references, alignment, and object/array headers.
6. Explain how to read stdout containing machine-dependent sizes **without inventing fixed byte counts**.
7. Diagnose agent configuration errors, identify invalid comparisons, and know when **JOL, JFR, heap dumps, or profilers** are needed instead of `getObjectSize`.

> **Guiding conclusion:** Use `getObjectSize` as **an approximate measurement for a single object in a specific JVM**, not as a tool to compute the total size of everything the object references, not as the number of bytes allocated by a request, and not as a quantity for absolute comparison across all JDKs/GCs/architectures.

## 1. Understanding the Exact Name and API Contract

Standard signature:

```java
// API fragment, not a standalone Java class.
long getObjectSize(Object objectToSize);
```

Package: `java.lang.instrument`, interface `Instrumentation`, located in module `java.instrument`. A normal Java program **cannot instantiate `Instrumentation` on its own**. The JVM provides it to an agent via:

```java
// Fragment: belongs to the class specified by Premain-Class in the agent JAR.
public static void premain(
        String agentArgs, Instrumentation instrumentation) {
    // Store the handle if needed; control lifecycle and access.
}
```

Distinctions to keep clear:

| Term | Does `getObjectSize` measure this? |
| --- | --- |
| A **specific object instance** | Yes: returns an estimated `long` byte count, VM-dependent |
| A specific `byte[]` or `Object[]` array | Yes: arrays are objects too; primitive elements are stored inline, reference slots are part of the array |
| The entire object graph reachable from a root | **Does not automatically** traverse referenced objects |
| All String characters + backing storage | **Does not automatically** add the backing storage behind the reference field |
| Total bytes allocated during a method's execution | **No**, that is an allocation metric, not the size of a single object |
| Retained heap if the object is reclaimed by GC | **No**, requires dominator/retained heap analysis from a heap snapshot |
| Process RSS / native memory / metaspace footprint | **No** |
| Exact portable object header/field layout | **No**; returns only a total byte estimate |
| Object address or raw object memory | **No** |
| A `null` argument | **Does not return 0**; the API throws `NullPointerException` |

### 1.1. What does “Shallow” mean in common usage?

Example:

```text
ReferenceBox
  └── Object value ──────────────► byte[4096]
        (reference slot)            (separate object)

getObjectSize(referenceBox):
  typically reflects the memory of ReferenceBox itself
  (header, reference field, padding per implementation)

getObjectSize(value):
  measures the byte[4096] object separately
```

On common JVMs like HotSpot, `getObjectSize(box)` **does not recursively traverse** to `byte[4096]`. If you only change the array size without changing the class/layout of `ReferenceBox`, the shallow estimates of the two boxes are usually the same. **That is an observation about the layout of the runtime under test, not a guarantee of invariant byte results from the Java SE specification.**

Do not confuse this with C/C++-style `sizeof` for a class. Java allows the VM to reorder, compress, and align layouts; the same source code can yield different sizes on 64-bit HotSpot versus another JVM/architecture.

### 1.2. What does the Javadoc warn about?

Limitations that must be stated accurately:

- **Implementation-specific approximation:** not an absolute size defined by the Java language.
- **May include some or all overhead:** headers and alignment have no fixed contract.
- **Useful only for comparison within the same implementation:** different JVMs/vendors/flags cannot be reduced to a single universal “law”.
- **May change within the same JVM invocation:** two calls on the same object are not required to always return the exact same byte count.
- **`null` throws `NullPointerException`:** do not use 0 as a substitute value for null.

For the goal of “comparing within the same JVM configuration”, we will **record the configuration explicitly**, measure objects within **a single process**, and avoid hardcoding expected sizes from folklore such as “Object is always 16 bytes”.

## 2. What Determines Object Size on the JVM?

Depending on the JVM, a Java object's memory may involve:

- **Object header:** runtime metadata such as identity/hash/lock/klass metadata; the exact representation is an implementation detail.
- **Instance fields:** primitive data and reference slots according to types and the field layout chosen by the JVM.
- **Array header/length:** arrays have a length and elements stored according to the array layout mechanism.
- **Alignment/padding:** the JVM may align objects to 8-byte, 16-byte, or other boundaries; padding bytes do not correspond to any Java field.
- **Compressed references:** on many 64-bit HotSpot configurations, reference slots can be compressed; the result is not simply `8 × number of reference fields`.
- **Architecture/JDK/GC/VM options:** implementation, runtime version, heap settings, alignment, and compressed class pointers can all change the value.

**This is not a portable formula where you simply sum field sizes.** The JDK may lay out fields in a different order from the source, with padding, inherited fields, and layout details not visible through standard reflection.

### 2.1. Comparing an empty object and objects with multiple fields

An object with no instance fields **still requires a runtime representation**. Adding an `int` field does not necessarily increase the size estimate by 4 bytes: existing padding is sometimes enough to hold the new field. Adding multiple `long`s or references may push the object past an alignment boundary.

| Type | Why measure it? | What you should **not** conclude |
| --- | --- | --- |
| `new Object()` | Minimal baseline object | “Every object equals that number plus the sum of its field types” |
| Custom empty class | Header, class metadata association | “Longer class names make objects larger” |
| Class with an `int` | Primitive field may fit into padding | “Always exactly 4 bytes larger” |
| Class with two `long`s | Adds category-2 payload | “Always increases by exactly 16 bytes” |
| Class with references | Stores only reference slots in the shallow object | “Automatically includes the pointed-to objects” |
| `record Point(int,int)` | A record is still an object per VM layout | “Records have no object header or are always smaller than classes” |

### 2.2. For arrays, consider element type and length

`byte[64]` holds 64 byte values inline. `long[64]` holds 64 long values inline. `Object[64]` holds 64 **reference slots**, not the 64 referenced objects themselves.

Conceptual model, **not a guaranteed quantitative formula**:

```text
Shallow size of a primitive array ~
  array header + inline element payload + padding

Shallow size of a reference array ~
  array header + reference slots + padding

Does not include the object graph of referenced elements.
```

You should measure different lengths (0, 1, 7, 8, 64, ...) to observe **alignment steps**, rather than assuming size grows linearly byte by byte. On a specific JVM and layout, you may observe equal estimates across several nearby lengths due to padding.

## 3. Experiment Design: Fix the Configuration Before Measuring

A fair comparison should record:

| Property | Example way to obtain | Reason |
| --- | --- | --- |
| JVM vendor/implementation | `java.vm.name`, `java.vendor` | Object layout is an implementation detail |
| Java runtime version | `java.runtime.version`, `java -version` | Version may change headers/layout |
| OS and CPU architecture | `os.name`, `os.arch` | Pointer width/ABI may differ |
| Heap settings | `-Xms`, `-Xmx` | HotSpot ergonomics and compressed references may depend on heap size |
| `UseCompressedOops` | HotSpot `PrintFlagsFinal` | Compresses ordinary object pointers |
| `UseCompressedClassPointers` | HotSpot `PrintFlagsFinal` | Layout of class metadata references |
| `ObjectAlignmentInBytes` | HotSpot `PrintFlagsFinal` | Object size alignment |
| GC implementation | JVM flags and VM logs | Runtime layout/overhead policies may differ |
| Agent set | Full command line | Other agents may affect setup/objects |
| Container memory/CPU | Runtime limits | VM configuration and measurement environment |

In the **main comparison**, use a **single JVM process** for all objects. All measured objects are created directly in `main` after the agent has obtained `Instrumentation`, avoiding “object A from config 1, object B from config 2”.

Do not force JVM flags without knowing whether the vendor supports them. The `-XX:...` examples in later sections are **HotSpot-specific experiments**, not standard Java APIs.

### 3.1. Check the JVM before building

```bash
java -version
javac -version
jar --help
```

On HotSpot JDK 17 with Bash/Linux, you can inspect the relevant options:

```bash
java -XX:+PrintFlagsFinal -version 2>&1 \
  | grep -E 'UseCompressedOops|UseCompressedClassPointers|ObjectAlignmentInBytes'
```

On PowerShell:

```powershell
java -XX:+PrintFlagsFinal -version 2>&1 | Select-String 'UseCompressedOops|UseCompressedClassPointers|ObjectAlignmentInBytes'
```

`PrintFlagsFinal` can print extensive information in varying formats; use it as **configuration evidence** rather than a fixed byte output. If a VM rejects a flag, omit that flag or switch to a vendor-supported configuration; do not assume a HotSpot flag is portable.

## 4. Java 17+ Project Structure Without External Dependencies

```text
object-size-lab/
├── agent.mf
├── src/
│   └── demo/
│       ├── SizeAgent.java
│       └── CompareSizes.java
├── build/
│   ├── agent/                (created at compile time)
│   └── app/                  (created at compile time)
└── size-agent.jar            (created by jar)
```

Separation goals:

- `SizeAgent.java` is packaged into an agent JAR with `Premain-Class`.
- `CompareSizes.java` is the application, run in the **same process** as the startup agent.
- `CompareSizes` calls the small public static API of `SizeAgent`, so the **agent JAR must also be on the application classpath** in addition to `-javaagent`.
- No native libraries, Maven, ASM, or Byte Buddy.
- Both classes compile with `javac --release 17`.

Create a new empty folder for this lab. There is no need to call `System.gc()` to “stabilize” measurements: a GC request is not guaranteed to run, and the Javadoc allows estimates to change within the same process.

## 5. `SizeAgent.java` Code: Receiving Instrumentation from the JVM

Save at `src/demo/SizeAgent.java`:

```java
package demo;

import java.lang.instrument.Instrumentation;
import java.util.Objects;

public final class SizeAgent {
    private static volatile Instrumentation instrumentation;

    private SizeAgent() {}

    public static void premain(
            String agentArgs, Instrumentation instance) {
        instrumentation = Objects.requireNonNull(instance);
        System.out.println("PREMAIN_ARGS=" + agentArgs);
    }

    public static boolean active() {
        return instrumentation != null;
    }

    public static long sizeOf(Object object) {
        Instrumentation current = instrumentation;
        if (current == null) {
            throw new IllegalStateException(
                    "Start JVM with -javaagent:size-agent.jar");
        }
        return current.getObjectSize(object);
    }
}
```

**Explanation:**

1. The JVM loads the agent from its manifest and invokes `premain` **before the application `main`**.
2. `Instrumentation` cannot be instantiated with `new`; the instance is passed in by the JVM.
3. `volatile` ensures safe reference publication if the app later reads it from another thread. This lab measures from the main thread only, but a real agent may be accessed from multiple threads.
4. `sizeOf(Object)` preserves the API contract: passing `null` through to `getObjectSize` when the agent is active throws `NullPointerException`, **rather than returning 0**.
5. If `-javaagent` is omitted while the JAR is on the classpath, `active()` returns `false`. This distinguishes **“agent class is on the classpath”** from **“the JVM actually started the agent”**.
6. The method does not alter the bytecode or class model of the measured object; it only asks the JVM for an estimate of an existing object.

**Note:** Do not keep `Instrumentation` expecting an ordinary library JAR to call into it when no agent was started. If the JVM was not started with an agent, Java SE provides no general API for an application to obtain an `Instrumentation` handle from arbitrary code.

## 6. `CompareSizes.java` Code: A Diverse but Controlled Sample Set

Save at `src/demo/CompareSizes.java`:

```java
package demo;

import java.util.Arrays;
import java.util.Locale;

public final class CompareSizes {
    private CompareSizes() {}

    static final class Empty {}

    static final class OneInt {
        int value = 7;
    }

    static final class TwoLongs {
        long first = 1L;
        long second = 2L;
    }

    static final class RefBox {
        Object value;

        RefBox(Object value) {
            this.value = value;
        }
    }

    static final class Pair {
        Object left;
        Object right;

        Pair(Object left, Object right) {
            this.left = left;
            this.right = right;
        }
    }

    record Point(int x, int y) {}

    private static void show(String label, Object value) {
        long bytes = SizeAgent.sizeOf(value);
        System.out.printf(
                Locale.ROOT, "SIZE %-23s %d%n", label, bytes);
    }

    public static void main(String[] args) {
        System.out.println("MAIN_BEGIN");
        System.out.println("AGENT_ACTIVE=" + SizeAgent.active());

        if (!SizeAgent.active()) {
            System.out.println("MEASUREMENTS_SKIPPED=true");
            return;
        }

        System.out.println(
                "VM_NAME=" + System.getProperty("java.vm.name"));
        System.out.println(
                "RUNTIME=" + System.getProperty("java.runtime.version"));
        System.out.println(
                "ARCH=" + System.getProperty("os.arch"));

        System.out.println("SECTION=objects");
        show("new Object()", new Object());
        show("Empty", new Empty());
        show("OneInt", new OneInt());
        show("TwoLongs", new TwoLongs());
        show("record Point", new Point(1, 2));

        System.out.println("SECTION=arrays");
        show("byte[0]", new byte[0]);
        show("byte[1]", new byte[1]);
        show("byte[7]", new byte[7]);
        show("byte[8]", new byte[8]);
        show("byte[64]", new byte[64]);
        show("int[0]", new int[0]);
        show("int[8]", new int[8]);
        show("long[8]", new long[8]);
        show("Object[8]", new Object[8]);

        byte[] small = new byte[1];
        byte[] large = new byte[4096];
        RefBox smallBox = new RefBox(small);
        RefBox largeBox = new RefBox(large);

        System.out.println("SECTION=references");
        show("RefBox(small)", smallBox);
        show("RefBox(large)", largeBox);
        show("referent byte[1]", small);
        show("referent byte[4096]", large);

        Object[] none = new Object[8];
        Object[] repeated = new Object[8];
        Arrays.fill(repeated, large);
        show("Object[8] nulls", none);
        show("Object[8] aliases", repeated);
        System.out.println(
                "ARRAY_LENGTH_EQUAL=" + (none.length == repeated.length));

        Pair alias = new Pair(large, large);
        Pair distinct =
                new Pair(new byte[4096], new byte[4096]);
        show("Pair(shared)", alias);
        show("Pair(distinct)", distinct);

        System.out.println(
                "ALIAS_SHARED=" + (alias.left == alias.right));
        System.out.println(
                "DISTINCT_REFERENTS="
                        + (distinct.left != distinct.right));

        System.out.println("SECTION=strings");
        String shortText = new String("a");
        String longText = new String("a".repeat(4096));
        show("String(length=1)", shortText);
        show("String(length=4096)", longText);

        boolean nullThrowsNpe = false;
        try {
            SizeAgent.sizeOf(null);
        } catch (NullPointerException expected) {
            nullThrowsNpe = true;
        }
        if (!nullThrowsNpe) {
            throw new AssertionError("getObjectSize(null) contract");
        }

        System.out.println("NULL_THROWS_NPE=true");
        System.out.println("DONE=true");
    }
}
```

### 6.1. Why does this code run on Java 17?

- `record Point` is a standard feature in Java 16+, so it compiles with `--release 17`.
- `String.repeat(int)` has been available since Java 11.
- `java.lang.instrument` is a standard API.
- `Arrays.fill` and `Locale.ROOT` are built in.
- No reflection into private JDK fields, no `Unsafe`, and no preview features.
- Requires only two source files and an agent JAR with a proper manifest.

### 6.2. Why not assert hardcoded sizes?

The code only prints the numbers returned by the **actual JVM**. We **deliberately avoid writing**:

```java
// Anti-pattern, not a portable assertion.
assert SizeAgent.sizeOf(new Object()) == 16;
```

The number “16” may appear on some HotSpot configurations, but **it is not part of the `Instrumentation.getObjectSize` contract**. Java has object alignment, compressed references, and other implementations; the Javadoc even allows the estimate to change within a single JVM invocation.

What can be asserted portably here is that **`getObjectSize(null)` must throw `NullPointerException`**. All other size comparisons are treated as **observations** paired with the JVM config, rather than turning layout folklore into pass/fail conditions.

### 6.3. Why pre-create objects for measurement?

`RefBox` and `Pair` are created as local variables before calling `show`. This makes it clear **which object is being measured** and **which objects are only referenced**; we do not use `Runtime.totalMemory() - freeMemory()` to infer the size of a single allocation from a heap delta.

`getObjectSize` does not return a Java object's address, field offsets, or graph reachability. If you need detailed layout analysis, use a tool such as OpenJDK **JOL**; if you need retained heap, use a heap analyzer.

## 7. Manifest `agent.mf`

File contents:

```text
Manifest-Version: 1.0
Premain-Class: demo.SizeAgent
```

**End the file with a trailing newline.** `Premain-Class` is a **binary class name** in the form `demo.SizeAgent`, not a path like `demo/SizeAgent.class` and not `SizeAgent.java`.

There is no need to add `Can-Retransform-Classes` or `Can-Redefine-Classes` because the lab only calls `getObjectSize`. `Agent-Class` is not needed because dynamic attach is not used. The agent does not register a transformer and does not touch `classfileBuffer`.

## 8. Compiling and Running on Bash (Linux/macOS)

From the `object-size-lab` root:

```bash
mkdir -p build/agent build/app

javac --release 17 -encoding UTF-8 \
    -d build/agent src/demo/SizeAgent.java

jar --create --file size-agent.jar \
    --manifest agent.mf -C build/agent .

javac --release 17 -encoding UTF-8 \
    -cp size-agent.jar \
    -d build/app src/demo/CompareSizes.java

jar --list --file size-agent.jar
```

Verify the JAR contains at minimum:

```text
META-INF/MANIFEST.MF
demo/SizeAgent.class
```

`jar --list` may print additional directory entries and in a different order; not every output line is hardcoded here.

### 8.1. Baseline: class on classpath without loading the agent

```bash
java -cp "build/app:size-agent.jar" demo.CompareSizes
```

**Exact stdout of the program:**

```text
MAIN_BEGIN
AGENT_ACTIVE=false
MEASUREMENTS_SKIPPED=true
```

Without `-javaagent`, the JVM does not call `premain`, so the `Instrumentation` reference remains `null`. Having `size-agent.jar` on `-cp` **only allows linking the `SizeAgent` class**; it does not make it an active agent.

### 8.2. Measuring with the startup agent

```bash
java -javaagent:size-agent.jar=lab \
    -cp "build/app:size-agent.jar" demo.CompareSizes
```

**Deterministic lines by logic and order**:

```text
PREMAIN_ARGS=lab
MAIN_BEGIN
AGENT_ACTIVE=true
VM_NAME=...                 (value from the running JVM)
RUNTIME=...                 (current runtime version)
ARCH=...                    (actual architecture)
SECTION=objects
SIZE new Object()            ... (measured via getObjectSize)
SIZE Empty                   ... (actual measurement)
SIZE OneInt                  ... (actual measurement)
SIZE TwoLongs                ... (actual measurement)
SIZE record Point            ... (actual measurement)
SECTION=arrays
...                          (SIZE lines for the arrays)
SECTION=references
...                          (SIZE lines for RefBox, Pair, and referents)
ARRAY_LENGTH_EQUAL=true
ALIAS_SHARED=true
DISTINCT_REFERENTS=true
SECTION=strings
...                          (two String SIZE lines)
NULL_THROWS_NPE=true
DONE=true
```

**This is an annotated output structure, not verbatim stdout**: `...` represents the actual numbers returned by the JVM and omitted `SIZE` lines. There is no “standard byte size” to pre-fill for every JVM. Fixed lines such as `PREMAIN_ARGS=lab`, `AGENT_ACTIVE=true`, `ALIAS_SHARED=true`, `NULL_THROWS_NPE=true`, and `DONE=true` come directly from the source code.

### 8.3. Windows PowerShell

```powershell
New-Item -ItemType Directory -Force build/agent,build/app | Out-Null

javac --release 17 -encoding UTF-8 -d build/agent src/demo/SizeAgent.java
jar --create --file size-agent.jar --manifest agent.mf -C build/agent .
javac --release 17 -encoding UTF-8 -cp size-agent.jar -d build/app src/demo/CompareSizes.java

java -cp "build/app;size-agent.jar" demo.CompareSizes
java -javaagent:size-agent.jar=lab -cp "build/app;size-agent.jar" demo.CompareSizes
```

**Classpath separator**: on Unix it is typically a colon `:`; on Windows it is a semicolon `;`. If you copy the Bash command `-cp "build/app:size-agent.jar"` to Windows, the JVM may fail to find the main class. `-javaagent` and `-cp` serve two different purposes; use **both** as configured in this lab.

## 9. How to Interpret the Measured Lines

### 9.1. `new Object()` and `Empty`

Both are Java objects; `Empty` has no instance fields but is not “free”. Within a given runtime, they often have a similar footprint if the layout policy is the same. However, do not claim they must be equal from the specification. If the measurements are equal, that is an **observation in the running configuration**, not proof that all empty classes always occupy the same number of bytes across all JDKs.

### 9.2. `OneInt`, `TwoLongs`, and `Point`

Compare the sizes of an object with one `int`, two `long`s, and a record with two `int`s. Do not add fixed field sizes to `Object`'s size:

```text
Do not assume:
size(OneInt) = size(Object) + 4
size(TwoLongs) = size(Object) + 16
size(Point) = size(Object) + 8
```

The JVM can use padding and reorder fields. What to compare are **the measured values across instances in the same process**. From there, ask: which change crosses an alignment step, and in which case does adding a field leave the estimate unchanged?

### 9.3. `byte[]` with lengths 0, 1, 7, 8, and 64

An array has a header and length even when `length=0`. A primitive `byte[]` stores its elements inline, so when the length increases enough, the shallow size is expected to grow. However, due to alignment, `byte[1]` and `byte[7]` **may** have the same estimate on a HotSpot configuration. Do not impose a rule like “header is always 16 bytes” from the Java language specification.

### 9.4. `int[8]`, `long[8]`, and `Object[8]`

Arrays of the same length do not have the same payload width. In common HotSpot implementations:

- `int[]` holds primitive int elements.
- `long[]` holds primitive long elements, typically with a larger payload than int at the same length.
- `Object[]` holds **reference slots**; their width depends on compressed ordinary object pointers and JVM layout.

Therefore you cannot substitute `size(Object[8]) = 8 × size(Object)`: a reference array **does not store Object instances inline**.

### 9.5. `RefBox(small)` and `RefBox(large)`

`smallBox.value` points to `byte[1]`; `largeBox.value` points to `byte[4096]`. Both boxes are of the same class and each has only **one reference field**; the shallow size of the boxes typically does not depend on the referent's size on HotSpot.

Compare:

```text
getObjectSize(smallBox)       -> RefBox itself
getObjectSize(largeBox)       -> RefBox itself
getObjectSize(small)          -> byte[1]
getObjectSize(large)          -> byte[4096]

Not:
getObjectSize(largeBox) = getObjectSize(RefBox)
                        + getObjectSize(large)
```

This is the clearest illustration of the difference between a **reference slot** and a **referenced object's payload**.

### 9.6. `Object[8] nulls` and `Object[8] aliases`

Both arrays have the same class and length. One array holds eight `null` values, and the other holds eight references **all pointing to the same `large` object**. They contain the same number of slots. Having slots refer to a large object does not make the array **contain** that object.

When computing the reachable memory of an object graph:

- The array instance and the referenced object are **two nodes**.
- Eight references pointing to the same node should be counted **only once** if you want to count unique reachable objects.
- Counting each “reference → object” edge as a new object will **double-count**.

### 9.7. `Pair(shared)` vs `Pair(distinct)`

`Pair(shared)` has two fields referencing **the same byte array**; `Pair(distinct)` has two references to **two independent arrays**. Both `Pair` objects have the same field structure, so their shallow sizes can be identical, even though their reachable object graphs have different cardinalities.

`ALIAS_SHARED=true` and `DISTINCT_REFERENTS=true` are **reference identity checks**, not byte counts. Distinguishing sharing is a prerequisite if you later write a graph traversal tool that avoids double-counting.

### 9.8. `String(length=1)` vs `String(length=4096)`

In Java 17 HotSpot, `String` typically stores character data in a backing `byte[]` (compact strings were introduced in JDK 9). `getObjectSize(String)` **does not automatically add the backing byte array**. Thus, measuring a short `String` and a long `String` can show similar shallow estimates despite a huge difference in character count.

**Do not** use `String.length() × 2` as a `String`'s footprint: the layout may use compact strings, encoding/coder, shared storage, or other VM policies; backing arrays also have headers and alignment. Do not access private `String.value` via reflection + `--add-opens` just to complete this lab; that relies on JDK internals and is not a portable approach.

## 10. Recording Measurements Without Mixing Configurations

Suggested grouping for recording results from **a single invocation**:

| Group | Objects | Question to answer |
| --- | --- | --- |
| Basic objects | `Object`, `Empty` | Do they differ? |
| Primitive fields | `OneInt`, `TwoLongs`, `Point` | How do fields and padding affect size? |
| Primitive arrays | `byte[0/1/7/8/64]`, `int[8]`, `long[8]` | Effect of type, length, and alignment |
| Reference arrays | `Object[8]`, `Object[8] nulls`, `Object[8] aliases` | Number of slots vs referenced contents |
| Holder | `RefBox(small)`/`RefBox(large)` | Is referent size counted recursively? |
| Alias graph | `Pair(shared)`/`Pair(distinct)` | Distinguishing shallow vs graph size |
| Text | `String(length=1/4096)` | String object vs backing storage |

**Pre-filled numbers in the table are not needed** for this lesson to be complete: the code prints each actual `long` value. When submitting a report, copy the actual output and include the JVM vendor/version, OS/arch, JVM flags, and workload name. Do not take a result table from the internet with unknown flags and treat it as the exact size on your system.

### 10.1. Example of computing a delta after obtaining output

Suppose you measure `s0 = getObjectSize(new byte[0])` and `s64 = getObjectSize(new byte[64])`, then:

```text
delta_bytes = s64 - s0

Interpret the delta only for the same array type,
same process, and same measurement setup.
```

If you want a ratio, you can compute `s64 / s0` when `s0 > 0`. However, that ratio is a **ratio of shallow estimates** including headers/padding, not a “payload compression ratio”. Do not infer that GC will reclaim exactly `delta_bytes` when a reference is dropped.

### 10.2. Why not use the execution time of `getObjectSize` as a size?

`System.nanoTime()` measures **duration**, in nanoseconds; `getObjectSize` returns a **byte estimate**. Those are two completely different quantities. Do not put `long before = System.nanoTime()` and infer bytes from `System.nanoTime() - before`. If you need to benchmark the overhead of the agent call, use JMH and microbenchmarking practices, without redefining the size metric.

## 11. Side Experiment: Changing JVM Flags in a Controlled Way

**The main experiment requires the same configuration.** After recording a complete baseline, you can run **a new process** with different HotSpot flags to study layout effects. This is **a separate experiment to observe VM dependence**; do not mix numbers from two invocations and claim the measurements are “under the same configuration”.

On 64-bit HotSpot JDK 17, if the options are supported by your vendor:

```bash
# Run A: illustrative fixed-heap configuration.
java -Xms256m -Xmx256m \
  -javaagent:size-agent.jar=lab \
  -cp "build/app:size-agent.jar" demo.CompareSizes

# Run B: disable compressed ordinary object pointers.
java -Xms256m -Xmx256m -XX:-UseCompressedOops \
  -javaagent:size-agent.jar=lab \
  -cp "build/app:size-agent.jar" demo.CompareSizes

# Run C: test 16-byte object alignment on HotSpot.
java -Xms256m -Xmx256m -XX:ObjectAlignmentInBytes=16 \
  -javaagent:size-agent.jar=lab \
  -cp "build/app:size-agent.jar" demo.CompareSizes
```

**`-XX:...` flags are HotSpot-specific; not all JVMs are guaranteed to accept them.** Do not expect B and C to always be “larger than A” for every object type. Compressed class pointers, heap ergonomics, field packing, padding, and object layout interact; alignment can increase some sizes in steps while leaving small objects unchanged in other cases.

Each run represents a **different JVM configuration**. Analysis should be separated:

- **Internal comparison within A**: one object versus another within process A.
- **Internal comparison within B**: one object versus another within process B.
- **If comparing A with B**: explicitly label it as a **configuration experiment**, not a portable conclusion about JVMs in general.

### 11.1. Why can compressed oops have an effect?

On many 64-bit HotSpot JVMs, compressed ordinary object pointers store references in a compressed form in many places. When disabled, some objects with multiple reference fields or `Object[]` may require different storage. Still, you do not need to infer pointer size from a C compiler or `sun.arch.data.model`: read the **actual VM flags** and **`getObjectSize` output**.

Do not assume `-XX:-UseCompressedOops` necessarily adds exactly `+4 bytes` per field; alignment may absorb the increase or step it up in larger increments.

### 11.2. Why does alignment change size numbers?

If the runtime aligns objects to `ObjectAlignmentInBytes`, a new field may fit into existing padding or push the total footprint past the next alignment boundary. With `-XX:ObjectAlignmentInBytes=16`, some small objects may be aligned up to a multiple of 16. **Do not** infer from this command that every object in every JVM must have a byte count divisible by 16 under the Java SE contract; the option is an implementation-specific policy.

## 12. Distinguishing Current Size from Allocation/Retained/Heap Footprint

The question “How much RAM does this object use?” can have four different meanings:

| Question | Which tool/approach is needed? |
| --- | --- |
| What is the estimated footprint of a single object? | `Instrumentation.getObjectSize(object)` |
| How many total bytes are in the object graph reachable from a root? | Graph traversal + identity deduplication + layout estimates, or heap analysis |
| How much heap would be freed if the root object were dropped? | **Retained heap/dominator** analysis, not simply summing sizes |
| How many bytes did a request allocate? | JFR allocation events, allocation profiling, JMH `gc.alloc.rate.norm`, or an equivalent tool |

### 12.1. Deep size is not just summing `getObjectSize` of each field

Suppose:

```text
          Pair
          /  \
         /    \
       ref    ref
         \    /
          \  /
         byte[4096]
```

Summing `getObjectSize(pair) + getObjectSize(pair.left) + getObjectSize(pair.right)` will **count the byte array twice** when both references point to the same object. To compute a **reachable size estimate**, you need to:

1. Traverse the object graph along reference relationships.
2. Use **object identity** (for example, `IdentityHashMap`) to avoid double-counting.
3. Distinguish primitive fields from reference fields, especially arrays.
4. Handle cycles, static references, weak/soft references, and classloader roots.
5. Have access to read instance fields of target objects; JPMS strong encapsulation can block reflection into JDK internals.
6. Decide on an inclusion policy: class objects/metaspace? off-heap buffers? shared interned objects? external native memory?
7. Accept that the sum of estimates is still not retained heap.

This is an **analysis process**, not a few lines of Java code. Do not add `--add-opens java.base/java.lang=ALL-UNNAMED` in production just to inspect `String.value` deeply; that widens access and still does not solve retained heap.

### 12.2. Retained heap differs from reachable heap

Object X **may reference** Y, while Y is also referenced by another root. Dropping X does not necessarily free Y. **Retained size** is typically tied to a dominator tree: objects that remain reachable only through X. `getObjectSize(X)` contains no information about the dominator tree, GC roots, or inbound references.

Example:

```text
Root A -> X -> Y
Root B ------> Y
```

Y is reachable from X, but dropping X does **not** guarantee Y is reclaimed because Root B still holds Y. Therefore, `getObjectSize(X) + getObjectSize(Y)` cannot be used as the amount of RAM freed if the reference A→X is removed.

### 12.3. An allocation profiler is not a substitute for object size

Measuring a delta:

```java
// Anti-pattern, not a measurement of a single object's size.
Runtime r = Runtime.getRuntime();
long before = r.totalMemory() - r.freeMemory();
Object value = new Object();
long after = r.totalMemory() - r.freeMemory();
long guessed = after - before;
```

This subtraction is affected by other allocations, GC, thread activity, TLABs, JIT escape analysis, and runtime bookkeeping. It **does not replace `getObjectSize(value)`**, nor is it a reliable retained heap metric.

## 13. When to Use JOL, JFR, or a Heap Analyzer?

- **JOL (Java Object Layout)**: an OpenJDK library/tool for inspecting field offsets, headers, and alignment/padding on a specific VM. Useful when you want to understand **why** `getObjectSize` returned the observed result. It uses mechanisms to access VM internals depending on the JDK and may require flags; it is not a standard Java SE API.
- **JFR (Java Flight Recorder)**: observes allocation hotspots, GC, and runtime events over time. Use it when the question is “how many objects/bytes does this code allocate?”, not what size a specific object has.
- **Heap dump + analyzer (Eclipse MAT or equivalent)**: provides object counts, shallow/retained sizes, and paths to GC roots at a snapshot. Useful for explaining memory leaks.
- **`jcmd GC.class_histogram`/heap histograms**: useful for viewing total instances/bytes per class on HotSpot at a point in time, but not the size of an individual object, and it can affect the application.
- **JMH**: measures overhead, time, and allocation rate of sizing code or object-creating code in controlled forks, avoiding manual benchmarks with timer noise.

**No single tool completely replaces the others.** This lesson focuses on `getObjectSize`; JOL/JFR/MAT are the next steps when your question goes beyond a shallow estimate.

## 14. Common Errors and Troubleshooting

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `AGENT_ACTIVE=false` | Agent JAR is on classpath, but `-javaagent` is missing | Add `-javaagent:size-agent.jar=lab` **before** the main class |
| Startup reports missing `Premain-Class` | Manifest lacks the entry or JAR is malformed | Inspect `META-INF/MANIFEST.MF` and rebuild |
| JVM cannot find `demo.SizeAgent` | Manifest binary name and JAR class entry do not match | Run `jar --list` and check `demo/SizeAgent.class` |
| `ClassNotFoundException: demo.CompareSizes` | `-cp` uses the wrong separator or path | Unix `:`, Windows `;`, verify `build/app` |
| `IllegalStateException` when calling `sizeOf` | `premain` has not run, yet the app calls the agent API | Run with the startup agent and check the active flag |
| `NullPointerException` on `sizeOf(null)` | Standard contract of `getObjectSize` | Test for NPE; do not treat null as a 0-byte object |
| Array sizes differ from numbers on a blog | Different JDK/vendor, alignment, or compressed references | Record VM config and compare **within the same process** |
| `Object[8]` is “smaller than 8 objects” | `Object[]` holds reference slots, not the pointed-to objects | Measure referents separately |
| `RefBox(large)` is no larger than `RefBox(small)` | Shallow size of the box does not include the referred array | Measure `byte[4096]` separately; explain the graph |
| `String(long)` and `String(short)` are nearly identical | `getObjectSize(String)` does not count backing content | Use heap analysis if total footprint is needed |
| Measurements differ between two runs | Different VM flags/JDK/GC/ergonomics; estimates may vary | Pin runtime config and note variability |
| Added an `int` field but size did not increase | Padding/alignment may have absorbed the field | Use JOL to inspect the layout |
| Code reading `String.value` throws `InaccessibleObjectException` | JPMS encapsulates private `java.base` internals | Avoid private reflection in the lab |
| Heap used delta does not match `getObjectSize` | Allocation metric has GC/JIT/TLAB interference | Use the right tool for the metric |
| “Retained size” differs from `getObjectSize` | Retained graph/dominator differs from shallow size | Heap dump/MAT, paths to GC roots |
| `-XX:-UseCompressedOops` is rejected | JVM does not support HotSpot flags or runtime policy | Do not use incompatible flags |
| `-XX:ObjectAlignmentInBytes=16` does not change every object | Padding, layout, and VM policy | Measure per type; do not assume a fixed rule |
| Agent compiled on newer Java fails on JVM 17 | Bytecode major version is too high | Compile with `javac --release 17` and test on target runtime |
| Need CPU/GC overhead, but only have size | Two different quantities | Use JFR/JMH/profiler as appropriate |

## 15. Practice Checklist

- [ ] Verify JDK, vendor, architecture, and VM flags before comparing.
- [ ] Identify the exact question: **shallow estimate** vs **reachable/retained/allocated bytes**.
- [ ] Use `-javaagent` and a valid `Premain-Class` manifest to obtain `Instrumentation`.
- [ ] Run the non-agent baseline: `AGENT_ACTIVE=false`, no measurements performed.
- [ ] Run with the agent: `PREMAIN_ARGS=lab` before `MAIN_BEGIN`, `AGENT_ACTIVE=true`.
- [ ] Measure all objects within the same JVM process/configuration.
- [ ] Do not hardcode byte counts from examples on other machines.
- [ ] Compare `Object`/`Empty`/primitive fields/record to discuss padding.
- [ ] Compare `byte[]` across lengths and `int[]`/`long[]`/`Object[]` of the same length.
- [ ] Distinguish a reference array from the objects it points to.
- [ ] Compare `RefBox` holding small/large arrays and measure each referent array separately.
- [ ] Compare `Pair(shared)`/`Pair(distinct)` to see identity and object graph differences.
- [ ] Do not use `String.length()` as the number of bytes allocated.
- [ ] Verify `getObjectSize(null)` throws `NullPointerException`.
- [ ] Do not use `Runtime.totalMemory() - freeMemory()` as the size of a single object.
- [ ] If running with different HotSpot flags, report it as a **separate cross-configuration experiment**.
- [ ] Present actual measurements alongside JVM version and flags, without filling in fake numbers.
- [ ] Recognize if estimates vary between calls: the Javadoc permits it; do not force measurements to be invariant.
- [ ] For deep/retained memory, use identity-aware graph analysis or heap tools.
- [ ] Do not open reflection access to JDK internals just to measure this lab.
- [ ] Verify the right tool for the goal: JOL for layout, JFR for allocations, MAT for retained heap, JMH for performance.

## 16. Self-Check Questions

1. **Is `getObjectSize` a portable exact byte count under Java SE?**  
   No. The Javadoc calls it an implementation-specific approximation; it may even change within a single JVM run.

2. **Why is `premain` needed?**  
   So the JVM can pass `Instrumentation` to the Java agent at startup; normal applications cannot create this instance themselves.

3. **Should `sizeOf(null)` return 0 or throw an exception?**  
   Throw `NullPointerException`, per the `Instrumentation.getObjectSize` contract.

4. **Does `getObjectSize(new byte[4096])` measure the byte elements?**  
   A primitive array object contains inline element storage; the estimate reflects the array itself, though exact bytes depend on the VM.

5. **Does `getObjectSize(new Object[100])` add the sizes of the 100 referenced objects?**  
   Not automatically. It measures the array object/slots and does not recurse through referents.

6. **Does changing `RefBox.value` from `byte[1]` to `byte[4096]` necessarily increase the box's shallow size?**  
   No. The box still stores a single reference field; the array is a separate object.

7. **If two references point to the same object, can you compute deep size by summing each reference?**  
   No; that object would be counted twice. You must deduplicate by identity.

8. **Is a `record` guaranteed by standard JVMs to use less memory than a regular class?**  
   No. Layout still depends on the JVM implementation.

9. **Is `String.length() * 2` the size of a `String` object?**  
   No. Compact strings, backing arrays, headers, and sharing make that formula incorrect.

10. **Why might `byte[7]` and `byte[8]` have the same size estimate?**  
    Because of alignment/padding in a given VM layout; not every payload byte immediately increases footprint.

11. **If you disable compressed oops and see different sizes, should you compare those numbers directly against the baseline as “same configuration”?**  
    No. Those are two different configurations; the test conditions must be stated.

12. **An object on HotSpot today is 16 bytes. Can you assert `== 16` for all Java 17 JVMs?**  
    No. Java SE does not mandate such absolute sizes.

13. **Is retained size equal to the sum of reachable object sizes?**  
    Not necessarily. Retained size depends on dominators/GC roots and shared references.

14. **Is the heap used delta before and after creating an object equal to `getObjectSize`?**  
    Not guaranteed, due to GC, JIT, TLABs, and other allocations.

15. **If the goal is “how many bytes per second does method A allocate?”, is `getObjectSize` enough?**  
    No. Use JFR/allocation profiling or JMH allocation metrics.

16. **If you need field offsets and header breakdown, what should you use?**  
    Use JOL or an appropriate layout analysis tool, while also checking JVM version/flags.

17. **Why must `size-agent.jar` be passed to both `-javaagent` and `-cp` in this lab?**  
    `-javaagent` triggers the JVM to invoke `premain`; `-cp` lets the application link against the public class `demo.SizeAgent` under the chosen artifact layout.

18. **Can measuring sizes between two JVM processes with the same flags still show differences?**  
    Yes. The Javadoc does not guarantee an invariant absolute value; environment, implementation, or ergonomics may differ.

19. **If an `Object[]` element changes from `null` to a reference to a large array, can you infer total heap from the `Object[]`'s size?**  
    No. The referent remains a separate object; you must account for the graph and reachability.

20. **What is the evidence of completing this lab?**  
    An active agent, real measurements within one JVM, clear analysis of the effects of fields/arrays/references without confusing shallow with deep/retained size, and reporting the configuration without hardcoding byte counts.

## 17. Official References

1. Oracle JDK 17 — **`Instrumentation.getObjectSize(Object)`**, approximation contract, `null` NPE, plus `getAllLoadedClasses`/transformers: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
2. Oracle JDK 17 — **`java.lang.instrument` package**, `-javaagent`, `Premain-Class`, and `premain`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
3. Oracle JDK 17 — **`java` launcher**, `-XX:-UseCompressedOops` and `-XX:ObjectAlignmentInBytes` on HotSpot: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
4. Oracle JDK 17 — **Java HotSpot performance enhancements**, compressed ordinary object pointers: https://docs.oracle.com/en/java/javase/17/vm/java-hotspot-virtual-machine-performance-enhancements.html
5. OpenJDK **JOL (Java Object Layout)**, implementation-dependent object headers/field layout/array base: https://github.com/openjdk/jol
6. Oracle JDK 17 — **`Class` and Java reflection** (limitations when inspecting object fields): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
7. Oracle JDK 17 — **`Runtime`**, `totalMemory`/`freeMemory` do not directly substitute for object size: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html
8. Oracle — **Java Flight Recorder**, allocation/runtime profiling: https://docs.oracle.com/en/java/javase/17/jfapi/
9. OpenJDK **JMH**, microbenchmarking and `gc.alloc.rate.norm`: https://github.com/openjdk/jmh
10. Eclipse MAT — **Memory Analyzer**, retained heap and dominator analysis: https://eclipse.dev/mat/

**Conclusion:** In Java instrumentation, `Instrumentation.getObjectSize` helps compare **the estimated footprint of individual objects** while keeping the **JVM implementation/configuration** consistent. Primitive arrays hold element payloads inline, while reference arrays and reference fields only store slots rather than adding the object graph. Do not use these results as deep/retained sizes or as the bytes allocated by a request. When you need to answer deeper questions, choose JOL/JFR/MAT/JMH for the appropriate metric, and report numbers as measurements **from the specific JVM that ran**, not as Java SE constants.
