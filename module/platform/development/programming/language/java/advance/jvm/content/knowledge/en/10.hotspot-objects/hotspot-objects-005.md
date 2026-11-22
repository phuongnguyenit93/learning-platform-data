# Compressed oops and compressed class pointers in 64-bit JVM

## 1. Objectives

On a 64-bit machine, native addresses typically have a width of 64 bits. If every Java reference field in an object and every **Object[]** element had to occupy 8 bytes, applications with many objects would consume significant memory for references. **HotSpot** has a mechanism called **compressed ordinary object pointers (compressed oops)** to store many references to Java heap objects using a narrow encoded form, usually **32 bits**. Another mechanism, **compressed class pointers**, uses a narrow form to represent **the pointer to the object type information** in the object header.

The two mechanisms address **two different types of pointers**, although they are related to performance, object size, and how HotSpot allocates memory regions. They do not change reference types in Java source code, do not turn a 64-bit JVM into a 32-bit JVM, and are not mandated by the Java Virtual Machine Specification (JVMS).

After this lesson, you will be able to:

- Distinguish **oop**, **narrowOop**, **Klass***, **narrowKlass**, and **java.lang.Class**.
- Explain why a 32-bit encoded reference can still address a heap of roughly tens of GiB thanks to **alignment**, **base**, and **shift**.
- Read a 64-bit HotSpot object header diagram under compressed or uncompressed **class pointers** configurations.
- Calculate the hypothetical size of an object or reference array under compressed/uncompressed configurations, accounting for **padding**.
- Distinguish the **commonly mentioned 32 GiB threshold** from an absolute limit; understand the impact of **ObjectAlignmentInBytes** and heap placement.
- Know the flags **UseCompressedOops**, **UseCompressedClassPointers**, **ObjectAlignmentInBytes**, **CompressedClassSpaceSize**, and how to check actual runtime flag values.
- Know the benefits, encode/decode costs, impact on cache locality, GC, and when only actual benchmarks are sufficient to conclude.
- Use **jcmd**, **PrintFlagsFinal**, **JOL**, and Java 17+ tools to observe without misinterpreting the numbers.

**Scope:** these illustrative layouts use 64-bit HotSpot **Java 17**, with **traditional object headers** and 8-byte alignment, unless explicitly stated otherwise. Other JVM implementations or other JDK versions may use different organizations. This is a **HotSpot implementation** mechanism, not an obligation for every Java SE-compliant JVM.

## 2. Terminology: oop vs. Klass pointer

In HotSpot documentation and source code:

- **oop** is a native-level reference to a **Java heap object**. The historical name is *ordinary object pointer*.
- **narrowOop** is the narrow encoded form of an oop, usually 32 bits when compressed oops are enabled.
- **Klass*** is a native-level pointer to the HotSpot metadata structure describing the **runtime class** of an object.
- **narrowKlass** is the narrow encoded form of a **Klass*** pointer, typically used in the **object header** when compressed class pointers are enabled.
- **java.lang.Class** is a **Java heap object** (class mirror) observable from Java via **SomeType.class**; it is **not** the same kind of object as the native **Klass*** structure.

Comparison table:

| Concept | What it points to | Typical usage location | Is it synonymous with a Java reference? |
| --- | --- | --- | --- |
| **oop** | Object/array on the Java heap | Object field, array element, many VM execution paths | It is how HotSpot represents a reference to a Java object |
| **narrowOop** | Object/array on the Java heap after decoding | Object field/array element when compressed | It is an encoding of oop |
| **Klass*** | Class metadata in the VM | Object header/VM internals | **Not** a regular Java object reference |
| **narrowKlass** | Class metadata via decoding | Object header when class pointers are compressed | **Not** narrowOop |
| **Class<?> mirror** | Java object representing a class | Reflection: **String.class**, **getClass()** | It is a Java object, referenced by an oop like other objects |

**Serious error:** "A compressed class pointer is a compressed oop pointing to a java.lang.Class object." Incorrect. The object header contains a class/klass metadata pointer; the Java Class mirror is a heap object linked to the metadata, but the two are not identical.

### 2.1. Two reference paths in the same object

~~~text
Java:
class Container {
    Object item;
}

A Container instance on HotSpot (illustrative):
+------------------------------------------------+
| Mark word                                      |
| Encoded class pointer (narrowKlass) ----------+ |----> Klass metadata of Container
| Field item (narrowOop) -----------------------|----> Java heap object referenced by item
| Padding if needed                             |
+------------------------------------------------+

Container.class ------> java.lang.Class mirror on heap
                            |
                            +-- runtime link to Klass metadata
~~~

An **item** field can be **null** or reference any Object; the class pointer in the object header indicates the runtime type of the **Container object** itself. They do not serve the same role, do not use the same address base, and cannot be interchanged.

## 3. Why does a 64-bit VM need compressed references?

Suppose a program has an object containing four reference fields and millions of similar objects. If a reference occupies 8 bytes instead of 4 bytes, four fields alone can add **16 bytes per object before considering alignment**. At one million objects, the difference in raw field storage is already about 16 million bytes; the actual impact also depends on object headers, padding, and graph layout.

For **Object[]**, each element is a reference slot, so an array with many elements can clearly benefit:

~~~text
Reference slots of Object[8]:

