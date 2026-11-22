# How References Are Updated When GC Moves Objects in HotSpot

In Java, you can hold multiple variables pointing to **one object**, pass it across many methods, put it into an array, collection, or field, and the system can still read that object after Garbage Collection (GC) cycles. However, in many HotSpot collectors, some **live objects are copied or moved to new heap addresses**. How do all references continue to work? Why is `a == b` still `true` even though the bytes representing the reference may change? And when does a collector actually rewrite a reference slot, versus when does it use forwarding or barriers?

**Key point:** A Java reference is how the program refers to **the same logical object**, not a promise of a fixed physical address. When a collector moves objects, HotSpot uses object-tracking structures and reference update/redirection mechanisms so that Java code always sees the right object. The specific method depends on the collector, GC phase, and JDK version.

This lesson focuses on **HotSpot Java 17**, especially the G1 evacuation mechanism, while also pointing out the difference in reference update timing between stop-the-world collectors and concurrent relocating collectors such as ZGC or Shenandoah. When talking about GC roots, `oop`, forwarding pointers, load/write barriers, or remembered sets, these are **HotSpot implementation details**, not a raw reference representation guaranteed by the Java Language Specification (JLS).

## 1. The core problem: “moving an object” vs. “changing object identity”

Consider the object graph:

```text
Before GC:

GC root: local x --------┐
GC root: local alias ----┤
Holder.field ------------┤
Array[0] ----------------┤
                         v
                  [Object A]  hypothetical address 0x1000
                      |
                      v
                  [Object B]  hypothetical address 0x1800

After a GC that moves A:

GC root: local x --------┐
GC root: local alias ----┤
Holder.field ------------┤
Array[0] ----------------┤
                         v
                  [Object A]  hypothetical address 0x9000
                      |
                      v
                  [Object B]  location depends on collector/GC phase
```

The addresses `0x1000` and `0x9000` here are **illustrative notation only**, not addresses taken from a real JVM.

If the collector has moved A from one heap region to a new region, all **reference paths that are still needed and can be used** must continue to point to A semantically. With a stop-the-world copying/evacuating collector, the appropriate reference slots are updated before application threads resume. With a concurrent moving collector, the program may go through barriers/forwarding logic, so not every slot necessarily holds the bits of the new location at the exact same instant.

Two statements need to be distinguished:

- **Object identity does not change:** A is still A; field values and aliasing relationships are preserved during a valid move.
- **Storage address can change:** the byte representation or location that HotSpot uses to find A can change; that address **is not Java-level identity**.

Therefore, a Java reference variable should not be understood as a “constant C pointer address” that an application can store as a `long` and use arbitrarily.

## 2. What does Java guarantee, and what does HotSpot do?

| Level | What can be relied upon | What must not be inferred |
| --- | --- | --- |
| **Java language** | `==` on two references to the same object still checks the same identity; field access, method calls, and object monitor semantics remain correct | That the object address will not change |
| **JVM specification** | Objects/arrays are created and managed with heap semantics; the JVM may manage memory and GC automatically | A single GC algorithm or object layout |
| **HotSpot collector** | The collector preserves live references according to its own policy when copying/compacting/moving objects | That G1, ZGC, and Shenandoah must use the same forwarding data structure or fix-up timing |
| **JIT/runtime** | Optimized code must still preserve Java-visible behavior | That every local `Object` always resides in a physical stack slot |

The JVM specification describes the heap and allows object memory to be automatically reclaimed. It does **not** require every implementation to use a **moving GC**. A collector may not move some or all objects in a cycle; an object remaining in an old location does not violate Java.

Furthermore, there are cases where the compiler eliminates physical allocation via **escape analysis/scalar replacement** while preserving observable behavior. Therefore, a Java program also must not use a successful run result to claim “this object was definitely copied from address X to Y”.

## 3. GC roots: starting points for finding live references

To know which objects need to be kept and which references must be tracked, the collector starts from a set of **GC roots** and additional structures managed by the runtime.

Some typical root sources on HotSpot:

- References in **Java thread frames**, including local variables, operand-stack values, and register locations that compiled code is using.
- **Static references** of classes that have been loaded and remain within the required liveness scope.
- **JNI local/global handles** and other runtime handles according to their respective semantics.
- References held by the VM/runtime itself for threads, class loaders, monitors, the code cache, or supporting structures.
- Roots serving a specific GC phase, such as code roots and remembered-set-derived heap roots when a collection only processes part of the heap.

**Being a root does not mean an object is kept forever:** when a stack frame exits or a reference is no longer considered reachable, the object can become eligible for reclamation after appropriate conditions/reference processing.

### Difference between a Java local and an actual GC root

