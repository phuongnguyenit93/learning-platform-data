# Object Size Differs from Graph Total or Retained Size

## 1. One Object, Three Different Memory Questions

A Java agent can call `Instrumentation.getObjectSize(object)` to obtain a `long` value. This value is **not** "the total amount of all data that the object points to" and is **not** the object's retained size in the JVM.

An exact distinction must be made:

- **Shallow size (shallow heap):** an estimate of the storage of **the object itself**: header, fields, directly stored array elements, and alignment/padding according to the JVM. It does not automatically traverse references to other objects.
- **Reachable graph size (reachable graph total):** the sum of shallow sizes of **distinct** object instances that an algorithm reaches from a starting object/root set along **defined edge types**. Without deduplication/cycle handling, the result is incorrect.
- **Retained size (retained heap):** the sum of shallow sizes of objects **dominated** by the object under consideration in an object graph with GC roots. It indicates the portion of the heap whose existence depends on the owner within a root graph/snapshot, **not** merely what the owner can reach.

**Main thesis of this article:** `getObjectSize(x)` only provides an estimate of the shallow size of `x`. This API does not traverse graphs, has no GC roots information, does not build a dominator tree, and **does not return retained size**. An object can have a very small shallow size yet a very large retained size, or a large reachable graph yet a small retained size because its descendants are shared by multiple owners.

### Choosing the measurement by question

| Question | Appropriate metric |
|---|---|
| How much memory does a single `Node` occupy on its own? | Shallow size |
| Approximately how many bytes does a `byte[]` of one million elements occupy? | Shallow size of the primitive array |
| Traversing from object A, how many object nodes are there and what is their total size? | Deduplicated reachable graph count/sum |
| A and B both reference payload S; what is the total unique heap of the graph? | Sum over `R(A) UNION R(B)` |
| If owner A is no longer present, which objects lose all GC-root paths? | Retained size / dominator analysis |
| Why is an object still alive via reference paths? | Paths to GC Roots |
| How much native RAM does a direct ByteBuffer use? | Native/direct memory metrics, not the shallow wrapper |
| Where is the JVM allocating objects rapidly? | Allocation profiler/JFR, not retained heap |

## 2. What Does `Instrumentation.getObjectSize(Object)` Actually Do?

### 2.1. Java SE 17 contract

Signature:

~~~java
long getObjectSize(Object objectToSize);
~~~

According to the Java SE 17 Javadoc, the value is an **implementation-specific approximation of the amount of storage consumed by the specified object**. It may include some or all of the object overhead; it is suitable for comparison **within a single implementation**, and is not guaranteed to be comparable across different JVM implementations. The estimate may also change **within a single invocation of the JVM**.

Several points must be stated explicitly:

1. There are no `depth`, `includeChildren`, `retained`, or traversal policy parameters.
2. It does not return a set of references/child objects.
3. It does not measure total heap, total allocated bytes, RSS, or native memory.
4. `getObjectSize(null)` throws `NullPointerException`, rather than returning 0.
5. You cannot treat the byte count of a specific 64-bit JVM as a standard across all VMs: object headers, compressed pointers, alignment, representation, and vendors differ.

### 2.2. Object fields vs referenced objects

~~~java
final class Holder {
    int count;
    Object child;
}
~~~

The shallow size of `Holder holder` consists of the storage of **the Holder instance itself**: object overhead, the primitive slot `count`, the reference slot `child`, and JVM alignment/padding. It **does not add** the storage of the object that `holder.child` points to.

If `holder.child` is assigned from `null` to an object with one million elements, the shallow size of Holder usually does not change under the same VM layout; the storage of the second object is a separate matter. A reference also does **not** prove sole ownership: child can be kept alive from other roots.

### 2.3. The easily confused case of arrays