Uncompressed:
  [8B][8B][8B][8B][8B][8B][8B][8B] = 64 B

Compressed oops:
  [4B][4B][4B][4B][4B][4B][4B][4B] = 32 B

Excluding header, alignment, or the actual objects referenced.
~~~

The benefits are not just **heap footprint**:

- Fewer reference bytes can improve **CPU cache locality**.
- Less data transferred from RAM/cache can reduce **memory bandwidth**.
- Some GC components traversing the object graph have fewer reference bytes to read/write.
- For cache/memory-bound workloads, the effect can be positive.

In return, the runtime must **encode/decode** references at appropriate places. The JIT compiler may optimize or fold operations; therefore, one cannot claim it is always faster or always slower without benchmarking. The impact depends on heap size, object graph, CPU architecture, GC, compiler, and configuration.

## 4. What does "a 32-bit reference that can still point to a 32 GiB heap" mean?

If 32 bits represent a **direct byte address**, we have at most:

~~~text
2^32 bytes = 4 GiB
~~~

However, an object is typically aligned to an address divisible by **8 bytes** in the default 64-bit HotSpot configuration. The low three bits of the byte **offset** are always 0. Instead of storing byte-by-byte addresses, the VM can store **offsets in 8-byte units**.

Idea:

~~~text
Actual address/offset:   0x00000000_00000018 = 24 bytes
Encoded in 8-byte units: 24 / 8 = 3

32-bit narrow value:     3
Decode (shift=3):        3 << 3 = 24
~~~

With 2^32 possible encodings, each step representing 8 bytes, the theoretical range is:

~~~text
2^32 * 8 bytes = 2^35 bytes = 32 GiB
~~~

This is why many documents say compressed oops support a heap of about **32 GiB** with 8-byte alignment. **Not** every 32-bit narrow value points to a valid object or means each object only takes 8 bytes; this is the **addressable** range, not the actual number of objects.

### 4.1. Base + shift

A common decoding scheme for a **non-null** narrow oop:

~~~text
decoded_address = base + (unsigned(narrowOop) << shift)
~~~

Where:

- **base**: the base address (or 0) depending on the encoding mode.
- **shift**: the number of shift bits, usually **3** with 8-byte object alignment.
- **narrowOop**: the 32-bit encoded value.
- **decoded_address**: the corresponding native-level address used by HotSpot to reference the object.

The reverse direction (within valid values and appropriate alignment):

~~~text
narrowOop = (decoded_address - base) >> shift
~~~

**This is a model**, not a Java API for accessing pointers. Details about NULL encoding, read/write barriers, GC forwarding, and address regions are handled by the VM.

### 4.2. Arithmetic example with non-zero base

Suppose *a mode* has:

~~~text
base          = 0x0000001000000000
shift         = 3
encoded value = 7
offset        = 7 * 8 = 56 decimal = 0x38

decoded address = 0x0000001000000038
~~~

This is a **hypothetical address**, not the real address of a Java object in a program. It shows why both **base** and **shift** are needed together. The zero-based form has base equal to 0, so the base addition can be eliminated, enabling faster code in some situations.

### 4.3. Do not forget null

A Java reference has the value **null**. HotSpot ensures that an encoded narrowOop value of 0 can be recognized as null according to implementation rules. For heap-based modes, handling null may require branching/special handling; one cannot mechanically assume that every pointer with value 0 decodes to **base** and is treated by Java as a valid object.

When manually simulating the formula with integers, remember it illustrates **non-null aligned references**; null is a special case.

## 5. Encoding modes of compressed oops

HotSpot documentation and source code distinguish modes to optimize decoding depending on where the Java heap is allocated:

| Mode (common name) | Idea | Shift/base |
| --- | --- | --- |
| **Unscaled / 32-bit** | Heap lies in a low address range; encoded value can be used directly as a byte offset | May have shift=0, base=0 |
| **Zero-based** | Heap lies in an address region suitable for base=0 | Usually shift=3 if addressing beyond 4 GiB is needed |
| **Non-zero / heap-based** | Uses a non-zero base address and a scaled offset | Base != 0, shift usually 3 |
| **Disjoint-base** (suitable implementation mode) | Chooses a base with a favorable bit pattern to optimize decoding | Still encoded offset + base logic, can be optimized with OR |

**You cannot force every JVM/OS/JDK to use only one specific mode.** The VM must be able to reserve the heap in a suitable address region; ASLR, address space layout, heap size, and VM arguments affect the chosen mode.

A HotSpot log line might express something like:

~~~text
Compressed Oops mode: Zero based
Oop shift amount: 3
~~~

This is an example log format, **not fixed stdout** for every run or every JDK. All numbers regarding heap base/mode must be measured from the actual process.

### 5.1. 32 GiB is not a boundary independent of all flags

The statement "compressed oops only work when -Xmx is under 32G" is an oversimplification:

- With 8-byte alignment, **32 GiB** is the theoretical range from 32-bit values shifted by 3 bits.
- Reservation/guard/alignment details can cause the actual on/off threshold to be lower than exactly 32 GiB on a specific JVM.
- **-XX:ObjectAlignmentInBytes** can change object alignment, causing the shift and addressable range to change.
- For example, alignment **16** gives a theoretical range of **2^32 × 16 = 64 GiB**, but padding/fragmentation costs may also increase.
- The VM may automatically disable compressed oops or reject the configuration if the request cannot be supported; one should not infer from **-Xmx** alone that the final flag is definitely enabled.