A Java variable visible in source code is not necessarily still a **live root** throughout its entire lexical scope. The compiler/JIT can determine that a local is no longer used and shorten its valid liveness range. Conversely, a reference may be held in a CPU register rather than staying in a stack memory slot.

HotSpot uses exact information to identify locations containing object references at GC-compatible points, especially **safepoints** and metadata associated with compiled code.

**Distinguish two similar-looking names:**

- `StackMapTable` in a class file is primarily **bytecode verification** metadata, used to verify stack/local types at control-flow boundaries.
- **Oop maps**/GC maps in the HotSpot runtime/JIT help identify locations containing **object pointers** that need to be processed during GC.
  
They are not a single shared table that can be swapped interchangeably; merely seeing `StackMapTable` in `javap -v` is not proof that you have viewed the JIT's full GC root map.

### Graph of reachable objects

```text
  GC roots
    |
    +----> object A -----> object C
    |          |
    |          +-------> object D
    |
    +----> object B -----> object C

Object C can be kept alive by TWO paths,
but is still only ONE logical object.
```

If C is moved, all reference paths **that can continue to access** C must point to the right C after/through the relocation process. The collector must also maintain information so that it does not copy C into two Java objects with different identities just because two roots point to it.

## 4. What tasks does a moving/copying GC typically perform?

A simple explanatory model of a **stop-the-world copying collector**:

1. Identify a set of objects/heap regions to collect; decide which objects are live according to the GC algorithm.
2. From the appropriate roots and edges, encounter a reference to a live object in a region to be evacuated.
3. Copy the object to a **to-space/destination** region with available space, or handle an exception if it cannot be copied.
4. Record the mapping **old address → new address** via forwarding information or an appropriate structure.
5. Update appropriate root slots and field/array reference slots so they point to the target object; continue scanning the reference fields of the newly copied object.
6. When relocation/fix-up is sufficiently safe, free/reuse the old region and let the application resume.

Symbolic example:

```text
from-space                       to-space

A@0x1000  -------- copy -------> A@0x9000
  ref X ----------- fix-up -----> A@0x9000
  ref Y ----------- fix-up -----> A@0x9000
  ref Z ----------- fix-up -----> A@0x9000

forward(A@0x1000) = A@0x9000

A is only ONE Java object semantically;
A at the two addresses must not be treated as two independent objects.
```

**Forwarding** lets the collector know A has already been copied so that the next time a reference is encountered it does not create a second logical Java object copy. When the collector encounters a field/reference pointing to the old address, it looks up the new address and updates/redirects accordingly.

The statement “every reference is fixed immediately” is only true if you have already specified **the full collector type and phase**. In a concurrent collector, safety invariants can be guaranteed by **barriers**, metadata, and phased fix-up, not by scanning all slots at a single point in time.

### Not every step “copies the entire heap”

A young collection may only process objects in the young generation; a G1 mixed collection processes a specific set of regions, not every object in the heap. A collector can also **mark/sweep**, **compact in place**, **copy/evacuate**, or combine multiple techniques across phases. Objects outside the collection set may **not move**.

## 5. G1 on HotSpot Java 17: evacuation and reference updates

G1 (Garbage-First) divides the heap into **regions** and collects a **collection set (CSet)** during GC pauses. For the selected regions, G1 typically **evacuates** live objects to destination regions.

G1 interprets “root” for the collection set more broadly than just traditional GC roots: a reference from **outside the CSet** into **inside the CSet** is also important, because the object holding the reference may not be in the regions currently being collected.

At a conceptual level:

```text
Region P (outside CSet)          Region R (inside CSet)
+---------------------+         +------------------------+
| object Parent       |         | object Child @old      |
| childRef -----------+-------->| data, refs             |
+---------------------+         +------------------------+
           |
           | G1 scans root / remembered-set edges
           v
Region S (destination/to-space)
+-------------------------+
| object Child @new       |
| data, refs              |
+-------------------------+

After GC:
Parent.childRef -------------> Child @new
```

In the G1 implementation, forwarding information allows following from the old object to the copied object. When a GC worker processes a reference slot into the CSet, it can:

- Check whether the object already has a forwarding destination.
- If not, coordinate to copy/claim the object to a new location when appropriate.
- Point the reference slot to the corresponding destination.
- Continue processing reference fields inside the copied object so that all appropriate live edges are updated.

Note the **race between GC workers** within the same pause: two GC workers can simultaneously discover a reference to the same object. The claim/forwarding mechanism ensures that only one **logical destination** is accepted, preventing two references of the Java program from pointing to two independent copied objects.

### Remembered sets and card marking

G1 could not be efficient if at every young GC it had to scan **all old regions** just to find fields pointing into young regions. Therefore, it uses a mechanism for tracking **cross-region references**:

- **Write barriers/card marking** record reference field changes that may introduce cross-region edges that need to be known.
- **Remembered sets** and related structures help identify the areas/slots that need to be scanned during a collection of certain regions.
- When an object is evacuated, tracking structures also need to maintain correctness for the new references/regions.

**A write barrier is not the GC object copy itself.** It is a supporting mechanism that maintains metadata/conditions so GC can find the necessary edges. Reading “write barrier fixes the reference” without knowing whether it is SATB marking, remembered-set tracking, or a relocation phase is an imprecise interpretation.

### Concurrent marking is different from evacuation

G1 has **concurrent marking** to evaluate liveness and select regions effectively. However, **evacuation of the collection set** in Java 17 G1 typically occurs during **stop-the-world pauses**, unlike collectors designed for concurrent relocation. G1 can log concurrent phases and evacuation pauses within one GC cycle; do not lump them all together as “G1 moves objects concurrently with Java threads”.

### Evacuation failure and non-moving objects

If to-space is exhausted, G1 can encounter an **evacuation failure** and handle a portion of objects using another strategy. In some situations, an object may be **self-forwarded/kept in its old location**. In addition, some regions/objects do not participate in evacuation during a given pause.

Therefore, it is incorrect to claim “G1 moves every live object after every GC”. The commitment that must be upheld is **correct references and correct Java object identity**, regardless of whether an object actually changed location.

## 6. Concurrent moving collectors: why might a reference not be rewritten immediately?

ZGC and Shenandoah pursue the goal of reducing pauses by performing much of the GC work **concurrently with application threads**. With a collector that moves objects concurrently, the application may hold a reference that was read before the object finished relocating.

To still access the right object, the collector uses a combination of:

- **Forwarding/relocation metadata**: identifies the new object corresponding to the old object.
- **Load/read barriers**: process the reference when the application reads/uses it, potentially checking state and redirecting to the appropriate destination.
- **Store/write barriers**: preserve invariants of concurrent marking/relocation algorithms when the application mutates the reference graph.
- **Update/remap phases**: ensure that necessary references are eventually brought to the right state according to the collector's policy.

### ZGC in JDK 17

ZGC uses the ideas of **colored pointers**, **load barriers**, and **concurrent relocation/remapping** to manage references while the application continues running most of the time. This is an **implementation/version-specific** description, not a universal definition of all JVM references.

Do not infer that a Java reference value stored in source code can be converted into a “colored pointer integer” and have its colors parsed manually. Those bits and encodings are structures managed by the runtime; changes across releases/JVMs are possible.

### Shenandoah in JDK 17

Shenandoah has **concurrent evacuation** and **barriers** to access the target object and update references when an object is moved. The specific barrier type and forwarding strategy depend on the Shenandoah mode/release; do not use a ZGC-specific diagram to definitively explain every Shenandoah implementation.

### Comparing at the right level

| Aspect | G1 on HotSpot Java 17 | Appropriate ZGC/Shenandoah on JDK 17 |
| --- | --- | --- |
| Scope of movement | Selected collection set/regions | Regions/objects per collector policy |
| Evacuation/relocation | Main part in STW collection pauses | Has phases **concurrent with Java threads** |
| How references are kept valid | Scan/update slots, forwarding, remembered-set/barrier support | Forwarding + barriers/remapping per collector |
| Java object identity | Unchanged | Unchanged |
| Is the address stable? | **Not guaranteed** | **Not guaranteed** |
| Are all objects always moved? | No | No |
| Details mandated by the Java language? | No | No |

When studying GC internals, always pin down the **JDK version/build/collector flags**. JDK 17 ZGC differs from later generations of ZGC, and collector choice can change behavior observed in logs, pause times, throughput, and memory footprint.

## 7. Where do reference slots live and what does GC update?

A Java object can be referenced through many kinds of “slots”:

| Where the reference is held | Java example | Mechanism at the HotSpot level |
| --- | --- | --- |
| Local variable in an active method | `Node n = root;` | Root in a Java frame/compiled register if still live; GC map helps identify it |
| Operand stack of a JVM frame | Receiver value right before `invokevirtual` | Runtime processes references on frame/operand state |
| Static field | `static Node CACHE;` | Reference held by appropriate class/runtime structures |
| Instance field | `parent.child` | Reference inside a heap object, may need update if target moves |
| Reference array element | `nodes[0]` | Slot inside an array object, may need update |
| Collection graph | `list.get(0)`, `map.get(key)` | Usually field/array references of the collection structure |
| JNI local/global reference | `jobject` handle | VM manages handle/reference according to the JNI contract |
| Compiled code roots | Embedded oops or references in compiled frames | JIT/VM maintains metadata so GC can locate/update |

In Java source, `list.get(0)` yields a reference; in implementation, the list may have a backing array with reference slots. GC cares about **the object graph and concrete slots/roots known to the VM**, without needing to understand the business meaning of the name `list`.