| Java object | Shallow of the object itself | Not yet included |
|---|---|---|
| `new Object()` | Header/padding | No child objects |
| `new byte[1_000_000]` | Header/length + **one million byte elements inline** | Objects outside the array |
| `new Object[1_000_000]` | Header/length + **one million reference slots** | Object instances that the slots point to |
| `new String("abc")` | String instance | Backing array/objects depending on JDK representation |
| `new ArrayList<>()` | ArrayList instance | Backing `Object[]` and elements |
| `new HashMap<>()` | HashMap instance | Table, nodes, keys, values |
| `new Node("A")` | Node instance | Nodes/Strings pointed to by its fields |
| `ByteBuffer.allocateDirect(...)` | Java wrapper | Native/off-heap region |

**Do not say "shallow does not count array elements"** without distinguishing: a primitive array contains primitive elements **inline inside the array object itself**; `Object[]` contains reference slots inline, but **does not contain the referenced objects themselves**.

Example:

~~~java
byte[] payload = new byte[1_000_000];
Object[] wrapper = {payload};
~~~

`getObjectSize(wrapper)` only measures the one-slot object array; `getObjectSize(payload)` measures the byte array separately. A real JVM may return different numbers depending on configuration; this article does not set a fixed byte-layout figure as a mandatory standard.

### 2.4. Shallow is not the entire application footprint

A Java `DirectByteBuffer` can have a small shallow size while pointing to a large native region. Thread stacks, metaspace, JIT code cache, memory mappings, JNI allocations, and other regions are likewise not included by a `getObjectSize` call on a Java wrapper.

Distinguish the labels:

- **Object shallow bytes**: estimate for a single Java object.
- **Live Java heap**: live objects determined by the GC/JVM.
- **Heap committed/reserved**: memory regions managed by the JVM, not identical to live objects.
- **RSS/process memory**: an OS-level metric that includes many parts outside the Java heap.

When diagnosing rising process RAM, calling only `getObjectSize` lacks sufficient information.

## 3. Reachable Graph Requires Traversal and Identity

### 3.1. Graph definition

Let:

- `V`: the object instances within the scope of the graph under study.
- `E`: the reference edges that the algorithm decides to follow.
- `R(x)`: the set of **distinct** objects reachable from x (including x).
- `s(v)`: the shallow size returned by `getObjectSize(v)`.

If we have the exact set `R(x)` for the **defined graph**, we can compute:

~~~text
ReachableShallowSum(x) =
    SUM( getObjectSize(v) for each distinct v in R(x) )
~~~

This formula is **not** a built-in method of Instrumentation. You must know the edges, traverse, and deduplicate. Knowing only `getObjectSize(x)` cannot derive `R(x)`.

### 3.2. Why must object identity be used?

Two instances can be considered equal by `equals()` yet still be **two separate allocations** on the heap. Conversely, two fields can hold references to **the same object instance**.

A suitable visited set:

~~~java
// Illustrative code snippet inside a class that has imported the corresponding types.
Set<Node> seen = Collections.newSetFromMap(
        new IdentityHashMap<Node, Boolean>());
~~~

`IdentityHashMap` uses identity (`==`) rather than value equality; therefore it does not double-count one instance and does not merge two different instances due to an overridden `equals`. A regular `HashSet` does not automatically guarantee this for object accounting.

### 3.3. Cycles and shared references

~~~text
ROOT A -> A -> S <- B <- ROOT B
           |
           v
           U -> A     (cycle A -> U -> A)
~~~

Edges:

~~~text
A -> S
A -> U
U -> A
B -> S
~~~

For this graph:

- `R(A) = {A, S, U}`.
- `R(B) = {B, S}`.
- Union of the two sets `R(A) UNION R(B) = {A, B, S, U}`.
- Adding `sum(R(A)) + sum(R(B))` separately causes S to be added **twice**.
- If DFS/BFS has no visited set, the cycle A→U→A can cause the algorithm to loop infinitely.

Therefore, when asking for the unique total of A and B, you must union the sets **by identity before summing**. A property such as `left` pointing to a child does not prove that the child is exclusively owned by the parent object.

### 3.4. "Graph total" depends on scope

