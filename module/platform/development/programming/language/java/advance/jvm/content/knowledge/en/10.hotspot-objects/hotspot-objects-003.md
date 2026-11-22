# Object Header, Field Data, Alignment, and Padding in the HotSpot JVM

A **Java object** does not just occupy the exact sum of bytes of the fields declared in source code. In a common layout of the **HotSpot JVM**, an instance on the Java heap consists of an **object header**, **instance field data**, and possibly **padding** to satisfy **alignment** constraints. For an array, the header also needs to store the **array length**. The actual layout depends on the JVM, JDK version, 32/64-bit architecture, compressed references, alignment options, and mechanisms such as **Compact Object Headers**.

This lesson focuses on the **physical representation in HotSpot**, which should not be confused with the abstract contract of the Java Language Specification (JLS): the Java specification defines the semantics of fields, objects, arrays, and the memory model, but **does not require every JVM to use the same number of header bytes or the same field order**.

Objectives after reading:

1. Explain the **mark word**, **class pointer/klass word**, and **array length** in the object header.
2. Distinguish between instance fields, static fields, object references, and referenced objects.
3. Calculate illustrative object size examples when **assumptions are explicitly stated**.
4. Understand **internal padding**, **external/tail padding**, alignment, and their impact on memory when there are millions of objects.
5. Know how **compressed oops** differ from **compressed class pointers**.
6. Use Java 17+ and tools like **Java Object Layout (JOL)** or `Instrumentation.getObjectSize` to observe, instead of guessing from source code.
7. Recognize newer HotSpot configurations with **compact headers** so as not to rigidly apply old diagrams.

## 1. General model of an object

An **illustrative** diagram for a regular object on a 64-bit HotSpot with a classic header style:

```text
Increasing address →
┌───────────────────────────────────┐
│ Object header                     │
│   mark word                       │
│   klass / class pointer           │
├───────────────────────────────────┤
│ Instance fields                   │
│   primitive values                │
│   reference values                │
│   ...                             │
├───────────────────────────────────┤
│ Padding if needed                 │
└───────────────────────────────────┘
```

For an array, there is additional element count information:

```text
┌───────────────────────────────────┐
│ Header: mark + class information  │
│ Array length (int)                │
├───────────────────────────────────┤
│ Array elements [0 .. length-1]    │
├───────────────────────────────────┤
│ Padding if needed                 │
└───────────────────────────────────┘
```

**This is not an absolute layout.** HotSpot may arrange fields using its own strategy, use compact headers, compress different pointers, or change how metadata is placed. The diagram only helps separate responsibilities.

### Key terminology

| Term | Explanation |
| --- | --- |
| **object header** | The information part for the VM to manage the object, type identity, and related state |
| **mark word** | Metadata word about object state; encoding changes by JDK, synchronization locks, GC, and header mode |
| **klass word / class pointer** | Information identifying the runtime class/class metadata of the object in the classic header |
| **instance field data** | Values of instance fields, including primitive values or references |
| **internal padding / gap** | Empty/unused bytes between components due to field alignment/layout |
| **external/tail padding** | Bytes inserted at the end of the object so the total size reaches object alignment |
| **object alignment** | Constraint on object size/address according to an implementation alignment unit |
| **shallow size** | Size of the **object itself**, without following references to calculate the object graph |
| **retained size** | Memory that can be freed if the object is a dominator of other objects, depending on the heap analysis/tool |

**A reference is not the object data of the target object.** If `Node` has a field `Node next`, the body of `Node` contains a **reference value**; the fields of the `next` object reside in **another object**. Therefore, you cannot add the entire chain of nodes into the shallow size of the first node.

## 2. Object header in HotSpot: components and responsibilities

### 2.1. Mark word

In the traditional HotSpot header model, the **mark word** holds information for managing object state, related to:

- **Identity hash code**, when it is computed/recorded according to VM strategy.
- **Locking/synchronization state**, depending on the monitor mechanism and HotSpot version.
- **GC age** or appropriate marking/state information.
- Some other **status bits**; bit layouts may differ across JDK generations.

The mark word **is not simply a Java `int hash` field** that developers see via reflection. It is internal JVM data. Every object can carry the necessary information to implement `Object.hashCode()`/identity semantics and `synchronized`, but **not every object upon allocation already has a precomputed identity hash**.

```java
Object x = new Object();
int h = System.identityHashCode(x);
```

This is an illustrative snippet inside a method; `System.identityHashCode` requests the object's identity hash and may modify metadata state/storage paths appropriate to the VM. **The hash value is not a memory address** and is not guaranteed to be unique across all objects.

### 2.2. Klass pointer / class word

In the traditional layout, the header also contains **information pointing to runtime class metadata** (often called `klass` pointer or class word). This helps the JVM know:

- Which runtime class/interface/array type the object belongs to.
- The appropriate size/layout of the object and the path to access metadata.
- Information supporting method dispatch, type checks, GC scanning, and many internal tasks.

This **is not necessarily a Java field `Class<?> clazz` stored directly inside the object**. `obj.getClass()` returns the appropriate **`java.lang.Class` mirror**, but VM class metadata and the mirror are related structures that should not be equated in terms of address/layout.

Two instances of the same class can share class metadata, but **each instance has its own header** according to the header mode in use.

### 2.3. Header size depends on mode

A configuration commonly used to explain **64-bit HotSpot JDK 17**, with compressed class pointers enabled, is:

```text
Normal instance (classic header):
offset 0..7   : mark word      8 byte
offset 8..11  : class pointer  4 byte (compressed)
---------------------------------------
Total header                   12 byte
```

If **class pointers are not compressed**, in classic mode the class word can be **8 bytes** wide, and the header is typically **16 bytes** in a corresponding 64-bit HotSpot.

**These numbers are configuration-specific implementation examples, not mandatory object sizes for every Java 17/JDK.** Heap alignment, architecture, header mode, and additional components also determine the final shallow size.

### 2.4. Compact Object Headers: do not hardcode 12 or 16 bytes for all new JDKs

The **OpenJDK Lilliput** project researches and implements ways to reduce the overhead of object headers. In recent JDKs:

- **JDK 24** introduced **Compact Object Headers (Experimental)** under **JEP 450**.
- **JDK 25** moved this feature to a product option that can be enabled under **JEP 519**.
- With compact headers on supported 64-bit HotSpot, class information and marking metadata can be combined into an **8-byte** header structure, instead of the two 8 + 4 or 8 + 8 byte parts of the classic layout.
- The `-XX:+UseCompactObjectHeaders` option and default/support status may vary by JDK/vendor; **check the JDK currently in use** rather than assuming it is always on or off.

Therefore, the statement **“every Java object always has a 12-byte header”** is both inaccurate for 32-bit/uncompressed modes and no longer universally applicable to HotSpot with compact headers.

The effect of a smaller header is reducing overhead across a **very large number of objects**, increasing heap/cache density, and sometimes improving performance. It **does not eliminate** instance fields, object alignment, or Java's semantic rules.

## 3. Instance fields: which values actually reside in the object?

Consider the class:

```java
class Record {
    byte active;
    int count;
    long total;
    Object owner;
    static int globalCounter;
}
```

This is an **illustrative class that can be placed in `Record.java`**, not a program with `main`. The four fields `active`, `count`, `total`, `owner` are **instance fields**; `globalCounter` is a **static field**.

| Field | Belongs to instance body? | Information |
| --- | --- | --- |
| `byte active` | Yes | Primitive `byte` value |
| `int count` | Yes | Primitive `int` value |
| `long total` | Yes | Primitive `long` value |
| `Object owner` | Yes | **Reference** to another object, does not contain that entire object |
| `static int globalCounter` | **No** | State belonging to the runtime class, not added once per instance |

**Do not confuse `static` with “residing on the stack”.** Static fields are tied to the runtime class and the JVM's storage mechanism, not instance variables, nor are they copied as a separate field inside each object.

### 3.1. Primitive size by semantics and by layout

| Type | Java primitive data width | Common field size in HotSpot |
| --- | --- | --- |
| `boolean` | Logical boolean, no JLS requirement forcing a field to be 1 byte | Typically 1 byte for a field; arrays/VM modes have implementation rules |
| `byte` | 8 bits | 1 byte |
| `short` | 16 bits | 2 bytes |
| `char` | 16-bit unsigned UTF-16 code unit | 2 bytes |
| `int` | 32 bits | 4 bytes |
| `float` | 32 bits | 4 bytes |
| `long` | 64 bits | 8 bytes |
| `double` | 64 bits | 8 bytes |
| Reference | Reference to an object or null | Typically 4 bytes with compressed oops, can be 8 bytes when uncompressed |

The “common” column describes **how HotSpot places data**. It does not claim that total shallow size is just the sum of those numbers: there are also the header, field alignment, object alignment, inherited fields, and layout choices.

### 3.2. Field order in RAM is not necessarily source order

Example:

```java
class Mixed {
    byte a;
    long b;
    byte c;
    int d;
}
```

The source fields appear in the order `a, b, c, d`, but HotSpot can **reorder offsets** or utilize gaps to reduce padding. There is no Java language promise that `b` must start immediately after `a` in physical memory. `getfield`/`putfield` operations remain correct because the JVM knows the class's runtime layout.

Field layout is influenced by several factors:

- Size/alignment of each field.
- Superclass already having instance fields.
- Compressed reference/class pointer mode.
- The HotSpot version's field layout algorithm.
- Differences for contended fields or advanced runtime changes.

**Therefore, do not guess offsets and rely on them as a stable ABI.** Java reflection can retrieve fields by name, but provides no public contract for their raw byte offsets.

### 3.3. Inherited instance fields still contribute to the object

```java
class Parent {
    int parentCount;
}

class Child extends Parent {
    long childTotal;
}
```

A **`Child` instance** needs to store both the inherited instance state of `Parent` and the fields of `Child`, plus header/padding. **There are not two independent object headers** for the parent part and child part when it is a single `Child` instance.

`new Child()` creates **one object** of runtime class `Child`, not a separate `Parent` object inside it in the sense of two allocations. The parent constructor is called in the constructor chain to initialize that object's fields.

## 4. Alignment: why can an object be larger than the sum of field widths?

**Alignment** is the requirement to align an object's address/size to a specific unit of the VM. On 64-bit HotSpot, an **8-byte object alignment** configuration is commonly encountered, though `-XX:ObjectAlignmentInBytes` can change alignment to supported values.

When the sum of header + fields is not divisible by the alignment, the JVM may need **padding**.

Illustrative formula:

```text
rawSize      = headerBytes + fieldRegionBytes + layoutGapsBytes
alignedSize  = roundUp(rawSize, objectAlignment)

roundUp(n, a) = ((n + a - 1) / a) * a
```