### When an object containing references is also copied

Suppose `Parent` and `Child` are both evacuated. The collector must ensure that in **the Parent copy**, the child field points to the appropriate **Child copy**. If the child field still contained an invalid raw old address after the old region was reclaimed, Java behavior would be wrong.

Model:

```text
Before:
Parent_old.child --> Child_old
root -----------> Parent_old

After:
root -----------> Parent_new
Parent_new.child --> Child_new

Forwarding:
Parent_old -> Parent_new
Child_old  -> Child_new
```

From Java's perspective, `root.child` is still **that exact Child**. The order of copying and fix-up is coordinated by the collector; Child does not necessarily have to be copied immediately before/at the exact same time as Parent.

### Can a `final` heap field have its reference “modified” by GC?

There is a difference between **a Java application rewriting a `final` field** and **the VM updating an internal reference representation due to object relocation**. Java's `final` rule does not prevent GC from maintaining a valid reference when the target object moves. That is not a business-level `putfield` changing the field from Child A to Child B. **The logical object value referenced is still Child A.**

## 8. Why `==`, `System.identityHashCode`, and monitors remain valid

### Identity is not an address

Suppose:

```java
Node a = new Node();
Node b = a;
```

This is an **illustrative fragment** inside a method; `Node` is a hypothetical class.

If a and b point to the same object, `a == b` is `true`. GC may change the object's storage location, but must not cause Java to observe it as two different objects.

`System.identityHashCode(a)` provides an identity-based hash code according to the API contract. The value for **the same object** must not mutate just because GC moved it; this value **is not a raw address** and must not be used as an address or a JVM-wide unique canonical identifier. **Two different objects can still have the same identity hash code.**

### Monitors and synchronized

If a thread holds an object's monitor via `synchronized(lock)`, a GC move of the object must not cause its monitor to “disappear” or cause another thread to mistakenly synchronize on a different object. How HotSpot stores lock state/monitors/mark words is an implementation detail that depends on locking mode and JDK.

Do not deduce from the fact that the object header can hold forwarding metadata that GC loses `hashCode`, lock state, or the class pointer semantically. The collector and runtime must preserve those properties when copying/relocating.

### The Java object graph remains consistent

- An object reference in an array/field/list must continue to represent **the same logical target** if that target is still alive and accessible to the application.
- `IdentityHashMap` uses reference identity semantics, not an immutable raw address that the program is allowed to depend on.
- GC relocation is **not** a Java-level data race between threads; the memory model/`volatile`/locks still have their own semantics.
- GC can be stop-the-world or concurrent, but correctness of Java-visible behavior must be preserved.

## 9. Complete Java 17 example: aliasing surviving GC pressure

Create **`StableReferences.java`**:

```java
import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.List;

public class StableReferences {
    static final class Node {
        final int id;
        Node next;

        Node(int id) {
            this.id = id;
        }
    }

    // Keep a new allocation reachable to reduce the chance of it being eliminated
    // solely by optimization. This is not proof that an object moved.
    static volatile Object allocationSink;

    public static void main(String[] args) {
        Node first = new Node(7);
        Node second = new Node(9);
        first.next = second;

        Node alias = first;
        Node[] array = {first};
        List<Node> list = new ArrayList<>();
        list.add(first);

        IdentityHashMap<Node, String> names = new IdentityHashMap<>();
        names.put(first, "first");

        int identityBefore = System.identityHashCode(first);

        for (int i = 0; i < 400; i++) {
            allocationSink = new byte[64 * 1024];
        }

        System.out.println("aliasSame=" + (first == alias));
        System.out.println("arraySame=" + (first == array[0]));
        System.out.println("listSame=" + (first == list.get(0)));
        System.out.println("linkedId=" + first.next.id);
        System.out.println("mapValue=" + names.get(alias));
        System.out.println("stableIdentityHash="
                + (identityBefore == System.identityHashCode(first)));
    }
}
```

Compile/run with Java 17+:

```bash
javac --release 17 StableReferences.java
java StableReferences
```

**Program stdout**, independent of whether a moving GC occurred:

```text
aliasSame=true
arraySame=true
listSame=true
linkedId=9
mapValue=first
stableIdentityHash=true
```

What the program checks is **Java reference semantics**: aliasing, reference fields/arrays/collections, and the identity hash code must not break. It **does not prove** that an object moved, because the JVM might not run GC, might only GC other regions, might keep the object in place, or might optimize away some allocations.

### Generating heap pressure and enabling controlled GC logs

You can re-run on a HotSpot supporting G1:

```bash
java -Xms16m -Xmx32m -XX:+UseG1GC -Xlog:gc StableReferences
```