If hand-written code only traverses `Node.left` and `Node.right`, it does **not** visit `Node.id` (String), the backing array of a collection, or references from JDK internals. That is the total of the **Node-only graph**, not the entire JVM heap graph.

A generic Java reflective walker also runs into private fields, superclasses, object arrays, JPMS access, special references, concurrency, and GC roots. You cannot claim that summing the shallow sizes of a self-discovered set is the JVM-wide retained heap.

## 4. Retained Size Requires Knowing All Paths from GC Roots

### 4.1. GC roots and live objects

The garbage collector considers reachability from **GC roots**, which depending on the runtime/snapshot may include active stack references, static fields via runtime class structures, JNI handles, and other sources.

An object S pointed to by A does **not** mean A is the sole reason S stays alive. If B is also kept alive by another root and B points to S, removing A does not make S unreachable.

### 4.2. Dominator: the "every path must pass through x" condition

An object `x` **dominates** an object `y` if **every path from the virtual super-root** connected to the relevant GC roots to y must pass through x. If there exists a root path that bypasses x, x does **not** dominate y.

The retained set of x consists of x itself and all objects dominated by x; retained size in a heap snapshot model is:

~~~text
RetainedSet(x) = { v | x dominates v }
RetainedSize(x) = SUM( shallowSize(v) for v in RetainedSet(x) )
~~~

A dominator tree is one way to represent this relation. **Edges in a dominator tree are not necessarily direct Java reference edges**. An object can dominate an entire subgraph even if it has no direct field pointing to every object in the subgraph.

### 4.3. The A/B/S/U graph has retained different from reachable

Suppose a **model** has only two roots and four object nodes:

~~~text
ROOT_A -> A
ROOT_B -> B
A -> S
A -> U
U -> A
B -> S
~~~

Then:

- A dominates U, because every root path to U passes through A.
- A does **not** dominate S: there is the path `ROOT_B -> B -> S`.
- B does **not** dominate S: there is the path `ROOT_A -> A -> S`.
- The retained set of A in the model = `{A,U}`.
- The retained set of B = `{B}`.
- Reachable from A is still `{A,S,U}`, **more than** the retained set of A.

This is an important illustration: **you cannot rename ReachableShallowSum(A) to RetainedSize(A)** if S is shared.

### 4.4. Numerical example solely for illustration

Suppose hypothetical shallow sizes:

| Node | Hypothetical bytes |
|---|---:|
| A | 24 |
| B | 24 |
| S | 40 |
| U | 24 |

Results in the **model**:

~~~text
Shallow(A) = 24

ReachableSum(A) = 24(A) + 40(S) + 24(U) = 88
ReachableSum(B) = 24(B) + 40(S) = 64

Separate sum = 88 + 64 = 152    (S counted twice)
Union unique = 24 + 24 + 40 + 24 = 112

Retained(A) = 24(A) + 24(U) = 48
Retained(B) = 24(B)
~~~

**24 and 40 are illustrative numbers**, not actual Java 17 object sizes. The same A gives shallow=24, reachable=88, and retained=48 (in the defined GC-root paths model). A real JVM may have completely different object layouts and root paths.

### 4.5. Subtracting reachable sets is not a general retained algorithm

In the model above, `R(A) - R(B) = {A,U}` matches the retained set of A because **it was assumed all root paths** only go through A and B. However, in a real JVM:

- Local variables, thread stacks, static fields, or JNI may keep A/U/S alive via other paths.
- Object fields not traversed by the Node-only graph, such as `String id`, are also references.
- Multiple roots can reach descendants of A without passing through A.
- Weak/soft/phantom references do not have the same keep-alive semantics as strong references.

Therefore, do not generalize `retained(A)=R(A)-R(B)`. Obtaining true retained heap requires a **GC-root graph and dominator analysis**, not two sets from a demo.

## 5. Complete Java 17+ Example: Shallow and Graph by Identity