In the formula, division is integer division with `a > 0`; it is only used to solve the problem **after** the layout is known. If the JVM reorders fields or uses compact headers, the inputs to the formula must change accordingly.

### 4.1. Example of an object with one `int`

Assume:

- 64-bit HotSpot, classic header **12 bytes** (mark 8 + compressed klass 4).
- `int` placed right after the header, occupying **4 bytes**.
- Object alignment = **8 bytes**.
- No other gaps.

```text
offset  0.. 7 : mark word       8 B
offset  8..11 : class word      4 B
offset 12..15 : int value       4 B
-------------------------------
raw / aligned size            16 B
```

An object with only **4 bytes of field data** in this model still takes **16 bytes of shallow size** because it must store the header.

### 4.2. Example of an object with no instance fields

Still with a 12 B classic header and 8 B alignment:

```text
offset  0.. 7 : mark word             8 B
offset  8..11 : class word            4 B
offset 12..15 : tail padding          4 B
-----------------------------------------
shallow size                       16 B
```

The 12 B header total is rounded up to **16 B**. Thus, “`new Object()` has no fields so it takes 0 bytes” is wrong. However, **16 B is not a universal object size**; compact header configurations make this example different.

### 4.3. Example with a `long` and a gap

Assume a 12-byte classic header, a `long` field taking 8 B that must be placed at a multiple-of-8 offset:

```text
offset  0.. 7 : mark word             8 B
offset  8..11 : class word            4 B
offset 12..15 : alignment gap         4 B
offset 16..23 : long value            8 B
-----------------------------------------
total                                24 B
```

For a class with only one `long`, this is a **reasonable illustrative layout** on classic 64-bit HotSpot. Do not take it as proof that a JVM never reorders or inserts other fields into the gap. When there are multiple fields, the VM can utilize the empty space instead of losing all of it.

### 4.4. Field packing example

Assume a layout with a 12 B header that needs to place an `int` and a `long`. If `int` fills positions 12..15 before `long` at 16..23, the total is **24 B**:

```text
[header 12][int 4][long 8] → 24 B
```

If another layout introduces an additional gap, the total could be higher. That is why **placement order matters**, yet Java source does not guarantee raw offset order. Use JOL or a reliable tool for the **executing JVM** instead of claiming every `int+long` always has an invariant size.

## 5. What types of padding exist?

| Type | Location | Cause |
| --- | --- | --- |
| **Header-to-field gap** | Between header and first field | Field requires stricter alignment than the offset after the header |
| **Internal padding** | Between fields | Field layout/alignment to place the next field |
| **Tail/external padding** | End of object | Rounds total object size up to an alignment multiple |
| **Array padding** | After the last elements or gap before the first element | Element base offset / total array size needs alignment |

Padding bytes **are not** Java fields; normal reflection does not return them as a `Field`. Depending on the VM, padding byte contents should not be interpreted as meaningful data. Do not design programs depending on them containing all zeros or retaining stable values across GC.

### Why does padding matter when an application has millions of objects?

Suppose there are **1,000,000 objects** and a layout change reduces the average shallow size by **8 bytes/object**:

```text
1,000,000 × 8 byte = 8,000,000 byte
```

This is equivalent to about **7.63 MiB** of data in binary conversion. This is only a **shallow footprint estimation exercise**; total retained memory also depends on references, the object graph, arrays, allocator/GC overhead, and other runtime factors.

When data is small but each item is a separate object, the ratio of header + padding can be large. For example, **one million boxed objects** holding individual primitive values can have higher overhead than using **one primitive array** if access/synchronization requirements allow. You should not optimize every program into primitive arrays regardless of semantics, but understanding layout helps reveal the difference.

## 6. Reference fields: compressed oops and compressed class pointers

### 6.1. Two pointer types with different roles

**Compressed ordinary object pointers (compressed oops)** is a 64-bit HotSpot mechanism that can represent object references in certain locations as shorter values, typically **4 bytes**, instead of 8-byte raw native pointers.

**Compressed class pointers** is a separate mechanism to represent references from the header/class metadata in a compact way, typically **4 bytes in the classic header**. The two mechanisms are related but **are not a single identical flag/concept**.

| Case | What is compressed (classic model) | Example places observed |
| --- | --- | --- |
| Compressed oops | Reference values to Java objects | Field `Object child`, elements of `Object[]` |
| Compressed class pointers | Reference to class metadata in the object header | Class/klass word of an ordinary object |
| Compact Object Headers | Reorganizes header information, combining metadata in a new mode | Object header of supported JDKs |

Running a 64-bit Java process **does not force every reference field to be 8 B**. Conversely, a class having an 8 B `long` field does not imply the header is using an 8-byte class pointer.

### 6.2. `-XX:+UseCompressedOops` does not turn `long` into 4 bytes

Compressing object pointers only affects the representation of eligible references; **it does not shrink `long` or `double` from 64 bits to 32 bits**. The result of a Java `long` expression still has exact JLS semantics.

Changing compressed oops can cause the shallow size of:

```java
class Node {
    Object left;
    Object right;
}
```

to differ, because the two reference fields may have different physical sizes. However, field order, header mode, and padding can also have an effect; you cannot simply add `2 × (8 - 4)` and claim an exact 8 B difference for every JVM.

### 6.3. Why are compressed references beneficial?

A heap containing many object references can significantly reduce its footprint when references take 4 B instead of 8 B. Common benefits:

- Fewer bytes for fields and arrays containing references.
- Data fits better in CPU caches, which can help locality.
- In some cases, reduced memory pressure, GC, and bandwidth.

In return, the JVM needs **decode/encode** logic for references and is affected by the heap range addressable by the compressed scheme; enabling/disabling is usually decided by ergonomics, heap size, and VM flags.

With JDK 17 HotSpot, you can inspect the actual flags:

```bash
java -XX:+PrintFlagsFinal -version
```

Look for `UseCompressedOops`, `UseCompressedClassPointers`, and `ObjectAlignmentInBytes`. **These are HotSpot flags**, which may change or be deprecated in newer JDKs; check the JDK you are running instead of copying flags from old blogs.

## 7. Arrays: header, length, and contiguous elements in JVM layout

Java arrays are objects with a **fixed length**. The same array class `int[].class` can have instances of length 0, 3, or 1,000; length belongs to the **array object**, not the `int[]` type.

In the classic **64-bit HotSpot layout with compressed class pointers**, a common model for arrays is:

```text
offset  0.. 7 : mark word       8 B
offset  8..11 : klass word      4 B
offset 12..15 : array length    4 B
offset 16..   : elements
...           : padding depending on total size
```

Thus, the illustrative array header has **16 bytes** before the element region. This **is not** a mandatory rule for compact headers, uncompressed modes, or other JVM architectures. In some modes, there is a gap between length and elements to ensure element alignment, especially for wide element types.

### 7.1. `int[]` example and 8 B alignment

Assuming a 16 B header, each `int` element 4 B, object alignment 8 B:

| Array | Header | Elements | Raw size | Aligned size |
| --- | ---: | ---: | ---: | ---: |
| `new int[0]` | 16 B | 0 B | 16 B | 16 B |
| `new int[1]` | 16 B | 4 B | 20 B | 24 B |
| `new int[2]` | 16 B | 8 B | 24 B | 24 B |
| `new int[3]` | 16 B | 12 B | 28 B | 32 B |
| `new int[4]` | 16 B | 16 B | 32 B | 32 B |

**This is a calculation based on assumptions**, not a `getObjectSize` result guaranteed on every HotSpot. If alignment changes to 16 B or the array header changes, the results must be recalculated.

### 7.2. `Object[]` differs from `int[]`

For `Object[]`, each element is a **reference value**, which may take 4 B when compressed oops is enabled or 8 B when disabled. **The contents of the object pointed to by the reference do not reside inside the array element in terms of shallow layout**.

```java
Object[] arr = new Object[2];
arr[0] = new byte[1024];
arr[1] = "hello";
```

This is an illustrative snippet inside a method. The shallow size of `arr` consists of the header + **two reference slots** + padding. It **does not** add the 1,024 bytes of the `byte[]` array and the `String` data. To know the total object graph, you need a tool that measures deep/retained size or analyzes the reference graph.

### 7.3. Multidimensional arrays are actually arrays of arrays

```java
int[][] matrix = new int[2][3];
```

In the Java model, this is **one outer array** containing references to **two inner int[] arrays**. Total memory is not just one 16 B header plus `2 × 3 × 4`: each inner `int[]` is also an object with **its own header and padding**.

```text
outer int[][]  ──►  [ ref0 | ref1 ]
                        │      │
                        ▼      ▼
                     int[3]  int[3]
                      object  object
```

The two inner arrays are distinct objects, allowing each row to have a different length. If you create `new int[2][]`, the outer array is allocated, but the two references are initially `null`; there are no inner arrays until the program creates them.

## 8. Calculating shallow size correctly: what to measure and what not to measure?

**Shallow size** represents the memory allocated for a single object as measured by a JVM/tool. It typically includes the header, instance fields or array elements, gaps, and tail padding; it does not recurse into other referenced objects.

**Deep size** is typically the total size of the reachable object graph as defined by the tool; **retained size** is the amount of memory that could be freed if the object and all objects only reachable through it became unreachable. These two concepts are not synonymous:

```text
A ──────► B ◄────── C
```

If `B` is still reachable via `C`, dropping `A` does not free `B`. Thus `A` can “deep traverse” to `B`, but does not necessarily **retain** `B` according to the dominator algorithm.

### Example of a node with a reference

```java
class Node {
    int value;
    Node next;
}
```

The shallow size of `new Node()` includes the header, `int`, `next` reference, and padding. A list of 1,000 nodes has a footprint coming from **1,000 separate objects**, each with header and alignment overhead; there may also be allocation/GC metadata at the heap region level. You cannot take the shallow size of a node and claim the exact retained size of the entire list when there are references from elsewhere.

### `String` and collections also have auxiliary structures

A `String` object in modern HotSpot typically has fields to represent character data, and the actual data may be in **another array object**. `ArrayList` can also reference a backing array. Therefore, measuring the shallow size of `String` or `ArrayList` **does not automatically measure the entire payload**. Private field structures of the JDK can change across releases; use a heap profiler or JOL matching the version instead of relying on a layout extracted from an old JDK.

## 9. Do identity hash, synchronized, and GC change the layout?

Runtime features interact with the header/metadata, but should not be equated with Java fields:

- **`System.identityHashCode(obj)`:** requests the identity hash according to VM rules. This method does not return the object's address, and values can collide between two objects.
- **`synchronized(obj)`:** executes monitor enter/exit according to the Java Memory Model. HotSpot has different lightweight locking/inflation/monitor metadata mechanisms depending on the JDK. Do not assume a fixed “biased locking” bit pattern for all current HotSpot versions.
- **Garbage collection:** objects can move in the heap; the collector needs to determine object size, which fields are references, and metadata supporting GC. That information can come from the object header and runtime class metadata.
- **Class loading/unloading:** class metadata and class mirrors are managed by the JVM; each object does not contain a full copy of bytecode or the method table.
- **Compact header mode:** changes in header organization can affect how lock/hash/GC metadata is handled.

You should not read raw mark words from a Java application using unverified offset access; this kind of operation depends on VM internals and can change during GC, hash calculation, lock transitions, or JDK upgrades.

## 10. Observing HotSpot layout with Java Object Layout (JOL)

**JOL (Java Object Layout)** is an OpenJDK tooling project used to observe object layout, offsets, and sizes on an actual JVM, or to simulate certain configurations. It is more suitable than manually adding field sizes if you need results for a specific JVM.

Project: https://openjdk.org/projects/code-tools/jol/  
Repository and CLI guide: https://github.com/openjdk/jol

When you **have the appropriate JOL CLI installed/available**, an example command:

```bash
java -jar jol-cli.jar internals java.lang.Integer
```

`jol-cli.jar` is an **illustrative filename**; replace it with the JOL JAR name/path you actually have. Some JOL CLI releases come with a versioned name or a `-full.jar` suffix. Do not run the command above without having the JAR.

Output may include:

```text
OFF  SZ   TYPE   DESCRIPTION
0    8           (object header: mark)
8    4           (object header: class)
12   4    int    Integer.value

Instance size: 16 bytes
Space losses: ...
```

This is an **abbreviated sample description** for a 64-bit HotSpot with classic header and compressed class pointers; it is not a fixed `jol` output. If run on a JDK with compact headers or different flags, offsets/instance size may differ.

### Reading `OFF`, `SZ`, `Instance size`, and `Space losses`

- **`OFF`:** byte offset from the start of the object in the presented layout.
- **`SZ`:** size of the corresponding item (bytes).
- **`DESCRIPTION`:** header, field, array element, or padding/gap.
- **`Instance size`:** shallow size of the instance according to the tool's measurement/model.
- **`Space losses`:** unused bytes due to gaps/tail padding as reported.

JOL may require appropriate permissions/agent to access exact layouts on newer JDKs. If a tool mode only provides an **estimate/simulation**, note clearly that it **is not a guaranteed measurement of every live object**.

### Do not confuse object header and field offsets with source field ordering

When JOL prints field `long b` at offset 16 even though `byte a` was declared first, that does not permit a program to rely on offset 16 as a public ABI. The layout is an internal contract of the HotSpot in use and can change on the next launch with different flags or a JDK upgrade.

## 11. Standalone Java 17+ example: distinguishing object, class, field, and array

Create the file **`ObjectLayoutBasics.java`**:

```java
public class ObjectLayoutBasics {
    static class Empty {}

    static class Data {
        byte flag = 1;
        int number = 42;
        Object reference = new Object();
        static int shared = 100;
    }

    static class Parent {
        int parentValue = 7;
    }

    static class Child extends Parent {
        long childValue = 9L;
    }

    public static void main(String[] args) {
        Data first = new Data();
        Data second = new Data();
        int[] array = new int[3];
        Child child = new Child();

        System.out.println("different instances: " + (first != second));
        System.out.println("same class: "
                + (first.getClass() == second.getClass()));
        System.out.println("flag and number: "
                + first.flag + ", " + first.number);
        System.out.println("different nested objects: "
                + (first.reference != second.reference));
        System.out.println("static shared: " + Data.shared);
        System.out.println("instance fields declared: "
                + Data.class.getDeclaredFields().length);
        System.out.println("empty declared fields: "
                + Empty.class.getDeclaredFields().length);
        System.out.println("child fields: "
                + child.parentValue + ", " + child.childValue);
        System.out.println("array length: " + array.length);
        System.out.println("array class name: "
                + array.getClass().getName());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 ObjectLayoutBasics.java
java ObjectLayoutBasics
```

**Exact standard output:**

```text
different instances: true
same class: true
flag and number: 1, 42
different nested objects: true
static shared: 100
instance fields declared: 4
empty declared fields: 0
child fields: 7, 9
array length: 3
array class name: [I
```

### Explanation

1. `new Data()` creates separate instances, but both have the same runtime class.
2. `Data.shared` is a **static field**, not occupying a separate instance body slot per `Data`. However, `getDeclaredFields()` lists **both static and instance fields**, so `Data` has **4 declared fields**; this number **is not the number of instance fields**.
3. `reference = new Object()` creates a **different object for each Data** in the example; Data only stores a reference to that object. The shallow size of Data does not add the `reference` object just because it is reachable.
4. `Child` can access `parentValue` from its superclass and its own `childValue`; in a Child instance, those are fields of the same object.
5. The `int[3]` array has an array header, three `int` elements, and layout-dependent padding. `[I` is the runtime name of the `int[]` array type as represented by `Class.getName()`.

This demo **does not print addresses or shallow size**, because standard Java SE APIs do not guarantee raw object layout. The experiment in the next section uses `Instrumentation` to measure on a real JVM.

## 12. Measuring shallow size with `Instrumentation.getObjectSize`