**GC logs, GC counts, and pause timings are not fixed** across OS/JVM/builds. If the collector performs young evacuation, the log will provide information about the collection; however, even when the log reports GC, **you cannot infer from the output that a specific object moved**. The number of bytes allocated in the loop, optimization behavior, and region allocation policy all affect what actually happens.

With the G1 collector, the command:

```bash
java -Xms16m -Xmx32m -XX:+UseG1GC -Xlog:gc*,gc+phases=debug StableReferences
```

can provide additional phase logging when the build supports the selected log tags. Do not use a specific BCI milestone, GC count, or imaginary address in the example as a test assertion.

### Why use `IdentityHashMap`?

`IdentityHashMap` compares keys using `==` instead of `equals`, which is useful for demonstrating Java identity semantics rather than pointer bits. If an object is moved, the map must still retrieve the right value for a key with the same identity. **Do not infer that `IdentityHashMap` internals store raw addresses.**

## 10. When weak/soft/phantom references exist: relocation vs. clearing

`java.lang.ref.Reference` introduces additional rules about reachability:

- Ordinary **strong references** can keep an object reachable.
- **`SoftReference`** has a clearing policy tied to memory sensitivity, with no deterministic schedule.
- **`WeakReference`** does not keep its referent alive like a strong reference; GC can clear it when the object has become weakly reachable under appropriate conditions.
- **`PhantomReference`** has a mechanism used for tracking post-mortem cleanup; `get()` always returns `null`; used with an appropriate `ReferenceQueue`.

Two **different** actions:

1. **Moving a live referent:** the object is still alive; the collector must ensure the reference to the object remains valid, possibly via remapping/forwarding.
2. **Clearing the referent of a `Reference` object:** when reachability and reference processing require it, the logical reference field is set to null according to contract, so Java can observe `weak.get() == null`.

Do not read `WeakReference.get() == null` and conclude “GC moved the object so the pointer was replaced with null”. Weak-reference clearing is a **reachability rule**, not a relocation bug.

### Java 17 example checking strong reachability without relying on GC timing

Create **`WeakReferenceSemantics.java`**:

```java
import java.lang.ref.Reference;
import java.lang.ref.WeakReference;

public class WeakReferenceSemantics {
    public static void main(String[] args) {
        Object strong = new Object();
        WeakReference<Object> weak = new WeakReference<>(strong);

        System.out.println("getBefore=" + (weak.get() != null));

        // Keep strong reachable up to the exact specified end point.
        Reference.reachabilityFence(strong);
    }
}
```

```bash
javac --release 17 WeakReferenceSemantics.java
java WeakReferenceSemantics
```

**Deterministic stdout:**

```text
getBefore=true
```

`Reference.reachabilityFence(strong)` lets the program specify a point up to which `strong` must be considered strongly reachable. The example intentionally does **not** call `System.gc()` or print `weak.get()` after losing the strong reference, because **when GC runs/clears a weak reference is non-deterministic**.

### Reference areas handled specially by the collector

A collector may have **reference processing phases** for `java.lang.ref` references. In G1, weak/soft/phantom reference handling is distinct work from copying/updating ordinary strong references; GC logs may also show these phases separately. Do not use the generic term “reference processing” to claim that every oop update during evacuation follows the same clearing rules.

## 11. JNI handles, native pointers, and the fact that Java objects can move

JNI is a place where serious bugs are easily introduced if C/C++ developers hold onto addresses under false assumptions.

### `jobject` is not a raw stable object address

Under standard JNI usage, objects are passed via **JNI references/handles**. The VM manages handles so that the collector can handle relocations appropriately. Native callers use `jobject` according to **JNI lifetime rules**, without assuming it is a stable raw object address.

- A **JNI local reference** is typically valid within the scope of the corresponding native call/frame and may be freed by the VM upon return according to contract.
- A **JNI global reference** persists until native code frees it with the appropriate API; holding global references too long can also keep objects alive and cause retention.
- A **weak global reference** has different semantics from a strong global reference; it can lose its referent if GC clears it.
- If you directly store the memory address of a Java object into a `uintptr_t` or `long`, the JVM **does not promise** to update that integer when GC moves the object. That is not a valid GC-tracked reference slot.

### `GetPrimitiveArrayCritical` and pinning/copying

The JNI API provides a way to obtain a pointer to primitive array contents for a usage window under a specific contract. The JVM may use **pinning**, **copying**, or an appropriate strategy depending on the runtime/API. Native code must obey critical region constraints and call the corresponding **Release** function promptly.

Do not infer that because `GetPrimitiveArrayCritical` exists, **all other Java objects** will be pinned, or that the returned address remains valid to use after release. The JNI API is not a general-purpose way to obtain a “permanent Java object address”.

### Direct buffers differ from heap objects