The lab exercise has two Java source files and one manifest. The Java agent receives `Instrumentation` in `premain`, and the application uses `getObjectSize` and traverses a graph with a cycle/shared node.

**Purpose:** illustrate that shallow **differs** from reachable sum, and adding two reachable sets can double-count. The demo does **not** pretend to compute JVM retained size.

### 5.1. Structure

~~~text
size-graph-demo/
├── AGENT.MF
├── src/
│   ├── agent/demo/SizeAgent.java
│   └── app/demo/GraphDemo.java
└── out/
    ├── agent/
    ├── app/
    └── size-agent.jar
~~~

### 5.2. `src/agent/demo/SizeAgent.java`

~~~java
package demo;

import java.lang.instrument.Instrumentation;

public final class SizeAgent {
    private static volatile Instrumentation inst;

    private SizeAgent() {}

    public static void premain(String arguments, Instrumentation instrumentation) {
        inst = instrumentation;
    }

    public static long shallow(Object object) {
        Instrumentation i = inst;
        if (i == null) {
            throw new IllegalStateException("Use -javaagent:size-agent.jar");
        }
        return i.getObjectSize(object);
    }
}
~~~

The agent does not register a `ClassFileTransformer` because there is no requirement to modify classfiles. It only uses `Instrumentation` to estimate the shallow size of existing instances. If `-javaagent` is missing, the wrapper throws a clear error rather than returning a fake number.

### 5.3. `src/app/demo/GraphDemo.java`

~~~java
package demo;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;

public final class GraphDemo {
    private GraphDemo() {}

    private static final class Node {
        final String id;
        Node left;
        Node right;
        Node(String id) { this.id = id; }
    }

    private static Set<Node> identitySet() {
        return Collections.newSetFromMap(new IdentityHashMap<>());
    }

    private static Set<Node> reachable(Node start) {
        Set<Node> seen = identitySet();
        ArrayDeque<Node> pending = new ArrayDeque<>();
        pending.add(start);
        while (!pending.isEmpty()) {
            Node current = pending.removeLast();
            if (!seen.add(current)) continue;
            if (current.left != null) pending.add(current.left);
            if (current.right != null) pending.add(current.right);
        }
        return seen;
    }

    private static Set<Node> difference(Set<Node> first, Set<Node> second) {
        Set<Node> result = identitySet();
        result.addAll(first);
        result.removeAll(second);
        return result;
    }

    private static Set<Node> union(Set<Node> first, Set<Node> second) {
        Set<Node> result = identitySet();
        result.addAll(first);
        result.addAll(second);
        return result;
    }

    private static String names(Set<Node> nodes) {
        List<String> ids = new ArrayList<>();
        for (Node node : nodes) ids.add(node.id);
        Collections.sort(ids);
        return String.join(",", ids);
    }

    private static long shallowSum(Set<Node> nodes) {
        long result = 0L;
        for (Node node : nodes) {
            result = Math.addExact(result, SizeAgent.shallow(node));
        }
        return result;
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");
        Node shared = new Node("S");
        Node unique = new Node("U");

        a.left = shared;
        a.right = unique;
        unique.left = a; // Cycle: A -> U -> A
        b.left = shared; // Shared S: A -> S <- B

        Set<Node> fromA = reachable(a);
        Set<Node> fromB = reachable(b);
        Set<Node> all = union(fromA, fromB);
        Set<Node> onlyA = difference(fromA, fromB);

        long aBytes = SizeAgent.shallow(a);
        long separateSums = Math.addExact(shallowSum(fromA), shallowSum(fromB));
        long unionSum = shallowSum(all);
        long duplicateShared = SizeAgent.shallow(shared);

        System.out.println("shallow(A) positive=" + (aBytes > 0));
        System.out.println("reachable(A)=" + names(fromA));
        System.out.println("reachable(B)=" + names(fromB));
        System.out.println("union(A,B)=" + names(all));
        System.out.println("onlyA(model)=" + names(onlyA));
        System.out.println("duplicate S counted twice="
                + (separateSums == unionSum + duplicateShared));
        System.out.println("reachableSum(A) >= shallow(A)="
                + (shallowSum(fromA) >= aBytes));
        System.out.println("JVM retained size measured=no");
    }
}
~~~