**Do not treat increasing alignment as a default optimization.** Increasing object alignment causes many small objects to spend more on padding; the reference savings may be outweighed. Choose by actual measurement and checking final JVM flags.

## 6. What are compressed class pointers used for?

Every Java heap object in HotSpot has an **object header** containing object management information and information about the object's **class metadata**. In a traditional 64-bit header:

- **Mark word**: runtime information area of the object; bit meanings depend on the state/HotSpot version (hash/locking/GC age...).
- **Klass pointer**: reference to metadata describing the runtime class of the object.
- For an **array object**, there is also **array length** in the traditional header.

When **compressed class pointers** are enabled, the class pointer component in the header can be stored as a **4-byte narrowKlass** instead of an **8-byte Klass***.

**NarrowKlass is different from narrowOop**:

| Question | Compressed oops | Compressed class pointers |
| --- | --- | --- |
| What is being compressed? | References to **Java heap objects** | References to **Klass metadata** |
| Where does it appear? | Java reference fields, arrays, and other appropriate places | Object header class pointer |
| Target address space? | Java heap | Class metadata region / class space |
| Encoding base/shift? | Tied to the object heap | Tied to class metadata addresses, with its own rules |
| Direct impact? | Size of reference field/array element | Size of the class-pointer component in the header |
| Related HotSpot flag? | **UseCompressedOops** | **UseCompressedClassPointers** |

With class pointer compression, the VM can reserve an address region for class metadata so narrowKlass can encode/decode appropriately. **CompressedClassSpaceSize** is a related option, but it is not a heap-size limit and is not synonymous with total Metaspace capacity.

### 6.1. Klass*, Class mirror, and class loader

~~~text
Java heap:
   anObject ----> Object header ----> Klass* metadata
   SomeType.class ----> java.lang.Class mirror object

Native class metadata:
   Klass structure describing SomeType
     - class loader identity
     - fields/methods/runtime metadata...
~~~

The relationship between the Java mirror and VM metadata is managed by HotSpot. When reading:

~~~java
Class<?> type = anObject.getClass();
~~~

Java code receives the **Class mirror**. This does **not** mean the VM simply takes the 32-bit narrowKlass value itself and returns it directly as a Java reference. The runtime must provide the proper Java object reference to the mirror via internal mechanisms.

**The same binary name in two defining class loaders** can create two distinct runtime classes and two distinct Klass metadata structures. Therefore, the class pointer of corresponding instances must point to the correct metadata of that runtime class.

## 7. Object header and size on traditional 64-bit HotSpot

The following tables assume **64-bit HotSpot Java 17** layout, traditional object headers, 8-byte object alignment, and no other header variants. These numbers are **typical examples**, not a JVMS specification, and are not guaranteed to be identical across all runtimes.

| Regular object header | With compressed class pointer | Without compressed class pointer |
| --- | ---: | ---: |
| Mark word | 8 B | 8 B |
| Klass pointer | 4 B | 8 B |
| Total header **before padding** | **12 B** | **16 B** |

For arrays in the traditional layout, **array length** usually adds **4 B**:

| Array header | With compressed class pointer | Without compressed class pointer |
| --- | ---: | ---: |
| Mark word | 8 B | 8 B |
| Klass pointer | 4 B | 8 B |
| Array length | 4 B | 4 B |
| Raw header bytes | 16 B | 20 B |
| First element position | Depending on element alignment and layout, typically 16 B for compressed Object[] | May require padding so reference element position aligns appropriately |

**Note:** compressed oops determine element reference width; compressed class pointers determine header pointer width. Therefore, **both flags must be considered**; one cannot simply say "enabling compressed oops makes every header 12 bytes" in all configurations.

### 7.1. Layout example of Holder with three references

~~~java
// Illustrative code about layout, not a Java memory property requirement:
final class Holder {
    Object first;
    Object second;
    Object third;
}
~~~

Assume 64-bit HotSpot traditional headers, 8-byte object alignment.

**Both compressed oops and compressed class pointers enabled**:

~~~text
Offset  Bytes   Component
0       8       Mark word
8       4       narrowKlass
12      4       narrowOop first
16      4       narrowOop second
20      4       narrowOop third
------------------------------
Total raw          24 bytes
Rounded to 8       24 bytes
~~~

**Both disabled** (wide object references and wide klass pointer):

~~~text
Offset  Bytes   Component
0       8       Mark word
8       8       Klass*
16      8       oop first
24      8       oop second
32      8       oop third
------------------------------
Total raw          40 bytes
Rounded to 8       40 bytes
~~~

The illustrative difference is **40 - 24 = 16 bytes/object**, i.e., 40% of the wide size. One million Holder instances in terms of **ideal shallow instance size** have a difference of 16 million bytes before considering GC overhead, other allocation metadata, and the referenced objects.

**Do not claim "a Java object always has a 12-byte header"**: besides class pointer width, there are JDK/VM mode, array kind, header implementation, alignment, and allocation decisions.

### 7.2. Example of an object with two int fields: padding can negate savings

~~~java
final class Point {
    int x;
    int y;
}
~~~

With the same 64-bit HotSpot assumptions:

~~~text
Compressed klass:
  header 12 + x 4 + y 4 = 20 -> align8 = 24 B

Wide klass:
  header 16 + x 4 + y 4 = 24 -> align8 = 24 B
~~~

Both are 24 bytes due to alignment. This shows that **a 4-byte reduction in the header does not necessarily reduce the final shallow size of every object type**; padding can absorb the savings.

### 7.3. Example of Object[1000]

Suppose a compressed klass array header is 16 bytes, compressed oop element is 4 bytes, 8-byte alignment:

~~~text
Object[1000] compressed:
  16 + 1000 * 4 = 4016 B
  align8 => 4016 B
~~~

With wide klass and wide element references, the element header may start at offset 24:

~~~text
Object[1000] wide:
  24 + 1000 * 8 = 8024 B
  align8 => 8024 B
~~~

The illustrative shallow size difference is **4008 bytes** for this array, **excluding** the 1000 objects that the elements might point to. If the array only contains null, the backing array itself still has the slots; having no referenced objects does not eliminate the memory of the slots.

### 7.4. Primitive arrays and fields

**int[]**, **byte[]**, **long[]** contain primitive elements, not Java object references in each element. Therefore, **compressed oops do not automatically shrink int elements from 4 bytes to 2 bytes** or long elements from 8 to 4.

Class pointer compression can still affect the **header of a primitive array**, but element widths are a separate matter.

| Component | Directly changed in width by compressed oops? |
| --- | --- |
| Object reference field | Yes in appropriate HotSpot layouts |
| Object[] element reference | Yes |
| int/float field | No |
| long/double field | No |
| byte/char/boolean primitives | Not directly by oop compression |
| Klass pointer in header | Belongs to compressed **class pointers**, not oop fields |
| Java object pointed to by reference | Still an object, with its own size |

## 8. Why are the two mechanisms related yet distinct?

Many HotSpot configurations enable both mechanisms by default. However, one must distinguish:

- **UseCompressedOops** controls the representation of appropriate oop locations.
- **UseCompressedClassPointers** controls the representation of klass references in object headers according to HotSpot capabilities.
- The set of conditions/policies enabling each flag may differ by JDK version, architecture, and relationships between flags.
- Do not infer from **UseCompressedOops=true** **without checking** that every environment definitely has **UseCompressedClassPointers=true**.
- Do not infer from "class metadata is compressed" that the entire **Metaspace** or every pointer in the JVM is halved.

In JDK 17/HotSpot, compressed class pointers are tied to a **compressed class space** region managed alongside appropriate Metaspace mechanisms. According to Oracle Java 17 tuning documentation, **CompressedClassSpaceSize** has a stated default of **1 GiB** in the corresponding configuration; the actual flag value may differ due to version/ergonomics/explicit overrides.

**Compressed class space is not the Java heap.** Do not increase **-Xmx** to "make more room for narrowKlass metadata" by direct assumption; one must inspect class metadata counts, Metaspace/CCS flags, and the native memory budget.

## 9. Does reference decoding make Java code behave differently?

No. According to the Java language, expressions like:

~~~java
Object a = new Object();
Object b = a;
Object c = new Object();
System.out.println(a == b);
System.out.println(a == c);
~~~

mean **identity comparison** of Java objects, independent of whether the VM stores oops in wide or compressed form. The fact that the VM must decode narrowOop before using an object does not turn **==** into comparing encoded byte sequences under any public contract.

Things Java code **cannot** infer:

- Actual pointer address from **System.identityHashCode**.
- Reference slot size from **Class.getName()**.
- Object memory address via **Object.toString()**.
- NarrowOop payload from **equals** or a cast.
- That objects are laid out contiguously and not moved by GC.

A Java reference is an abstract value type; HotSpot can compress, decompress, keep values in registers, and GC can move objects, as long as Java semantics are preserved.

## 10. Java 17+ Example 1: reference semantics invariant to compression flags

Create file **ReferenceSemanticsDemo.java**:

~~~java
public class ReferenceSemanticsDemo {
    static final class Node {
        Node next;
        int value;

        Node(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Node a = new Node(7);
        Node same = a;
        Node other = new Node(7);
        a.next = other;

        Node[] nodes = {a, same, other};

        System.out.println("sameRef=" + (a == same));
        System.out.println("differentObject=" + (a != other));
        System.out.println("sameValue=" + (a.value == other.value));
        System.out.println("arrayAlias=" + (nodes[0] == nodes[1]));
        System.out.println("link=" + (a.next == nodes[2]));
    }
}
~~~

Compile/run on JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 ReferenceSemanticsDemo.java
java ReferenceSemanticsDemo
~~~

**Stdout:**

~~~text
sameRef=true
differentObject=true
sameValue=true
arrayAlias=true
link=true
~~~

Run additionally on a **64-bit HotSpot** supporting the following flag:

~~~bash
java -XX:-UseCompressedOops ReferenceSemanticsDemo
~~~

**Java-level stdout remains the same**, because compressed oops are only an internal representation. However, the shallow size of objects/arrays may change. Do not treat identical stdout as proof that **the flag was enabled/disabled as intended**: you must read the final flag values as shown in the next section.

### 10.1. What cannot be measured by this example

The example above **does not** display addresses, header bits, or the number of bytes of a reference. It only confirms that Java semantics are preserved. To see actual HotSpot layout, use JOL/diagnostic VM tools. Do not try to write Java source code to read private native pointers or use unsafe memory hacks in foundational exercises.

## 11. Java 17+ Example 2: illustrative layout calculation (not introspection)

Create file **LayoutArithmeticDemo.java**:

~~~java
public class LayoutArithmeticDemo {
    static int alignUp(int bytes, int alignment) {
        return ((bytes + alignment - 1) / alignment) * alignment;
    }