`ByteBuffer.allocateDirect` uses backing memory with direct buffer semantics; the Java wrapper object is still managed by GC and can move. The backing memory resides outside the Java heap per the implementation mechanism; native pointers to the backing region have different lifetime rules from Java object references.

This explains why a native buffer address being stable within a specific API's scope does **not** prove that the addresses of all Java objects are stable.

## 12. Compressed oops: a Java reference is not necessarily a machine-width pointer

In many 64-bit HotSpot configurations, references to Java heap objects can be stored as **compressed ordinary object pointers (compressed oops)** to reduce memory used for object fields/arrays. The JVM decodes/encodes them into usable addresses in the implementation.

Things to understand:

- A Java `Object` reference **does not have a JLS-mandated primitive type size** of 32 or 64 bits.
- Some HotSpot heap configurations use compressed oops while others do not; encoding may use a base/shift and runtime-dependent schemes.
- When an object moves, the collector/JIT must ensure that the reference representation, whether compressed or not, still leads to the right logical object.
- `System.identityHashCode(obj)` does not give a raw object address and cannot be used to deduce compressed-oop bits.
- Compressed oops information cannot replace GC root maps and forwarding/relocation logic.

You can observe some flags on HotSpot:

```bash
java -XX:+PrintFlagsFinal -version
```

Look for `UseCompressedOops` and related flags in the build's output, but do not deduce the **exact memory layout** from a single flag alone. JDK/vendor/GC config details also determine object alignment and decoding behavior.

## 13. Safepoints, barriers, and synchronization between GC and mutators

### Stop-the-world

During stop-the-world GC phases, application threads are brought to a safe state so the collector can traverse, relocate, and perform necessary updates without mutators concurrently modifying the heap graph in an uncontrolled way. How HotSpot coordinates safepoints/handshakes is an implementation detail.

A `synchronized` call is **not** a mechanism the application needs to add to make GC reference updates safe. The GC/VM handles internal consistency itself.

### Concurrent

With a concurrent collector, an application thread is a **mutator** because it can read/write fields, allocate objects, and modify the reference graph while GC runs. Barriers and phase invariants ensure that wrong references are not observed.

Example model:

```text
Mutator reads field -> read/load barrier -> effective target object
Mutator writes field -> write barrier -> tracking/marking/remembered metadata
GC relocated object -> forwarding/remapping -> references remain valid
```

However, this is only a **high-level diagram**. G1 write barriers serve remembered sets/marking and must not be taken as evidence that G1 is performing concurrent evacuation. ZGC and Shenandoah have different barrier implementations and should not be compared instruction-for-instruction as identical.

### GC barriers differ from `volatile` and Java Memory Model memory fences

- **GC barrier:** runtime instrumentation for GC to maintain invariants (marking, remembered sets, remapping...).
- **`volatile`/synchronization/JMM:** guarantees visibility/ordering/happens-before for the Java program.
- A compiler/JIT may implement both kinds using different machine instructions or combine optimizations, but **their semantics and purposes are not identical**.
- A GC reference update does **not** replace the need for application synchronization when multiple threads concurrently modify a mutable object.

## 14. Not every object must move: “pinned”, “humongous”, evacuation failure

Several cases where relocation cannot be assumed:

1. **Region not in the collection set**: the object may not be copied.
2. **GC does not occur**: creating heap pressure or calling `System.gc()` is not definitive proof that an object moved.
3. **Large/humongous objects**: some collectors have special policies for objects spanning multiple regions; relocation may not follow the normal evacuation path.
4. **Evacuation failure/to-space exhaustion**: the collector may keep some objects in place and apply fallbacks.
5. **Native/JNI critical regions or pinning**: can affect the ability/timing to relocate related objects depending on the API/collector.
6. **Non-moving phases/collectors**: mark-sweep does not necessarily have a relocation step like a copying GC.

The goals of relocation typically include reclaiming memory efficiently, reducing fragmentation, and supporting bump-pointer allocation and region-based management, while collectors also balance throughput, pause times, and CPU/memory overhead.

An object “not moving during an observed GC” **does not** create a fixed-address contract for the next time.

## 15. How do you know if GC moved a specific object?

From portable Java code, **there is no standard API returning a stable raw heap address to compare before/after GC**. Therefore:

- `System.identityHashCode(obj)` only measures an identity-based hash code, not an address.
- `obj.toString()` per `Object` typically contains the hash code in hex, which is also **not** a heap address.
- `Unsafe`/JOL/internal debuggers can provide implementation-specific information, but reference encoding, GC timing, and how memory is read can easily make results misleading. Do not use raw addresses for application logic.
- GC logs report GC phases/regions/bytes depending on log level, and usually do **not** list every individual object relocation by a stable identifier.
- Heap dumps/diagnostic tools may represent object IDs or locations for a snapshot, but printed IDs/addresses are not a Java identity contract across multiple snapshots.