### 5.4. What makes the example work?

- `reachable` only traverses **Node.left/right**, without visiting Strings in `Node.id`, other runtime objects, or GC roots.
- `IdentityHashMap` does not confuse two instances with equal `equals`.
- `seen.add(current)` avoids infinite traversal on the cycle A→U→A.
- `union` merges the two starting sets before summing, so the shared object S appears only once.
- `difference` is only a set comparison in the Node-only model, and does not promise retained size.
- `names` sorts labels so output does not depend on hash-map iteration order.
- `Math.addExact` avoids silent addition overflow; the demo graph is very small.
- `shallowSum` still has to call `getObjectSize` **on each node**, whereas `getObjectSize(a)` only processes A alone.

During execution, the locals `a`, `b`, `shared`, and `unique` in `main` itself also create their own keep-alive paths. **That is why the last line explicitly states that JVM retained size has not been measured.**

### 5.5. `AGENT.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: demo.SizeAgent

~~~

The manifest ends with a newline, and `Premain-Class` is in the main section. `Can-Retransform-Classes` or `Can-Redefine-Classes` is not needed because the agent does not modify classes.

### 5.6. Build and run with JDK 17+

Create output directories:

Bash/macOS/Linux:

~~~bash
mkdir -p out/agent out/app
~~~

PowerShell/Windows:

~~~powershell
New-Item -ItemType Directory -Force out/agent, out/app | Out-Null
~~~

Compile the agent, package the JAR, compile the application:

~~~bash
javac --release 17 -d out/agent src/agent/demo/SizeAgent.java
jar cfm out/size-agent.jar AGENT.MF -C out/agent .
javac --release 17 -cp out/size-agent.jar -d out/app src/app/demo/GraphDemo.java
~~~

Run on Unix:

~~~bash
java -javaagent:out/size-agent.jar -cp "out/app:out/size-agent.jar" demo.GraphDemo
~~~

Run on Windows:

~~~powershell
java -javaagent:out/size-agent.jar -cp "out/app;out/size-agent.jar" demo.GraphDemo
~~~

### 5.7. Compiled and tested stdout

The core program was **compiled with `javac --release 17` and run on JDK 24**; the exact output is:

~~~text
shallow(A) positive=true
reachable(A)=A,S,U
reachable(B)=B,S
union(A,B)=A,B,S,U
onlyA(model)=A,U
duplicate S counted twice=true
reachableSum(A) >= shallow(A)=true
JVM retained size measured=no
~~~

Fixed shallow byte numbers are not printed: the Javadoc does not guarantee the same object layout/estimate across all JVMs.

If you want to print the **actual estimated** values of the current JVM, add the following snippet to `main` after creating `fromA`:

~~~java
System.out.println("approxShallowA=" + SizeAgent.shallow(a));
System.out.println("approxNodeSumA=" + shallowSum(fromA));
~~~

The results will vary by JVM, and `approxNodeSumA` is still the **sum of the Node-only graph**, not the retained heap.

### 5.8. Explaining the meaning of each line

| Output | Valid conclusion |
|---|---|
| `shallow(A) positive=true` | The API returns a positive estimate in the JVM running the demo |
| `reachable(A)=A,S,U` | From A, three Node instances are reached via left/right |
| `reachable(B)=B,S` | From B, two Node instances are reached |
| `union(A,B)=A,B,S,U` | Four unique nodes, S only once |
| `onlyA(model)=A,U` | A and U are not in B's reachable set in the model |
| `duplicate S counted twice=true` | Sum of the two separate sums adds s(S) twice |
| `reachableSum(A) >= shallow(A)=true` | A's reachable set includes A itself |
| `JVM retained size measured=no` | No GC-root/dominator analysis |

## 6. One Edge Change Can Change the Entire Conclusion