    static int holderSize(int headerBytes, int referenceBytes,
                          int references, int alignment) {
        return alignUp(headerBytes + referenceBytes * references, alignment);
    }

    static int arraySize(int headerBytes, int elementBytes,
                         int length, int alignment) {
        return alignUp(headerBytes + elementBytes * length, alignment);
    }

    public static void main(String[] args) {
        int compressedHolder = holderSize(12, 4, 3, 8);
        int wideHolder = holderSize(16, 8, 3, 8);
        int compressedArray = arraySize(16, 4, 1000, 8);
        int wideArray = arraySize(24, 8, 1000, 8);

        System.out.println("holderCompressed=" + compressedHolder);
        System.out.println("holderWide=" + wideHolder);
        System.out.println("arrayCompressed=" + compressedArray);
        System.out.println("arrayWide=" + wideArray);
        System.out.println("holderSavings=" + (wideHolder - compressedHolder));
        System.out.println("arraySavings=" + (wideArray - compressedArray));
    }
}
~~~

Run:

~~~bash
javac --release 17 -encoding UTF-8 LayoutArithmeticDemo.java
java LayoutArithmeticDemo
~~~

**Exact stdout:**

~~~text
holderCompressed=24
holderWide=40
arrayCompressed=4016
arrayWide=8024
holderSavings=16
arraySavings=4008
~~~

The program uses **hypothetical layout parameters** of a traditional HotSpot configuration. It does not access the memory layout of the running VM and will print the same numbers even if you disable compressed oops. The important part is understanding **calculation + alignment**, without confusing these arithmetic results with a heap measurement tool.

### 11.1. Limitations of the formula

**alignUp(raw, 8)** only simulates rounding at the object size level. HotSpot may reorder fields, insert internal padding, and arrange headers/arrays according to runtime configuration. For classes with mixed-width fields and inheritance, a formula taking header plus sum(field sizes) may not accurately reflect the layout. You need to measure the specific class.

## 12. How to check which JVM flags are actually enabled

On **64-bit HotSpot/OpenJDK/Oracle JDK 17**, use the command:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Output lines may include these flags:

~~~text
UseCompressedOops
UseCompressedClassPointers
ObjectAlignmentInBytes
CompressedClassSpaceSize
MaxHeapSize
MaxMetaspaceSize
~~~

In practice, **PrintFlagsFinal prints many flags**; search for the names above using your terminal's search tool. Do not assert a fixed line order or fixed bool value, as ergonomic flags can depend on version, machine memory, container, and other options.

On Linux/macOS you can filter:

~~~bash
java -XX:+PrintFlagsFinal -version 2>&1 \
  | grep -E 'UseCompressedOops|UseCompressedClassPointers|ObjectAlignmentInBytes|CompressedClassSpaceSize|MaxHeapSize'
~~~

In PowerShell:

~~~powershell
java -XX:+PrintFlagsFinal -version 2>&1 |
  Select-String 'UseCompressedOops|UseCompressedClassPointers|ObjectAlignmentInBytes|CompressedClassSpaceSize|MaxHeapSize'
~~~

**Only compare values under the same startup conditions.** If a production application runs in a container with memory limits, the flags chosen by ergonomics may differ from a bare java command on a laptop.

### 12.1. Enabling/disabling compression in experiments

Example (only with supporting HotSpot implementations):

~~~bash
java -Xmx512m -XX:+UseCompressedOops ReferenceSemanticsDemo
java -Xmx512m -XX:-UseCompressedOops ReferenceSemanticsDemo
~~~

Use **PrintFlagsFinal** with the same flags to confirm the final state:

~~~bash
java -Xmx512m -XX:-UseCompressedOops -XX:+PrintFlagsFinal -version
~~~

Do not automatically try to enable a flag not supported by the configuration/JVM in production. Some flags have dependencies and require the VM to decide feasible values; the final decision must be checked in the output.

**Do not confuse:** **-Xmx512m** is the max heap size; it does not directly limit the bytes of **class metadata**, does not indicate used heap, and does not mean the memory actually committed by the process is 512 MiB.

### 12.2. Observing compression mode and GC logs

HotSpot has logging tags for compressed oops/heap in some versions/configurations. Example for guidance:

~~~bash
java -Xlog:gc+heap+coops=debug -version
~~~

Not every build/mode prints the same data. Use:

~~~bash
java -Xlog:help
~~~

to see valid tags on the running JVM. When logs are available, you can look for **Compressed Oops mode**, heap address range, or oop shift; this is diagnostic output, **not a stable API**.

### 12.3. jcmd for a real process

If using HotSpot and JDK tools:

~~~bash
jcmd
jcmd <PID> help
jcmd <PID> VM.flags
jcmd <PID> VM.metaspace
~~~

Replace **<PID>** with the actual PID. Some commands/detail levels depend on the JDK build and permissions; always read **jcmd <PID> help** before applying. **VM.metaspace** helps investigate class metadata, not output the exact size of each oop field of every object.

## 13. Using Java Object Layout (JOL) to observe real objects

**JOL (Java Object Layout)** is an OpenJDK tool for inspecting/estimating JVM memory layout. It can display reference field sizes, offsets, headers, alignment, and differences between VM configurations.

Example usage once you have the proper JOL CLI JAR:

~~~bash
java -jar jol-cli.jar internals java.lang.Integer
~~~

Or use JOL **jol-core** via an appropriate dependency and the **ClassLayout** API in a Java project. This is a command example depending on a JAR provided by OpenJDK JOL, **not a built-in Java 17 command**; if JOL is not downloaded, the program will not run with only the JDK.

In traditional JOL output you might see:

~~~text
(object header: mark)       8 bytes
(object header: class)      4 bytes if narrowKlass
field Integer.value         4 bytes
Instance size               16 bytes in the illustrative configuration
~~~

This example is **conditional** data (64-bit HotSpot, compressed class pointers, and corresponding alignment). When changing JVM flags, field layout and padding may differ.

**Prefer measuring with JOL**, rather than using **System.getProperty("sun.arch.data.model")** and inferring reference width: a 64-bit process does not mean every object reference field is 8 bytes.

### 13.1. Fair experimental comparison

To test the impact of compression on memory footprint:

1. Use the same **JDK build**, same GC, and same dataset.
2. Enable compression and then disable compression in separate JVM processes.
3. Check the final **UseCompressedOops** and **UseCompressedClassPointers** flags.
4. Keep **-Xms/-Xmx**, ObjectAlignmentInBytes, and related parameters controlled.
5. Use JOL to measure the shallow size of specific objects/arrays.
6. Use heap histogram/profiler to measure retained graph sizes if needed.
7. Benchmark with proper warm-up and measurement methodology to observe throughput/latency, not inferring from a single small run.
8. Check GC allocation rates/pauses and RSS/native memory budget if memory is the goal.

**Which measurement is being compared?** Shallow size differs from retained size; allocated bytes differ from live heap; reserved memory differs from committed memory, which differs from RSS. Compressing references clearly affects certain types of storage, without making these metrics identical.

## 14. Impact on GC, CPU cache, and JIT

### 14.1. CPU cache and bandwidth

A pointer-heavy object graph is often traversed via dereference operations. With 4-byte narrowOop instead of 8-byte wide oop, reference-containing parts can be smaller:

- A cache line can hold more slots.
- More of the graph fits in L1/L2/L3.
- The VM/GC needs to read/write fewer reference bytes in some phases.

However, each dereference may need to compute **base + shift**, and the JIT compiler/CPU architecture may apply addressing optimizations to reduce the cost. Therefore, **compressing references does not mean speed doubles (2×)** or that every lookup has zero overhead.

### 14.2. GC barriers and object movement

GC can move Java objects; references must be updated/interpreted according to the proper encoding. Some collectors have different read/write barriers or load barriers, affecting execution paths while still preserving semantics.

Do not treat a compressed oop as **a 32-bit integer immutable with respect to object address** when GC moves objects. Representation and update logic are the runtime's responsibility. The encode/decode formula only helps understand the addressable range, not as an invitation to modify object references at the Java source level.

### 14.3. JIT can change how references are stored

Not every Java reference continuously resides in a 4-byte memory slot. The JIT may keep a reference in a CPU register, unbox/scalar-replace/eliminate object allocation under escape analysis conditions, or use intermediate formats. The compressed oops mechanism applies to **appropriate oop locations in the HotSpot implementation**, not as a rule that "every reference variable at every moment occupies exactly 4 bytes".

## 15. When does compression save less than expected?

1. **Objects have too few reference fields:** Savings are low; header reduction may be absorbed by alignment padding.
2. **Small objects with increased alignment:** If ObjectAlignmentInBytes is increased to 16/32 to support a larger range, average padding may increase.
3. **Application memory is mostly primitive arrays:** Reducing the width of oop slots has little direct impact on primitive elements.
4. **Application holds many byte[]/char[]:** Buffer contents are bytes/chars, not object-reference slots.
5. **Large native/direct buffers:** Compressed oops affect Java object refs, not automatically reducing **DirectByteBuffer native memory**, thread stacks, or code cache.
6. **Heap has few live objects:** Changing reserved capacity does not mean the actual graph footprint is large.
7. **Object sharing and dedup:** The actual ratio of objects and references matters more than just the number of class declarations.
8. **CPU arithmetic-heavy code:** Cache benefit may be small, encode/decode cost depends on VM/JIT.
9. **Heap requirement exceeds favorable compression range:** The VM may choose wide oops or require a different alignment configuration, introducing new trade-offs.
10. **Compressed class space becomes a bottleneck:** That is a matter of class metadata capacity/unloading, not automatically solved by reducing Java oop field width.

## 16. Distinguishing three commonly confused memory thresholds

| Threshold | What does it limit? | Related examples/flags |
| --- | --- | --- |
| **About 32 GiB with shift=3** | Theoretical addressable range of narrowOop with 8-byte scale | UseCompressedOops, ObjectAlignmentInBytes |
| **Java heap maximum** | Max heap level configured/chosen by JVM ergonomics | -Xmx, MaxHeapSize |
| **Compressed class space** | Region managing class metadata needed for narrowKlass encoding | UseCompressedClassPointers, CompressedClassSpaceSize |

A program with an 8 GiB Java heap does not need 8 GiB of compressed class space. A program with hundreds of thousands of generated classes can experience metadata pressure even when the live object heap is very small.

### 16.1. CompressedClassSpaceSize is not the limit for all metadata

HotSpot Metaspace has multiple structures/allocation types. The **compressed class space** is only one part related to narrowKlass. Increasing or decreasing **CompressedClassSpaceSize** does not mean the entire **Metaspace** is increased/decreased by that exact amount.

When seeing **OutOfMemoryError: Compressed class space** or **OutOfMemoryError: Metaspace**, look at class loading growth, class-loader retention, GC class unloading, and flags; avoid only changing -Xmx and concluding you tuned the right thing.

## 17. Distinguishing "oop" in the JVM from an ordinary Java object

HotSpot uses the term **oop** for its internal representation of Java heap references. This is not a Java source keyword:

~~~java
Object ref = new Object();
~~~

The variable **ref** has a Java reference type; the compiler/JVM manages the representation. In class files, **aload/astore/getfield/putfield/aaload/aastore** operate on JVM values/references according to the JVMS. Bytecode does not contain a separate field descriptor named **narrowOop**.

**There is no compressed reference descriptor:** A field of type **Object** still has descriptor **Ljava/lang/Object;**, and an Object[] array is still **[Ljava/lang/Object;** regardless of -XX:+/-UseCompressedOops.

Similarly, **Klass*** and **narrowKlass** are not Java source types, cannot be imported like normal Java API classes, and do not appear in **javap -s** as user-declared fields.

### 17.1. Class.getClassLoader() and the class pointer

A class is identified at runtime by its binary name and defining loader. When an object header carries a Klass metadata pointer, that metadata corresponds to the exact runtime class. However, from Java it can only be safely observed via:

~~~java
Class<?> type = object.getClass();
ClassLoader loader = type.getClassLoader();
~~~

This is Java-level Reflection. Do not use **getClassLoader().toString()** output as the native address of Klass; nor assume that the **Class object** and **Klass metadata** are the same object on the heap.

## 18. Common misconceptions

1. **"A 64-bit JVM requires every Java reference to occupy 8 bytes."** False in HotSpot with compressed oops.
2. **"Compressed oops make object addresses only 32 bits."** False: a 32-bit **encoded value** decodes to a native address that can be wider.
3. **"2^32 × 8 bytes is exactly 32 GB in all situations."** It is only the theoretical addressable range of 8-byte scaling; heap placement/flags/guards impose real constraints.
4. **"UseCompressedOops and UseCompressedClassPointers are the same flag."** False: two different types of pointers.
5. **"A class pointer is a reference to the java.lang.Class Java object."** False: it points to Klass metadata.
6. **"NarrowOop and narrowKlass use the same base/shift."** False: different target address spaces and encoding settings.
7. **"All heap objects shrink by exactly 4 bytes when class pointers are compressed."** False: alignment padding can keep shallow size unchanged.
8. **"All Java objects have a 12-byte header."** False: depends on mode, JDK, regular object/array, and implementation.
9. **"Object[1000] only takes 4000 bytes when compressed."** False: there are also the array header and alignment.
10. **"int[] is compressed to 2 bytes per int."** False: primitive element widths are not determined by UseCompressedOops.
11. **"The String.intern pool is the compressed class pointers region."** False: the two mechanisms are not related that way.
12. **"Just increasing -Xmx increases compressed class space."** False: the two regions/flags belong to different resources.
13. **"JOL describes the standard layout of every JVM."** False: JOL measures/estimates per VM, not replacing the JVMS.
14. **"Disabling compressed oops always increases performance by removing the shift."** False: cache/memory costs can exceed decode cost.
15. **"Enabling compressed oops always halves the heap."** False: effectiveness depends on the proportion of references, headers, padding, primitive data, and GC.
16. **"A Java object cannot be moved by GC because it has an encoded address."** False: HotSpot/GC updates references as needed.
17. **"You can read a compressed oop via System.identityHashCode."** False: the hash is not a memory address.
18. **"Class files have a narrowOop descriptor."** False: compression is a runtime implementation detail.
19. **"32 GiB is an absolute threshold that cannot be exceeded with compression."** False: object alignment can change the range, accompanied by trade-offs.
20. **"HotSpot Metaspace and Java heap are both controlled by -Xmx."** False: native metadata requires checking separate limits.

## 19. Exercises with answers

**Exercise 1.** On 64-bit HotSpot, if an Object reference field is stored as a 4-byte narrowOop, does the VM still use native 64-bit addresses?

**Answer:** Yes. The encoded narrowOop is a narrow representation; the VM can decode it into a full native address when used.

**Exercise 2.** With 8-byte alignment, what is the shift usually, and what is the theoretical addressable range?

**Answer:** Shift 3, because 2^3=8. Range 2^32×8 = 2^35 bytes, or 32 GiB.

**Exercise 3.** Why can increasing ObjectAlignmentInBytes=16 give a 64 GiB range in the formula yet waste memory?

**Answer:** Shift 4 corresponds to 16-byte scaling; every object must be aligned to a larger step, so padding/fragmentation can increase.

**Exercise 4.** What is the difference between narrowOop and narrowKlass?

**Answer:** NarrowOop encodes a reference to a Java heap object; narrowKlass encodes a pointer to the object's class metadata.

**Exercise 5.** In a traditional header with an 8-byte mark word and a 4-byte compressed klass pointer, what is the raw object header size?

**Answer:** 12 bytes before padding for a regular object in the hypothetical configuration.

**Exercise 6.** Why does Object[1000] not just have 1000×4=4000 bytes with compressed oops?

**Answer:** There are also the array header and alignment; for example, compressed klass+oop, alignment 8, array header 16 → 4016 bytes.

**Exercise 7.** A Point class has only two int fields. Why can it be 24 bytes in both wide and compressed klass modes?

**Answer:** Compressed header 12+8 primitive=20, rounded up to 24; wide header 16+8=24. Padding eliminates the difference.

**Exercise 8.** When reading **object.getClass()**, does Java receive Klass* or a Class<?> mirror?

**Answer:** It receives the **java.lang.Class mirror object**, not the raw native Klass*.

**Exercise 9.** If the JVM reports **OutOfMemoryError: Compressed class space**, what should you inspect?

**Answer:** Class metadata/class-loader growth, compressed class space budget, unloading, and native memory; not just increasing -Xmx.

**Exercise 10.** Does disabling compressed oops change the stdout of a program comparing references?

**Answer:** No, if the program is valid and under the same data conditions. Java reference identity semantics do not depend on internal width.

**Exercise 11.** On a 64-bit JVM with compressed oops, must a local variable of type Object occupy exactly 4 bytes on the native stack?

**Answer:** No. Locals in the JVM model, compiler registers, and native stack layout differ from object field/array element encoding.

**Exercise 12.** Can you measure object size accurately using **Holder.class.getDeclaredFields().length * 4 + 12**?

**Answer:** No. You must consider types, superclass fields, field arrangement, alignment, padding, and VM flags; use JOL/an appropriate profiler.

**Exercise 13.** Two different class loaders define the same class name. Must the header class pointer of instances point to the same Klass metadata?

**Answer:** No. These are different runtime classes, so their corresponding metadata differs.

**Exercise 14.** Does **-XX:+UseCompressedOops** guarantee that the final flag is enabled if the heap is too large or the configuration is incompatible?

**Answer:** Do not assume so. The runtime may warn, auto-adjust, or reject it; always check final flags and VM diagnostics.

## 20. Practical workflow and checklist

When evaluating compressed references for a HotSpot application:

1. **Identify the environment**: JDK build, 64-bit architecture, collector, OS, container limits, current flags.
2. **Read final flags**: UseCompressedOops, UseCompressedClassPointers, ObjectAlignmentInBytes, MaxHeapSize, CompressedClassSpaceSize.
3. **Analyze the workload**: many object references/arrays or mostly primitive buffers, off-heap memory?
4. **Take a specific class example**: calculate theoretical shallow size including header and padding; do not just sum reference widths.
5. **Use JOL/VM tools** to observe actual layout; do not turn hypothetical examples into production metrics.
6. **Measure performance** with benchmarks that include warm-up, throughput/latency, GC pauses, and memory footprint.
7. **Be cautious changing alignment**: expanding addressability can increase object padding.
8. **If a memory error occurs**: distinguish Java heap, Metaspace, and compressed class space.
9. **Avoid using internal pointers from Java**: do not equate HashCode, Java Class mirror, and Klass*.
10. **Note implementation dependency**: hotspot flags/layout vary by JDK, not a JVMS requirement.
11. **With plugins/dynamic class generation**, watch the number of classes/loaders and unloading capability; compressed class space can be exhausted even when the live heap is small.
12. **Verify correctness before optimizing**: changing flags must preserve Java code semantics and be tested on the target staging/runtime.

### Reference materials

- **Oracle Java SE 17 — The java Command**, especially UseCompressedOops, ObjectAlignmentInBytes, and VM flags: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **Oracle Java SE 17 GC Tuning — Other Considerations**, including class metadata and compressed class pointers: https://docs.oracle.com/en/java/javase/17/gctuning/other-considerations.html
- **Oracle HotSpot VM Performance Enhancements — Compressed Oops** (explaining mechanism, history): https://docs.oracle.com/en/java/javase/21/vm/java-hotspot-virtual-machine-performance-enhancements.html
- **OpenJDK JOL (Java Object Layout)**: https://github.com/openjdk/jol
- **OpenJDK HotSpot source — CompressedOops implementation**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/oops/compressedOops.hpp
- **JVMS Java SE 17 — Run-Time Data Areas**, to distinguish the JVM model from implementation layout: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5

**Core takeaway:** Compressed oops use **narrowOop** to represent many Java heap references via 32-bit encoded offsets; compressed class pointers use **narrowKlass** to shrink the class-metadata pointer part of the object header. Both can shrink the object graph, but they do not share the same target space, do not share the same meaning, and do not automatically guarantee optimization in every workload. **32 GiB is a common milestone from 32-bit × 8-byte scaling**, not an absolute answer; always measure actual object alignment, heap placement, and flags on the running HotSpot/JDK.