If the goal is simply to ensure the program does not break after GC, tests should check **contents, aliasing, and object identity semantics**. If the goal is to study collector internals, use **version-pinned builds/diagnostics**, GC logs/JFR/SA/JVM debug instrumentation according to what the environment supports, while stating observation limits.

### Suggestions for checking G1 phases

With a test JVM running long enough:

```bash
java -XX:+UseG1GC -Xlog:gc*,gc+phases=debug -jar app.jar
```

`app.jar` is the name of a **sample application** that must actually exist, not a file created in this lesson. In the log, look for lines about **Evacuate Collection Set**, root scanning, object copy/evacuation, reference processing, and pause times. Phase names/annotations may change across versions/GC log levels.

At the same time, you can inspect:

```bash
jcmd <PID> GC.heap_info
jcmd <PID> VM.flags
```

`<PID>` is a placeholder for the actual process ID. `jcmd` commands do not return a list of raw object references that were fixed up, but they help identify the collector, heap settings, and runtime state. Do not take sample logs from another environment as evidence for the current process.

## 16. Some common debugging mistakes

| Incorrect inference | What is true |
| --- | --- |
| “A Java reference is an always-immutable object address” | Java guarantees reference semantics, not a physical address |
| “GC moving an object will make `a == b` false” | The collector preserves aliasing/identity semantics |
| “A local reference disappears when the object moves” | The VM updates/redirects live roots according to GC mechanisms |
| “The collector always scans every heap field after every minor GC” | Region/remembered-set/root discovery avoids unnecessary full scans |
| “A forwarding pointer is a user-visible Java field” | It is internal GC/VM metadata, not a public Java API |
| “G1 evacuates concurrently just like ZGC” | Java 17 G1 primarily evacuates in STW pauses; concurrent marking is a different phase |
| “Every Java collector uses the same load barrier” | Barrier strategy is implementation-specific |
| “A write barrier means Java `volatile`” | GC barriers and JMM synchronization serve different purposes |
| “`final Node child` prevents GC from changing pointer bits” | `final` protects program semantics; GC still maintains internal representations |
| “`System.identityHashCode` is a memory address” | It is an identity-based hash, not an address; collisions are possible |
| “`WeakReference.get() == null` proves GC moved the object” | That is reachability/reference clearing, not relocation |
| “Once you have a `jobject`, native code can hold a raw pointer forever” | JNI handles have lifetime rules; raw object addresses are not stable |
| “`System.gc()` definitely runs a moving GC” | It is only a request/hint; it does not guarantee moving any specific object |
| “JVM GC automatically solves all data races” | GC keeps internal memory safe; the app still needs proper synchronization |
| “Arrays/lists hold objects at the exact physical address from when they were added” | They hold references whose semantics are maintained by the JVM |
| “A GC log showing a pause means all live objects moved” | Collection scope may be only a subset of regions; many objects do not move |

## 17. Workflow for analyzing issues related to object relocation

**Step 1 — Pin down the implementation.** Record the JVM vendor/build/version, active collector, heap flags, and platform. Avoid mixing G1 behavior from newer JDKs with JDK 17 ZGC.

**Step 2 — Identify the symptom.** Is it a `ClassCastException`, `NullPointerException`, JNI native crash, heap corruption, mistaken aliasing assumption, or an object cleared by GC due to a weak reference? Different errors have different root causes.

**Step 3 — Check the Java-visible contract.** Verify the same object with `==`, field contents, proper Java synchronization, and reference lifetime. Do not use identity hashes as raw pointers.

**Step 4 — Identify GC roots.** Is there a live reference from stack, static fields, heap objects, or JNI handles? A local whose liveness has ended does not automatically keep an object alive throughout its lexical scope.

**Step 5 — Understand the collector phase.** G1 evacuation? Concurrent marking? ZGC/Shenandoah remapping? One phase does not mean every object is moved.

**Step 6 — Cross-check the reference category.** Strong, weak/soft/phantom, JNI local/global/weak global, direct/native memory, and pinned primitive arrays all have different semantics.

**Step 7 — For JNI/Unsafe/agents, check lifetime and validity.** Do not store raw object addresses outside the VM contract; do not manually edit class/object headers, compressed oop bits, or forwarding metadata.

**Step 8 — Use controlled diagnostics.** `-Xlog:gc*`, JFR/JVM diagnostics when appropriate, heap dumps/JOL/SA if studying the implementation; avoid forcing GC in production just to produce a “before/after address”.

**Step 9 — Write regression tests against Java results.** Verify the object graph, aliasing, identity maps, collection contents, and concurrency invariants instead of checking arbitrary offsets/addresses.