In `main`, before computing `reachable(a)` and `reachable(b)`, try:

~~~java
b.right = unique;
~~~

Because B now has the path `B -> U -> A`, it can reach A, S, and U. The result in the **model** will include:

~~~text
reachable(A)=A,S,U
reachable(B)=A,B,S,U
onlyA(model)=
~~~

The difference is empty because all Nodes of A are reachable from B. This shows that a **single edge** can change the ownership inference result. However, it does not turn set subtraction into JVM retained heap: GC roots outside the model still need to be known.

## 7. True Retained Heap: Using Heap Dumps and the Dominator Tree

### 7.1. Eclipse Memory Analyzer (MAT)

Eclipse MAT analyzes heap dumps and provides complementary views:

| View | Answers |
|---|---|
| **Histogram** | How many instances of each class exist, and what is the total shallow heap per class? |
| **Dominator Tree** | Which object/owner dominates and retains a large graph? |
| **Paths to GC Roots** | Why does this object remain reachable from a root? |
| **Leak Suspects Report** | Which groups of objects/retainers are worth investigating further? |

The dominator tree is a **keep-alive relation**, not a field tree. A small owner can dominate a large structure across multiple reference levels and have a large retained heap.

### 7.2. Diagnostic workflow

1. Read the symptoms: is Java heap used rising after GC, is the allocation rate high, or is process RSS increasing?
2. Identify the exact JVM/process, JDK version, workload, and timing needed for the snapshot.
3. Capture a heap dump using an authorized tool, controlling pause/disk cost.
4. Inspect the Histogram to see which classes have large total shallow heap or abnormal instance counts.
5. Inspect the Dominator Tree to find owners with significant retained heap.
6. Inspect Paths to GC Roots for suspect owners/children.
7. Cross-check against lifecycle: request/session, cache, listeners, ThreadLocal, plugin ClassLoader.
8. Compare multiple snapshots or trends when needed; do not conclude a leak from a single large graph at one point in time.

Example HotSpot/JDK command:

~~~bash
jcmd <pid> GC.heap_dump /secure/path/snapshot.hprof
~~~

**Illustrative command:** replace `<pid>` and the path for the real environment. Check available options with `jcmd <pid> help GC.heap_dump` on the running JVM. A heap dump can cause a pause, consume RAM/disk, and contain sensitive information such as tokens, user data, or payloads; appropriate permissions and security policies are required.

### 7.3. Allocation and native memory are not retained heap

- `Instrumentation.getObjectSize`: shallow estimate of a single Java object.
- Heap dump/MAT: live heap object graph and retained/dominators.
- JFR/allocation profiler: which code paths allocate heavily and at what rate.
- Native Memory Tracking/direct-buffer/native profiler: memory outside the Java heap and JVM native allocations.

A high allocation rate is not necessarily a leak if objects quickly become unreachable. Increasing retained heap does not necessarily come with a high current allocation rate if a cache holds previously accumulated data.

## 8. Why Do Generic Object Walkers Often Measure Incorrectly?

A traversal of the `Node.left/right` graph is easy to write because the schema is known in advance. However, for an arbitrary Java heap:

1. **Many kinds of references:** instance fields, superclass fields, arrays, collection internals, synthetic fields.
2. **Module boundaries:** JPMS can block reflective access to JDK private fields with `InaccessibleObjectException`.
3. **Cycles and shared references:** requires a visited set by identity, not `equals`.
4. **Weak/soft/phantom refs:** not every Java field keeps an object alive with the same strong semantics.
5. **GC roots:** a traversal starting at one object does not know all incoming root paths.
6. **Concurrency:** the graph can be modified during traversal, yielding inconsistent results.
7. **Native memory:** does not reside entirely within the Java heap graph.
8. **Observer effect:** holding references in a visited set can inadvertently extend object lifetimes; traversal consumes CPU/memory.
9. **Custom classloaders:** classes with the same name from different loaders have different identities.
10. **Implementation-specific sizes:** even the shallow sum of many objects is still a sum of estimates, not an exact RSS measurement.