The Java Instrumentation API has the `getObjectSize(Object)` method, which retrieves an **implementation-dependent approximation of the memory consumed by an object**. It requires a **Java agent** with `premain` supplied via `-javaagent`; there is no need to use the internal `sun.misc.Unsafe` API or assume header offsets.

This method **does not sum all objects reachable** from the measured object, and the result is not an invariant ABI/GC retained-size contract.

### 12.1. Create the agent `ShallowSizeAgent.java`

```java
import java.lang.instrument.Instrumentation;

public class ShallowSizeAgent {
    private static Instrumentation instrumentation;

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;
    }

    public static long sizeOf(Object value) {
        if (instrumentation == null) {
            throw new IllegalStateException("Start with -javaagent");
        }
        return instrumentation.getObjectSize(value);
    }
}
```

### 12.2. Create the program `SizeExperiment.java`

```java
public class SizeExperiment {
    static class Empty {}

    static class OneInt {
        int value;
    }

    static class OneLong {
        long value;
    }

    static class HasReference {
        Object child = new byte[1000];
    }

    private static void show(String name, Object value) {
        System.out.println(name + " shallow: "
                + ShallowSizeAgent.sizeOf(value));
    }

    public static void main(String[] args) {
        show("Empty", new Empty());
        show("OneInt", new OneInt());
        show("OneLong", new OneLong());
        show("HasReference", new HasReference());
        show("int[0]", new int[0]);
        show("int[3]", new int[3]);
        show("byte[1000]", new byte[1000]);
    }
}
```

### 12.3. Create the manifest for the agent

Create a UTF-8/ASCII text file named **`manifest.mf`**:

```text
Premain-Class: ShallowSizeAgent

```

A **trailing blank line at the end of the manifest** is required per JAR manifest structure. In the directory containing the above files, run:

```bash
javac -encoding UTF-8 ShallowSizeAgent.java SizeExperiment.java
jar cfm shallow-agent.jar manifest.mf ShallowSizeAgent.class
java -javaagent:shallow-agent.jar SizeExperiment
```

If the JAR filename is different, replace it accordingly. `-javaagent` is the standard Java Instrumentation API mechanism; the two demo classes require no external libraries.

### 12.4. Results and how to read them

The program prints 7 lines in the format:

```text
Empty shallow: <bytes>
OneInt shallow: <bytes>
OneLong shallow: <bytes>
HasReference shallow: <bytes>
int[0] shallow: <bytes>
int[3] shallow: <bytes>
byte[1000] shallow: <bytes>
```

**This is a format template, not exact stdout**: the `<bytes>` values are determined by the actual JVM. With a 64-bit HotSpot configuration of classic header + compressed pointers + 8 B alignment, you **may** see sizes matching the models calculated in sections 4/7. If the JDK has compact headers enabled or different alignment, the measurements may change.

Things to verify from the measurements:

- `Empty` has a **non-zero** shallow size due to object header/alignment.
- `HasReference` only includes the **reference field**, not adding the entire referenced `byte[1000]`.
- `byte[1000]` is **another array object**, with header + 1000 elements + padding.
- `int[3]` has more elements than `int[0]`, but the change after alignment may not be exactly 3 × 4 B.
- `OneLong` and `OneInt` may have equal or different shallow sizes depending on header/gaps/alignment; do not conclude solely from primitive width.

**Why not write a fixed set of stdout numbers?** `getObjectSize` returns an *implementation-specific approximation*; JVM implementations and options can make the output differ. A quality README must distinguish between a **valid template** and a **guaranteed result**.

### 12.5. Try changing alignment to compare

With HotSpot JDK 17 supporting the flag:

```bash
java -XX:ObjectAlignmentInBytes=16 -javaagent:shallow-agent.jar SizeExperiment
```

When changing object alignment, some shallow sizes may increase because the object total must be rounded up to a larger multiple. Do not run this flag blindly on production applications; this exercise is only for test processes, and the flag can affect heap ergonomics.

If you want to test compressed oops mode, first **check the flags of the JDK version currently in use**. Do not assume the same parameters are always supported or have the same effect after major changes in JVM layout.

## 13. Measuring layout vs. heap profiler: which tool answers which question?

| Question | Suggested tool | Limitations |
| --- | --- | --- |
| What fields, offsets, and padding does an object have? | **JOL** | Depends on VM/JDK/options; may need an agent to verify |
| Roughly how many shallow bytes does an object occupy? | **Instrumentation.getObjectSize** | Implementation-dependent estimate, does not count referenced graph |
| Which object classes are occupying the most heap? | `jcmd PID GC.class_histogram`, heap profiler | Histograms typically aggregate by class, do not show individual object layout |
| Which objects are retaining data not being GC'd? | Heap dump + dominator tree | Requires understanding GC roots/retained size; heap dumps can be resource-intensive |
| Current heap and native footprint? | JVM metrics, JMX, NMT, OS monitoring | Do not mix reserved/committed/RSS/shallow |
| What is the header mode/heap alignment? | HotSpot flags, JOL VM details | Do not use assumptions from another machine |

JDK 17 HotSpot diagnostic examples:

```bash
java -XX:+PrintFlagsFinal -version
jcmd -l
jcmd PID GC.class_histogram
```

In the last line, **replace `PID` with the actual process number**; do not run arbitrarily in production because a class histogram can incur time/safepoint overhead. For a simple application wanting to know offsets/field packing, **JOL** is usually more suitable than a histogram.