**Step 10 — Conclude with the right level of certainty.** “References remain valid after GC” can be confirmed by Java semantics; “object A actually moved from 0x... to 0x...” requires appropriate implementation-level evidence.

## 18. Self-check questions

**Question 1:** `Node a = new Node(); Node b = a;`, GC copies the object to another region. Is the expression `a == b` allowed to change to `false`?

**No.** Both references still point to the same logical object.

**Question 2:** A field `parent.child` points to a Child that has just been evacuated. What must the collector ensure?

**Reading the field still retrieves the right Child**, via updating the reference slot or an appropriate redirection/remapping mechanism; never letting the application see an invalid stale raw address.

**Question 3:** What is forwarding information for when multiple roots point to the same object?

To recognize that the object **has already been copied** and let all paths find the same valid destination, instead of producing multiple independent logical copies.

**Question 4:** Does a G1 young GC need to scan the entire old heap to discover old-to-young edges?

Not necessarily. G1 uses remembered sets, card marking, and appropriate root-tracking mechanisms.

**Question 5:** Can ZGC fix up a reference at the moment the application reads it?

Yes. ZGC uses load barriers and relocation/remapping mechanisms; it must not be assumed that all slots are always eagerly rewritten in a single STW pause.

**Question 6:** Does `System.identityHashCode(obj)` change after relocation?

Not because of relocation itself. It is an identity-based hash, not a raw address.

**Question 7:** Does `WeakReference.get() == null` indicate that the object moved or that it was cleared?

A null result can be caused by **weak reference clearing** under reachability rules; it is not an indicator of relocation.

**Question 8:** Does a Java source variable still in scope definitely keep an object as a GC root?

No. Liveness can end before the end of the scope. Use `Reference.reachabilityFence` when you truly need to maintain strong reachability up to a specific point.

**Question 9:** Once you receive a `jobject` via JNI, can you cast it to a native address and cache it throughout execution?

No. Use JNI references/handles according to the lifetime contract; the JVM does not promise to update a raw integer address stored manually by native code.

**Question 10:** Does a GC log containing the line “Evacuate Collection Set” prove that the specific object in variable `first` changed its address?

No. The log reflects a GC phase; it does not definitively identify a specific object and does not provide before/after raw addresses.

## Sources and references

- [JVMS Java SE 17 `2.5.3 — Heap](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.3): runtime heap and object management.
- [JVMS Java SE 17 `2.6 — Frames](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6): JVM frames, local variables, operand stack, and references.
- [Oracle Java SE 17 — G1 Garbage Collector](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector1.html): root processing, evacuation, remembered sets, and failure scenarios.
- [OpenJDK source — G1ParScanThreadState (reference evacuation/update)](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/g1/g1ParScanThreadState.cpp): clear example of forwarding and reference slot updates, **note that the main branch link does not necessarily match JDK 17**.
- [JEP 333 — ZGC](https://openjdk.org/jeps/333): goals and concepts of concurrent GC, colored pointers/load barriers.
- [JEP 189 — Shenandoah](https://openjdk.org/jeps/189): concurrent evacuation of the collector.
- [Java SE 17 `Object`](https://docs.oracle.com/javase/17/docs/api/java.base/java/lang/Object.html) and [`System.identityHashCode`](https://docs.oracle.com/javase/17/docs/api/java.base/java/lang/System.html#identityHashCode(java.lang.Object)): object identity and identity-based hash.
- [Java SE 17 `IdentityHashMap`](https://docs.oracle.com/javase/17/docs/api/java.base/java/util/IdentityHashMap.html): key comparison by `==`.
- [Java SE 17 `Reference`](https://docs.oracle.com/javase/17/docs/api/java.base/java/lang/ref/Reference.html) and [`WeakReference`](https://docs.oracle.com/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html): reachability, clearing, and `reachabilityFence`.
- [JNI Specification Java SE 17 — JNI Functions](https://docs.oracle.com/javase/17/docs/specs/jni/functions.html): local/global references, weak globals, critical array access.
- [Java SE 17 `ByteBuffer`](https://docs.oracle.com/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): direct buffers and heap buffers.
- [Java SE 17 `java` command](https://docs.oracle.com/javase/17/docs/specs/man/java.html), [`jcmd`](https://docs.oracle.com/javase/17/docs/specs/man/jcmd.html): collector flags, unified GC logging, and VM diagnostics.

**Takeaway:** when HotSpot moves an object, **Java reference semantics and object identity must remain unchanged**. G1 typically updates roots/field slots during evacuation pauses with forwarding; concurrent collectors can maintain correctness via **barriers and remapping** at different points in time. Java code should rely on **object identity, reachability, and proper synchronization**, not on raw addresses, identity hash numbers, or assumptions that every GC moves every object.