Therefore, a `sumReachable` function should state **what kind of graph it actually traverses**. Only with root information, appropriate edge types, and dominator analysis can the label "retained heap" be used.

## 9. Real-World Scenarios

### 9.1. A List containing many byte arrays

~~~java
List<byte[]> chunks = new ArrayList<>();
for (int i = 0; i < 100; i++) {
    chunks.add(new byte[1024 * 1024]);
}
~~~

This is an illustrative code fragment (imports are needed in a standalone program). `getObjectSize(chunks)` does **not** return a 100 MiB total; it measures the `ArrayList` object itself. The backing array and the 100 `byte[]` arrays are separate objects. The retained size of the list/owner also depends on other keep-alive paths to the arrays.

### 9.2. A `HashMap` cache

The shallow size of a `HashMap` omits the table array, entry nodes, and objects pointed to by keys/values. A cache root can retain a very large graph, but if values are also referenced from other caches, the reachable sum does not equal retained size.

A large retained size **is not automatically a memory leak**. A legitimately large cache still has a high retained size; TTL, eviction, and lifecycle must be checked.

### 9.3. ThreadLocal and listeners

A ThreadLocal value or listener registry can keep a graph alive after a request completes. Inspect Paths to GC Roots; the shallow size of the ThreadLocal/listener owner does not describe the full retention.

### 9.4. ClassLoader after redeploy

An old ClassLoader can be kept alive by a thread context loader, static registry, or JNI after a redeploy. The owner's retained heap may involve many class instances and static graphs, even though the ClassLoader's shallow size is small. Distinguish the Java heap from metaspace/native class metadata.

### 9.5. Shared immutable objects and interned strings

Two caches sharing a String/payload with the same **object identity** will cause reachable sums to double-count if summed separately. Clearing one cache does not reclaim the object while the other cache still references it.

### 9.6. Native-backed direct buffer

A small shallow `DirectByteBuffer` wrapper can own a large native region. To explain process RSS, native/direct metrics are needed; the wrapper's retained heap does not automatically include the entire off-heap allocation.

## 10. Common Mistakes and How to Fix Them

| Mistake | Problem | Solution |
|---|---|---|
| Calling `getObjectSize(list)` and labeling it "list total" | Only measures the list instance | Analyze the backing/children graph separately |
| Assuming the shallow size of `Object[]` includes all element objects | Reference slots differ from referents | Measure referents separately and deduplicate |
| Assuming the shallow size of `byte[]` does not include elements | Primitive elements are stored inline | Understand array object layout |
| Summing every reference encountered | Cycles/shared objects cause infinite loops or double-counting | Identity visited set |
| Using `HashSet` by `equals` | Merges two allocations with different identities | Use an identity set |
| Equating reachable sum with retained size | Shared GC-root paths break domination | Use a dominator tree |
| Treating an outgoing field as sole ownership | Multiple roots may keep the object alive | Inspect Paths to GC Roots |
| Treating a size estimate as a fixed byte count across all JVMs | Javadoc does not guarantee it | Compare within the exact same JVM/config |
| Using reflection to walk all JDK fields | JPMS/internal objects have restrictions | Use supported heap snapshot tools |
| Forgetting weak/soft/phantom refs | Reachability is not the same as strong GC references | State edge semantics explicitly |
| Equating retained heap with RSS | Native/other memory is outside the Java heap | Separate heap and native metrics |
| Large retained = leak | May be an intentional cache | Verify lifecycle and trend |

### Retained size does not promise immediate RAM reclamation by GC

Retained size in a heap snapshot is typically interpreted as "the portion of memory no longer kept alive if the owner is properly removed in the root graph"; that does **not** guarantee GC runs immediately or that RSS drops correspondingly. The garbage collector, heap commitment, and OS page management are independent layers.

## 11. Checklist for JVM Investigation

**Before measuring:**