### Do not use `Runtime.totalMemory()` to infer exact object size

`Runtime.getRuntime().totalMemory() - freeMemory()` approximates the heap in use as a snapshot, but allocating an object can coincide with GC/TLAB refill/class loading or other allocations. Taking the difference of two calls is not an accurate shallow size measurement. To study layout, prefer instrumentation/JOL.

## 14. False sharing, `@Contended`, and advanced padding overhead

Sometimes concurrency programming wants to **increase memory distance** between fields or counters to reduce **false sharing** between CPU cores. HotSpot has internal mechanisms/annotations like `@Contended` and version-dependent supporting flags that can introduce **intentional padding** into the object layout.

This goes against the goal of “smallest packing”, but can improve throughput in some multi-threaded workloads. You should not hastily treat every padding byte as a design flaw to be eliminated:

- **Alignment padding** serves valid/efficient data placement.
- **Contended padding** can be a performance strategy for data shared across threads.
- The benefit of a change must be confirmed with **proper benchmarking**; adding padding increases memory footprint.

In JDK 17, `jdk.internal.vm.annotation.Contended` is a module-internal API, not a standard Java SE API. **It is not recommended** to add it to application code based solely on this lesson; support, encapsulation, and JDK version must be evaluated.

## 15. Object layout does not determine everything about performance

A smaller shallow size can reduce heap pressure, cache misses, and GC work, but **does not automatically guarantee** a faster program. Other factors include:

- **Object allocation rate**: how many objects are created/second.
- **Object lifetime**: whether objects die young or live long.
- **Memory locality**: whether data is accessed sequentially or across a reference graph.
- **Escape analysis/scalar replacement**: the JIT can eliminate or replace some physical allocations while preserving semantics.
- **GC algorithm**: collectors have their own ways of managing regions/compaction and overhead.
- **Synchronization**: lock contention and runtime metadata affect throughput.
- **Data structure choice**: `int[]` differs from `List<Integer>` in boxing, references, and cache locality potential.

**Important point when benchmarking:** if the JIT proves an object does not need to be physically allocated in optimized code, using a simple benchmark with `new Object()` in a loop may not measure the object allocation the author thinks it is measuring. Use JMH/profilers when evaluating real performance.

### Primitive array and boxed objects

Compare:

```java
int[] values = new int[1000];
```

with:

```java
Integer[] boxed = new Integer[1000];
```

In the first array, each element directly holds an `int` value. In the second array, each element is a **reference** to an `Integer` object or `null`, and individual `Integer` objects have their own overhead. However, you cannot simply say every element of `Integer[]` definitely has its own separate object, because boxing caches/reference sharing can occur. Choosing a structure depends on semantics, nullability, API, and performance.

## 16. Common misconceptions

| Misconception | Correct understanding |
| --- | --- |
| “A Java object only occupies the sum of its field sizes.” | There are also the header, layout gaps, and padding |
| “`new Object()` has no fields so its size is 0.” | The object still has header and alignment overhead per the VM |
| “Every 64-bit HotSpot has an exact 12-byte header.” | Classic compressed 12 B is an example; uncompressed/compact/other JDKs have different layouts |
| “The mark word is the object's address.” | The mark word is metadata, not the address returned by `identityHashCode` |
| “`identityHashCode` is always unique across all objects.” | Hash collisions can occur; do not use it as an absolute identifier |
| “The klass pointer is an instance field `Class<?> clazz`.” | The header uses internal metadata; the class mirror is a related API, not a source field |
| “A static field costs an extra 4/8 B for **each** instance.” | Static state is tied to the class, not the private field data of every object |
| “`Object ref` contains the entire target object.” | It contains a reference value to another object |
| “A `boolean` field is always defined by the JLS as 1 byte.” | Physical layout is a JVM detail; HotSpot commonly uses 1 B for a field |
| “Field source order is the byte offsets.” | HotSpot can reorder/pack fields |
| “Object alignment only affects performance, not size.” | Alignment rounds object size up and can increase padding |
| “A `Child` object has two headers because it has `Parent`.” | One runtime object of class Child contains inherited fields, not two parent/child allocations |
| “`int[][]` only has one header.” | Each outer/inner array is an object with its own header |
| “`String` shallow size is the entire memory of the string.” | The payload can be in another referenced array/object |
| “JOL output on another machine is a stable Java ABI.” | Different JVMs/JDKs/flags can change offsets/sizes |
| “`getObjectSize` counts the entire object graph.” | It measures a **shallow estimate** of one object |
| “GC definitely leaves objects at a fixed address.” | Moving collectors can relocate objects; raw addresses are not Java-level stable identity |
| “Compact headers make objects need no metadata.” | Metadata is represented differently/compactly; the JVM still must manage type and state |

## 17. Exercises and solutions

### Exercise 1 — Empty class

**Assumption:** 64-bit HotSpot classic compressed header 12 B, alignment 8 B, class with no fields.  
**Question:** Illustrative shallow size?

**Answer:** `roundUp(12, 8) = 16 B`. Padding is 4 B; do not claim that a JDK with compact headers enabled also has this size.

### Exercise 2 — One `int`

**Assumption:** same JVM as Exercise 1; `int` is placed at offset 12.  
**Answer:** `12 + 4 = 16 B`, already 8 B aligned, no tail padding needed.

### Exercise 3 — One `long`

**Assumption:** mark 8 B + compressed class word 4 B, `long` field must start at offset 16 and alignment is 8 B.  
**Answer:** 4 B gap before long, long 8 B, total **24 B**.

### Exercise 4 — `int[3]` array

**Assumption:** array header 16 B, each int 4 B, alignment 8 B.  
**Answer:** raw 16 + 12 = 28 B; aligned **32 B**, 4 B tail padding.

### Exercise 5 — `int[2]` array

**Assumption:** same as Exercise 4.  
**Answer:** 16 + 8 = **24 B**, divisible by 8; no tail padding needed.

### Exercise 6 — An array of references

**Assumption:** array header 16 B, 3 compressed reference elements 4 B each, alignment 8 B.  
**Answer:** 16 + 3 × 4 = 28 B, aligned **32 B**. Does not add the shallow size of referenced objects.

### Exercise 7 — Static field

```java
class Example {
    int a;
    static int total;
}
```

**Question:** Does the `total` field increase the shallow size of each `new Example()` by an `int`?  
**Answer:** No. It is tied to the runtime class, not each instance.

### Exercise 8 — Inheritance

```java
class A { int a; }
class B extends A { int b; }
```

**Question:** How many object headers does `new B()` have within that same object?  
**Answer:** One under the typical HotSpot model; parent fields and child fields belong to one runtime object, without creating a separate A object.

### Exercise 9 — Two references

```java
class Holder {
    Object x;
    Object y;
}
```

**Question:** If both fields point to the same object, does the shallow size of Holder decrease?  
**Answer:** No, because there are still two field slots holding references. Deep/retained analysis changes depending on aliasing and the object graph.

### Exercise 10 — Layout and JDK version

**Question:** Must the size of `new Object()` observed with JOL on HotSpot JDK 17 compressed header be the same as HotSpot running Compact Object Headers on a newer JDK?  
**Answer:** No. Header representation changes; it must be measured on the exact JVM/configuration.

### Exercise 11 — Padding bytes

**Question:** Can you use reflection `getDeclaredField("padding")` to automatically get an object's tail padding?  
**Answer:** No. Padding is not a Java field declared in the class; only layout tools display it.

### Exercise 12 — Heap diagnosis

**Question:** A heap profiler shows millions of `Node` objects. Should you just measure the size of one `Node` and conclude the total retained heap?  
**Answer:** Not yet. You need to look at references, auxiliary arrays, actual counts, the object graph, dominators, GC roots, and class loaders to determine retained/allocated memory.

### Exercise 13 — Reference field

**Question:** When compressed oops is enabled, an `Object x` field is typically 4 B. If `x` points to `byte[1000]`, does `Holder` contain over 1,000 B inside its own body?  
**Answer:** No. `Holder` contains the reference field; the array is a separate object with its own header/payload.

### Exercise 14 — Different alignment

**Assumption:** raw object size 20 B, alignment changes from 8 B to 16 B.  
**Answer:** `roundUp(20, 8) = 24 B`; `roundUp(20, 16) = 32 B`. This is an arithmetic exercise after knowing the raw layout; the JVM may change layout when changing modes, so actual measurements need confirmation.

## 18. Summary

Foundational model:

```text
Ordinary object (generalized HotSpot layout):
    object header
  + instance field values
  + internal/tail padding
  = shallow footprint of the object (per VM)

Array object:
    array header + length metadata
  + array element slots
  + padding
  = shallow footprint of the array

Object graph:
    many objects/arrays linked by references
  → deep/retained size is NOT the shallow size of one object
```

The **mark word** serves object state metadata, **class/klass information** helps the JVM identify runtime type and layout; **field data** is instance-specific values, not containing the class's static fields or the entire objects that references point to. **Padding** appears due to field/object alignment. Improvements such as **compressed oops**, **compressed class pointers**, **Compact Object Headers**, and field packing can significantly change the footprint when there are millions of objects.

To learn/verify properly, **always state the assumptions of 64-bit/32-bit JVM, JDK version, header mode, compressed references, and object alignment**, then use **JOL** or **Instrumentation.getObjectSize** on the actual runtime. Do not turn a 12-byte header diagram from old HotSpot documentation into a rule for every Java version.

### References

- **OpenJDK Java Object Layout (JOL):** https://openjdk.org/projects/code-tools/jol/ and https://github.com/openjdk/jol — tool to inspect object headers, field offsets, instance sizes, and padding.
- **OpenJDK JEP 450 — Compact Object Headers (Experimental):** https://openjdk.org/jeps/450 — JDK 24.
- **OpenJDK JEP 519 — Compact Object Headers:** https://openjdk.org/jeps/519 — JDK 25.
- **Oracle JDK 17 — java command options:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html — HotSpot flags `ObjectAlignmentInBytes`, `UseCompressedOops`, and logging tools.
- **Java SE 17 `Instrumentation.getObjectSize`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#getObjectSize(java.lang.Object) — size estimate contract, not deep size.
- **HotSpot source (implementation):** https://github.com/openjdk/jdk/tree/master/src/hotspot/share/oops/ — object header, mark word, and metadata structures. Details in `master` may differ from JDK 17; when exact verification is needed, check the corresponding branch/release.

**Key takeaway:** A Java object has **JVM overhead**, and the actual bytes occupied in the heap are not determined solely by the list of fields in `.java`. Grasping **header — fields — alignment — padding**, and then measuring on the actual HotSpot, will help you understand footprint, optimize data structures, and avoid false guesses when debugging heap memory.