- [ ] Have you determined whether you need shallow size, reachable graph sum, retained heap, allocation, or RSS?
- [ ] Has the Java agent received `Instrumentation` from `premain/agentmain`?
- [ ] Are you avoiding calling `getObjectSize(null)` or expecting the API to traverse graphs automatically?
- [ ] Are the JVM/vendor environment, compressed pointers, and alignment recorded if comparing sizes?
- [ ] If traversing a graph yourself, have the starting roots and edges been defined precisely?

**When computing the graph:**

- [ ] Is deduplication done by identity?
- [ ] Are cycles/shared objects handled?
- [ ] Is it explicitly documented which fields/arrays/JDK private internals are skipped?
- [ ] Could weak/soft/phantom references and concurrent mutation affect the result?
- [ ] Have you avoided calling a Node-only sum the JVM retained size?
- [ ] If true retained size is needed, are you using a heap-root/dominator analyzer?

**When concluding:**

- [ ] Did you inspect all three: Histogram, Dominator Tree, and Paths to GC Roots?
- [ ] Did you compare metrics across lifecycle/GC before concluding a leak?
- [ ] Did you distinguish off-heap memory from heap?
- [ ] Are heap dumps and sensitive data properly protected?
- [ ] Do the metric names in dashboards/reports accurately reflect the measurement performed?

## 12. Self-Check Questions

**1.** Does `getObjectSize(new Object[1000])` include the shallow sizes of the objects pointed to by the array?

> No. The array contains reference slots, not the referenced instances inline.

**2.** Does `getObjectSize(new byte[1_000_000])` reflect the inline primitive bytes?

> Yes. A primitive array is an object whose elements are stored inline, although the exact byte layout depends on the JVM.

**3.** Why is a `HashSet` based on `equals` unsafe for deduplicating heap objects?

> Two objects with different identities can be equal by value; heap accounting must keep each allocation separate.

**4.** A reaches S, and B also reaches S from another root. Does A dominate S?

> No. There is a path through B to S that bypasses A.

**5.** Is `onlyA(model)=A,U` in the example the JVM retained size of A?

> No. It is the difference of two reachable sets along Node.left/right edges; the JVM still has local variables/roots and other objects.

**6.** Can an object with a small shallow size have a large retained size?

> Yes, when it dominates a large graph that is kept alive only through it.

**7.** What should you inspect to find out who is keeping an object alive?

> Heap dump, Paths to GC Roots, and Dominator Tree; then cross-check with the lifecycle.

**8.** Why does `getObjectSize(directBuffer)` not reflect the buffer's entire native memory?

> The API only measures the shallow Java wrapper, not the entire native backing region.

**9.** Does a large retained size prove a leak?

> Not yet. It must be checked against lifecycle, cache policy, roots, and trend.

**10.** Does an increasing allocation rate necessarily mean retained heap is increasing?

> No. Objects can be allocated rapidly yet die quickly.

**11.** Is `getObjectSize(x)` a fixed byte count across all JVMs/vendors?

> No. The Javadoc defines it as an implementation-specific approximation that can change even within a single run.

**12.** What should you do if you want the unique total from roots A and B with shared nodes?

> Union the reachable sets by identity before summing shallow sizes, rather than directly adding the two sums when shared nodes exist.

## 13. Official Documentation and Tools

- Java SE 17, `Instrumentation.getObjectSize(Object)` — implementation-specific approximation, overhead, and NullPointerException: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Java SE 17, `java.lang.instrument` — agent `premain` and manifest: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- Eclipse MAT, **Dominator Tree** — dominates, immediate dominator, retained set: https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/concepts/dominatortree.html
- Eclipse MAT, **Basic Tutorial** — Histogram, Dominator Tree, Paths to GC Roots: https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/gettingstarted/basictutorial.html
- Eclipse MAT, **Finding Memory Leak** — leak suspects, root paths, and retained ownership: https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/reference/findingmemoryleak.html
- Java SE 17, `jcmd` — tool for capturing heap dumps and checking options: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
