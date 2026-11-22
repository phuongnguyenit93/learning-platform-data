# Escape Analysis and Scalar Replacement of Aggregates in HotSpot

## 1. Does an object appearing in Java source have to be allocated on the heap?

Not necessarily. Java allows writing `new Point(...)` to create an object **semantically**, but the program can only observe the behaviors that the language guarantees: field values, reference identity when observable, method call results, exceptions, synchronization, etc. The JVM is permitted to optimize the implementation if it preserves those behaviors.

In **HotSpot/OpenJDK Java 17**, the **C2** optimizing compiler can use **escape analysis (EA)** to determine whether a created object can be observed outside the scope under consideration. If an object does not escape and satisfies implementation conditions, **scalar replacement of aggregates (SRA)** can transform operations on the object into operations on **component values**, such as `x` and `y`. When that happens, the actual allocation and some loads/stores/locks can be eliminated from machine code.

Three concepts must be kept distinct:

1. **Escape analysis** is the **analysis** step of data flow and reference paths to evaluate what scope an object can escape.
2. **Scalar replacement** is a **code transformation**: replacing an aggregate object with independently trackable scalar fields/values; when successful, it can **eliminate the allocation**.
3. **Lock elimination** is the removal of unnecessary synchronization when the compiler proves a monitor produces no observable effect between threads; it is related to EA but is **not synonymous with SRA**.

One extremely important note: **HotSpot C2 Java 17 does not generally turn non-escaping Java objects into heap objects allocated on the Java stack**. When scalar replacement succeeds, the object may **not be materialized** as an allocation on the hot execution path; field values may reside in CPU registers, stack slots of the compiled frame, or be optimized further. This is **different** from allocating a complete object with a header on the stack.

### Learning Objectives

After this lesson, you will be able to explain:

- How an object escapes a method, thread, or compiled graph scope.
- Why `return new Point(...)` and `return p.x + p.y` lead to different optimization opportunities.
- How C2 observes the allocation/reference graph and uses **inlining, alias/points-to analysis** as its foundation.
- How scalar replacement can eliminate `new`, field loads/stores, and reduce GC pressure.
- What the compiler must preserve when there are exceptions, side effects, identity, locks, and deoptimization.
- Why **not escaping does not guarantee zero allocation**.
- How to verify using JMH, JFR, allocation counters, and the proper HotSpot flags of JDK 17.

All Java examples below are runnable on **Java 17+** when written as full files; only snippets explicitly marked as *fragment/pseudocode* are not standalone. Any results that depend on the compiler/GC are explicitly noted as having **no single output**.

## 2. Java heap, stack, and the optimizer's “virtual” objects

### Java-level semantics are not memory layout

In Java:

```java
Point point = new Point(3, 4);
int sum = point.x + point.y;
```

This is an illustrative *fragment*. Semantically, the program initializes a `Point` and reads two fields. However, the compiler can prove that no other part of the code needs to recognize `point` as an independent object.

Diagram before optimization:

```text
Bytecode / object model:
  new Point
  dup
  iconst_3
  iconst_4
  invokespecial Point.<init>
  astore point
  aload point
  getfield x
  aload point
  getfield y
  iadd

  -> sum
```

**Illustrative** diagram after optimization:

```text
  point.x -> scalar x = 3
  point.y -> scalar y = 4

  sum = x + y = 7

  Object header/allocation does not need to exist on the hot path
  if the compiler has proven all safety conditions.
```

This is **not machine-code disassembly** of a verified run. C2 may even constant-fold `3 + 4` into `7`, or inlining/escape analysis may not have run while the program is still cold.

### 4 things to distinguish

| Component | Explanation |
| --- | --- |
| **Java heap object** | Runtime entity managed by GC when the object is actually allocated |
| **Java reference** | Value used by the program to reference an object; there is no standard raw address API |
| **Compiled frame/register values** | Where the CPU/JIT can store `x`, `y` values or intermediate data |
| **Virtual/scalar-replaced object** | A **logical** representation in the optimizer, which may have no corresponding physical allocation on the hot path |

You cannot measure “which stack address a Java object resides at” simply by having `new` in source. Programmers do not control that layout and should not impose a requirement that “every short-lived object must be stack allocated” on HotSpot Java 17.

## 3. “Escape” means escaping from where?

There are at least two important boundaries:

- **Method escape:** a reference to the created object can exist or be used outside the activation/analysis scope of the method.
- **Thread escape:** the object can be observed/accessed by another thread, typically via a field of a shared object, a static reference, or an equivalent publication mechanism.

Example:

```java
final class Pair {
    int a, b;
    Pair(int a, int b) {
        this.a = a;
        this.b = b;
    }
}
```

This is an illustrative class without `main`. Scenarios:

```java
static int localOnly(int x) {
    Pair p = new Pair(x, 2);
    return p.a + p.b;
}

static Pair returnsObject(int x) {
    return new Pair(x, 2);
}
```

The two methods are *fragments*, which can be placed inside an enclosing class.

- In `localOnly`, if all uses are known, `p` has a very good chance of being scalar-replaced.
- In `returnsObject`, the caller receives a **reference** to Pair. At the standalone method boundary, Pair appears to escape. However, if the caller **is inlined into the same compiled graph** and only reads fields, the compiler can still eliminate the allocation across the method boundary.
- If the caller stores the reference into a static field or returns it to an environment that is not inlined/analyzed, the object usually needs to be materialized.

**Escape is scoped to the analysis.** An object escaping a small method does not necessarily escape the entire **inlined compilation graph**; and an object that does not cross to another thread may still have to be heap-allocated to preserve reference identity or because the compiler is unable to prove optimization conditions.

## 4. Escape states commonly used in HotSpot documentation

HotSpot Server Compiler documentation describes familiar analysis states:

| State | Practical interpretation | Model example |
| --- | --- | --- |
| **NoEscape** | The compiler proves the candidate does not escape and may be scalar-replaceable when relevant conditions are met | Create `Point`, only read fields and then return `int` |
| **ArgEscape** | The object crosses an argument/callee boundary but is not concluded to globally escape in the corresponding analysis | Passed into a helper whose behavior is determined by the compiler |
| **GlobalEscape** | The object can leave the scope of control/thread or exist where external code accesses it | Stored in a static field, returned reference out of the graph, published to a shared object |

**Do not infer “NoEscape = heap allocation is definitely removed”.** This is an **analysis result** and must additionally satisfy conditions of the scalar replacement pass. Object size, graph shape, merges, arrays, calls, and compiler heuristics can prevent the transformation.

Nor should the name `GlobalEscape` be viewed as a complete description of every code path in source: C2 uses data-set/flow-insensitive analyses and can reach a **conservative** conclusion when there is a branch eligible to escape.

## 5. Which reference paths make an object escape?

Common ways:

### Returning a reference

```java
static Pair makePair(int a, int b) {
    return new Pair(a, b);
}
```

The caller can retain Pair. If the optimizer does not see the caller or the caller actually uses the reference long-term, the allocation usually must exist. But if the caller is inlined and the result only computes `pair.a + pair.b`, optimization can still occur.

### Assigning to a static field

```java
static volatile Object published;

static void publish(int a) {
    published = new Pair(a, 10);
}
```

These are **fragments**. The value in `published` is published to other code. If the assignment is observable, the compiler cannot simply keep `a`/`b` in method registers and pretend the object reference actually existed in the static field.

### Storing into another escaped object

```java
static final class Holder {
    Object value;
}
static void attach(Holder external, int x) {
    external.value = new Pair(x, 1);
}
```

If `external` can be accessed by other code after the call, Pair also becomes accessible through the holder. The escape conclusion depends on receiver/holder analysis and the compilation graph.

### Passing to another thread / queue / callback

```java
static void submit(java.util.concurrent.Executor executor, int id) {
    Pair p = new Pair(id, id + 1);
    executor.execute(() -> System.out.println(p.a + p.b));
}
```

This is a fragment. The Executor may process the lambda after the `submit` method has finished; the lambda captures `p`, so the compiler must preserve reference semantics along with the data across that lifecycle. However, the compiler can optimize internal parts of the lambda/Pairs under narrow conditions; do not assert there are always exactly two allocations (Pair and lambda) for every compiler.

### Calling a method not sufficiently analyzed by the compiler

```java
static int passUnknown(Pair p, java.util.function.ToIntFunction<Pair> f) {
    return f.applyAsInt(p);
}
```

If the callsite to a concrete implementation has not been inlined or might publish Pair, the optimizer may have to be conservative. **Not every argument passed to a method is automatically GlobalEscape**; static/interprocedural analysis or inlining can prove the callee only reads fields.

## 6. C2 relies on points-to / connection graph

In HotSpot C2, Escape Analysis uses a **connection graph (points-to/alias relationships)** analysis structure over the compiler IR to track allocations and which references can point to which objects.

Model:

```text
new Pair(3, 4)
     |
     v
  P: object allocation node
    / \
   v   v
 field a field b
   |     |
   3     4

Local reference p ----------> P
Static/reference escape? ---> not seen in compiled graph

=> P may be NoEscape / scalar-replaceable
```

If reference `p` is assigned to a static/returned field, the graph contains an additional edge to the escape boundary:

```text
Local p -> P -> static published
                      |
                      v
                reachable beyond scope

=> Compiler must account for the possibility that P escapes
```

This is a **conceptual** diagram, not the exact internal format of `escape.cpp`. C2 must handle aliasing, phi nodes, field loads/stores, nested objects, method inlining, and exception paths. Sometimes a path looks local in source, but the compiler cannot prove it due to merging multiple references.

### What does flow-insensitive mean?

A limitation analyzed by OpenJDK: C2's traditional EA algorithm is **flow-insensitive** in important respects. If the same allocation has **one escaping branch**, the compiler may conservatively treat it as escaping even on the frequent non-escaping path.

```java
static volatile Object shared;
static int conditionalEscape(int x, boolean publish) {
    Pair p = new Pair(x, 2);
    if (publish) {
        shared = p;
    }
    return p.a + p.b;
}
```

This is a fragment. Logically, when `publish=false`, the object does not need to be retained outside the method. But **do not automatically conclude** that HotSpot Java 17 will generate a zero-allocation fast path specifically for the false branch. Partial escape analysis requires deeper transformations, and the C2 implementation has limitations; different JDK 17u updates may improve some specific cases.

Do not take the statement “EA analyzes all possible paths” as a guarantee that **path-sensitive partial allocation** exists for every code shape.

## 7. Scalar replacement of aggregates (SRA): operating on each field

Suppose:

```java
static final class Point {
    int x;
    int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }
}

static int compute(int input) {
    Point p = new Point(input, input + 1);
    p.x += 2;
    return p.x * p.y;
}
```

These are fragments, without `main`. The field operations can be represented as:

```text
Original logical object:
  p = new Point(input, input+1)
  p.x = p.x + 2
  result = p.x * p.y

Scalar form:
  x = input
  y = input + 1
  x = x + 2
  result = x * y

If p does not have to be materialized, eliminate allocation/header/field memory ops.
```

Note that the compiler may place `x`, `y` in registers or stack slots depending on the register allocator. There is no promise that “each field becomes exactly one Java local variable on the stack”. Nor is there a promise that C2 generates the exact same number of machine instructions as the diagram.

### Why does reducing allocation help GC?

If each request creates thousands of small temporary wrappers/points and the optimizer eliminates many allocations:

- Reduces bytes allocated on the Java heap.
- Reduces the number of object headers and related initialization/write operations.
- Reduces pressure on Eden/TLAB and can reduce young GC frequency.
- Reduces the amount of data GC must scan or copy if the object truly does not exist.
- Allows the compiler to proceed with constant propagation, dead-store elimination, and strength reduction.

However, **not every reduced allocation translates into a proportional speedup**. HotSpot TLAB allocation is already very fast; other bottlenecks such as I/O, CPU branch misprediction, or memory access may dominate.

## 8. Complete Java 17: temporary object used only for arithmetic

Create the file **`ScalarPointDemo.java`**:

```java
public class ScalarPointDemo {
    static final class Point {
        final int x;
        final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }
    }

    static int score(int input) {
        Point p = new Point(input, input + 1);
        return p.x * 2 + p.y;
    }

    public static void main(String[] args) {
        System.out.println("score3=" + score(3));
        System.out.println("score10=" + score(10));
    }
}
```

Compile/run Java 17:

```bash
javac --release 17 ScalarPointDemo.java
java ScalarPointDemo
```

**Exact stdout:**

```text
score3=10
score10=31
```

The formula is `2×input + (input+1) = 3×input+1`. The `Point` object does not escape `score` according to the Java source; in principle it is suitable for EA/SRA after JIT compilation/inlining. **Two lines of output do not prove `new Point` was eliminated.** The JVM may not have C2-compiled yet, or the compiler may have performed other optimizations.

If you want to study the effect of EA specifically, you need to measure in a sufficiently long-running repeated workload and compare flags/metrics on the same JVM; do not state any “object allocations = 0” figure as a default fact.

## 9. Relationship between inlining and escape analysis

Inlining replaces a method call with the callee's logic inside the **compiled graph**. This can help EA see that an object is only used to read fields, even though it was passed across a source method boundary.

Example:

```java
static int consume(Pair p) {
    return p.a + p.b;
}

static int calculation(int x) {
    Pair temporary = new Pair(x, x + 1);
    return consume(temporary);
}
```

These are fragments. If `consume` is inlined, the optimizer can see:

```text
new Pair(x, x+1)
    |
    +--> load a
    +--> load b
    |
    v
return a+b

=> Pair allocation can be scalar-replaced if it does not escape.
```

If `consume` is too large, has unknown/native calls, or **is not inlined**, it may be difficult for the compiler to prove the necessary properties. C2 has some limited interprocedural EA capabilities, but it must **not** be assumed that the optimizer sees through every method/library boundary.

### Inlining is not always good

C2 has **inline budgets**, limiting method size/call depth, and must balance compiled code size, compile time, CPU instruction cache, and runtime throughput. Forcing too much inlining can bloat compiled methods, complicate the EA graph, and reduce effectiveness in other code regions.

Therefore, the statement “splitting into small methods always makes escape analysis fail” is also false: inlining can stitch them back together; conversely, a very large method with complex control flow does not mean EA will succeed.

## 10. A non-escaping object may still not be scalar-replaced

Common obstacles (not sufficient conditions to **definitely** fail in every release):

- **Control-flow merges:** the same reference variable after an `if` can point to two different allocations; the compiler needs to handle phi nodes/aliasing.
- **Conditional escape:** the object only escapes on one branch, but flow-insensitive EA may evaluate conservatively.
- **Non-inlined calls:** the object is passed to a method not sufficiently analyzed or a native call.
- **Loop-carried object state:** an object is updated/passed across multiple iterations with complex references/merges.
- **Identity-sensitive behavior:** the object genuinely needs reference identity, a monitor, an identity hash, or native/reflection interaction.
- **Arrays:** variable index access, unknown sizes, aliasing, or array-copy semantics can make scalarization harder.
- **Large/nested object graphs:** the cost of representing each field/element can exceed compiler limits.
- **Deoptimization state:** the JIT must ensure enough information exists to reconstruct the object with the right fields/identity when needed.
- **Escape through exceptions:** an exception object or cause/stack trace that is returned/thrown can have a different lifetime and observation than temporary math objects.
- **JVMTI/agent/debug instrumentation:** certain runtime observations/flags can change which optimizations can be applied.

**NoEscape is not a code-generation guarantee.** A small non-escaping object may still be heap-allocated if C2 has not run yet, compiler budgets do not allow it, or the analysis is conservative.

### Control-flow merge illustration

```java
static int mergeExample(boolean chooseNew, int x) {
    Pair p = new Pair(1, 2);
    if (chooseNew) {
        p = new Pair(x, x + 1);
    }
    return p.a;
}
```

This is a fragment. At `return`, `p` can be the old or new object. An ideal optimizer could transform the code into `chooseNew ? x : 1`; however, **it cannot be asserted that C2 Java 17 always scalar-replaces both allocations**. Different JDK 17 updates may have different merge-handling capabilities; read the exact JDK build and test rather than memorizing a “C2 never does X” list.

## 11. Lock elimination: removing useless synchronization when an object is not shared

Java `synchronized` can be applied to an object that is never shared with another thread:

```java
static int localLock(int x) {
    Object privateLock = new Object();
    synchronized (privateLock) {
        return x + 1;
    }
}
```

This is a method fragment. If the compiler proves no other thread can observe `privateLock` and all other semantics are preserved, HotSpot C2 can **eliminate locking/unlocking operations** that have no actual contention effect.

**Points to distinguish:**

- EA detects the degree to which an object can escape.
- Lock elimination removes certain monitor-enter/exit operations from compiled code when valid.
- Scalar replacement can simultaneously eliminate the allocation of the lock object, but **the two optimizations are not synonymous**.
- There is no guarantee that the Java compiler will remove `synchronized` in all cases.
- When the lock monitor is an object that can be shared/needs thread coordination, the compiler **must not** remove the synchronization effect required by the Java Memory Model.

### Why must synchronized still be correct with exceptions?

Java `synchronized` must ensure the monitor is released when the block exits or throws an exception. If the JIT proves the lock is completely thread-local and optimizes it away, it must still preserve all **Java-visible results and exception behavior**, even when code is deoptimized or switches execution representations.

Do not “manually optimize” by deleting `synchronized` on shared data just because you once saw JIT lock elimination in a microbenchmark. The JMM still applies in full.

## 12. Complete Java 17: synchronizing on a private object

Create the file **`PrivateLockDemo.java`**:

```java
public class PrivateLockDemo {
    static int guardedSum(int a, int b) {
        Object lock = new Object();
        synchronized (lock) {
            return a + b;
        }
    }

    public static void main(String[] args) {
        System.out.println("sum=" + guardedSum(10, 32));
        System.out.println("same=" + (guardedSum(1, 2) == 3));
    }
}
```

```bash
javac --release 17 PrivateLockDemo.java
java PrivateLockDemo
```

**Exact stdout:**

```text
sum=42
same=true
```

The `synchronized` statement is valid Java code; whether the compiler eliminates the runtime monitor **is not directly observable from stdout**. Use debug/compiler diagnostics or controlled benchmarking if the goal is to confirm lock elision, not the timing of a single call.

## 13. Identity, hash code, and object-observable behavior

A temporary object used only to read two fields seems scalar-replaceable. But there are operations that make **identity** part of observable semantics:

```java
static boolean sameReference(Object x, Object y) {
    return x == y;
}
```

This is a fragment. When identity is used, HotSpot can still optimize some situations using aliasing analysis **without necessarily materializing the object**, but it must preserve:

- `a == b` returns true if both references represent the same logical object.
- Two objects distinct in identity must not be merged into one object due to scalar replacement.
- `System.identityHashCode(obj)` has stable semantics for **the same object** (not a raw memory address), and may affect the ability to eliminate the allocation.
- `synchronized(obj)`, `wait`, `notify`, JNI handles, and identity-sensitive reflection/agent observations require the exact contract.

**Avoid overclaiming:** “calling `identityHashCode` always prevents EA” is not necessarily true for every optimizer, and “if an object does not escape then every identity operation is free” is also false. Only when you understand compiler codegen and deoptimization obligations can you draw conclusions for a specific JDK/build.

### A Java object does not become a value type just because of SRA

A normal Java class still has **reference identity semantics**. Scalar replacement is an internal codegen choice of the JIT for **an execution context**; it does not turn the class into a primitive type, an identity-less record value type, or alter the API contract.

## 14. Deoptimization: when a virtual object must take Java shape again

HotSpot C2 often optimizes based on dynamic profiles and guarded assumptions. If an assumption no longer holds, the JVM can perform **deoptimization** to restore an execution state compatible with the interpreter or another compiled tier.

Suppose in optimized code:

```text
Java source:
  Point p = new Point(3, 4);
  int total = p.x + p.y;

Optimized state:
  virtual Point {x=3, y=4}
  total = 7
  no heap object on the hot path
```

If deoptimization needs local `p` to continue existing with Java semantics, the VM may have to **materialize/reallocate** the corresponding object based on metadata recording its fields and references.

```text
Nmethod optimized execution
  |
  | uncommon trap / invalidated assumption
  v
Deopt metadata:
  virtual object Point(x=3,y=4)
  |
  v
materialization / reconstruction when needed
  |
  v
Interpreter-compatible frame, exact Java behavior
```

**Two misconceptions to avoid:**

1. Not every scalar-replaced object “lives on the stack” from the start, and then deopt merely copies that whole object to the heap. Sometimes **no physical object existed before deopt**.
2. Not every deoptimization definitely recreates an object. The compiler/runtime only performs the operations necessary to preserve the semantics of the **live state** that must be recovered.

Deoptimization cost can include reconstructing states, materializing virtual objects, and switching tiers. Therefore, an optimization that is good on the hot path can still cause spikes if speculative assumptions change frequently.

## 15. Java 17 example: escaping when returning an object, not escaping when returning only a scalar

Create the file **`EscapePathDemo.java`**:

```java
public class EscapePathDemo {
    static final class Pair {
        final int left;
        final int right;

        Pair(int left, int right) {
            this.left = left;
            this.right = right;
        }
    }

    static int computeScalar(int value) {
        Pair pair = new Pair(value, value + 2);
        return pair.left + pair.right;
    }

    static Pair createReference(int value) {
        return new Pair(value, value + 2);
    }

    public static void main(String[] args) {
        int a = computeScalar(5);
        Pair b = createReference(5);
        System.out.println("scalar=" + a);
        System.out.println("pair=" + (b.left + b.right));
        System.out.println("sameResult=" + (a == b.left + b.right));
    }
}
```

```bash
javac --release 17 EscapePathDemo.java
java EscapePathDemo
```

**Exact stdout:**

```text
scalar=12
pair=12
sameResult=true
```

This illustrates the **API difference** between a method returning `int` and a method returning an object. `createReference` returns an object to the caller, so at the method boundary it escapes. However, if the JIT **inlines both `createReference` and the field reads in `main`**, it can still eliminate the allocation in the compiled graph. Therefore, the program **does not prove** which exact method actually heap-allocated.

Do not use `System.identityHashCode` to read an object's address to “prove” the object resides on the stack or heap.

## 16. Interprocedural EA and call graph limitations

C2 can analyze some callees to understand object arguments without necessarily inlining everything, but its scope still has limits regarding bytecode, call shape, virtual dispatch, and compiler budget.

**Inlining is especially important** because it expands the compiled graph, helping the optimizer see all uses of a candidate object. When code has polymorphic dispatch, reflection, JNI, or native calls, it is harder for the compiler to prove that a caller-owned temporary object does not escape.

Example:

```java
interface Consumer {
    int use(Pair pair);
}

static int callThroughInterface(Pair pair, Consumer consumer) {
    return consumer.use(pair);
}
```

This fragment has the potential for receiver `consumer` to change runtime type; C2 can devirtualize/inline via type profile/CHA in some cases, but does not promise it will always succeed.

Do not write that “an object passed into another method definitely escapes”, because that is false when the callee is inlined or the compiler knows it only reads fields. Nor write “the compiler always sees through every call”, because that is overly optimistic.

## 17. Is scalar replacement for arrays different from object fields?

For an object with a fixed number of fields, the optimizer can easily replace each field with SSA values. For arrays, the compiler must handle:

- **Array length:** is it known or reasonably bounded?
- **Index:** is it a constant, a small known range, or variable and hard to prove?
- **Aliasing:** multiple references pointing to the same array, which calls is the array passed through?
- **Bounds checks:** can they be eliminated while preserving exception semantics?
- **Arraycopy/clone:** are their semantics and lifetime suitable for scalarization?
- **Object/reference elements:** do the inner objects also escape or need to preserve identity?
- **Loop-carried state:** does an array updated across iterations complicate the graph?

A small temporary `int[]` with constant indexes can be a candidate. However, **there is no guarantee HotSpot Java 17 automatically eliminates every `new int[3]`**; constraints/optimizations depend on the build and compiled graph.

### Example illustrating only an optimization opportunity

```java
static int fromSmallArray(int x) {
    int[] values = {x, x + 1, x + 2};
    return values[0] + values[2];
}
```

This is a fragment. If the compiler has enough information, it can simplify this to `2*x + 2`. Do not use this code to promise that `int[]` does not exist on the heap in every Java implementation.

## 18. Traditional C2 EA has limitations with flow merges and loops

According to OpenJDK research reports on escape analysis:

- An allocation that escapes on only **one branch** can still be treated conservatively.
- **Phi/merge** between two references from different allocations can restrict scalar replacement.
- **Loop-carried allocations** and values flowing across iterations can be difficult to optimize.
- **Non-inlined helpers**, bytecode size limits, and complex call graphs can block NoEscape candidates.
- Improvements such as **allocation merge reductions** in certain JDK 17u updates can change results for specific patterns; you must pin the **17.0.x vendor/build** to draw conclusions.

This explains why two snippets that look “equally non-escaping” in source can have very different allocation rates on JMH.

### Flow-insensitive does not mean no control flow analysis at all

It is a way to describe a **characteristic of the EA algorithm** and where the compiler must make conservative conclusions; it does not mean C2 is completely unaware of `if`, SSA, branches, or types. The compiler has many other passes that can optimize logic even if EA/SRA does not handle the entire pattern.

## 19. Related flags on HotSpot Java 17

Flags commonly used in EA/SRA experiments:

| Flag | General role |
| --- | --- |
| `-XX:+DoEscapeAnalysis` | Enables EA; usually enabled by default with C2 where applicable |
| `-XX:-DoEscapeAnalysis` | Disables EA for controlled comparison |
| `-XX:+EliminateAllocations` | Enables allocation elimination/SRA when conditions are met |
| `-XX:-EliminateAllocations` | Disables the allocation elimination part to isolate its impact |
| `-XX:+EliminateLocks` | Enables certain lock eliminations when valid |
| `-XX:-EliminateLocks` | Disables lock elimination for comparison |
| `-XX:+PrintCompilation` | Observes compilation events/tiers (does not say whether allocation was removed) |
| `-XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining` | Observes inlining decisions on supported builds |
| `-XX:-TieredCompilation` | Changes tiering strategy; not a simple switch to turn on EA |

**Do not assume every HotSpot build accepts every flag in every mode.** Check flags in the running runtime:

```bash
java -XX:+PrintFlagsFinal -version
```

Filter the names `DoEscapeAnalysis`, `EliminateAllocations`, and `EliminateLocks` using an OS-appropriate tool. Do not hard-code a single default across all JDK distributions.

**Avoid instructing to enable `-XX:+PrintEscapeAnalysis` or `-XX:+PrintEliminateAllocations` as commands guaranteed to run on product HotSpot builds.** These options are usually only available in **non-product/debug builds**; on a production VM they may be rejected. Use supported JMH/allocation profiling/assembly diagnostics and specify the build.

## 20. Why shouldn't you measure EA with a single System.nanoTime?

Suppose:

```java
long start = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    new Point(i, i + 1);
}
System.out.println(System.nanoTime() - start);
```

This is a fragment that is **not a reliable benchmark**:

- **Dead-code elimination:** the object is unused; the compiler can very easily eliminate the entire logic.
- **Constant folding**: inputs and calculations can be precomputed.
- **Loop optimizations**: unrolling, elimination, or vectorization make the number of operations differ from source.
- **JIT warmup:** a short test measures interpreter/C1/C2 compilation mixed together.
- **GC/OS scheduling** causes latency to vary with the system.
- **Object allocation** on TLAB is very fast; the difference in a single loop can be small with high variance.
- **Disabling an EA flag** can affect many other optimizations, so you cannot assume every CPU delta is pure “Point allocation time”.

Use **JMH** with forks/warmup/measurement/Blackhole or an observable return value. Combine **allocation rate per operation**, CPU time, and latency, instead of just a single nanoseconds number.

## 21. Measurement model: comparing two JVM configurations

When studying EA, you can perform **two separate runs of the same workload**:

```bash
java -XX:+PrintCompilation ScalarPointDemo
java -XX:-DoEscapeAnalysis ScalarPointDemo
```

The commands above run the example logic but **cannot** serve as a benchmark: the program exits very quickly, and it is not certain there is a C2-compiled hot path. Use an appropriate JMH benchmark and run multiple forks to compare:

- A: default EA on.
- B: `-XX:-DoEscapeAnalysis`.
- C if needed: `-XX:-EliminateAllocations` while keeping EA per the VM build.
- Other flags, heap, GC, threads, and machine load kept equivalent.
- Sufficient warmup so both run at comparable compilation levels.

**Correct conclusion:** if A has lower allocation bytes/op than B in a sufficiently reliable benchmark, then EA/SRA may be contributing, but you need to check other effects, codegen, and compiler diagnostics. Do not attribute every difference solely to “Point on stack”.

### Understanding the bytes/op unit

- JFR's allocation profiling can use sampled events, and is **not guaranteed** to count every single allocation down to the byte.
- Per-thread allocated-bytes counters from `com.sun.management.ThreadMXBean` (when supported/enabled) have per-thread semantics, unlike process RSS/heap used.
- Heap used snapshots decrease due to GC; **delta used heap is not cumulative allocated bytes**.
- JMH `gc.alloc.rate.norm` can help quantify bytes/op with an appropriate profiler, but is still a tool/implementation-specific measurement requiring warmup and forks.
- Observing “0 B/op” allocation **in a specific benchmark** is not a law that every production call allocates nothing.

## 22. Example measuring allocated bytes using the extended HotSpot API (Java 17)

In the JDK's `jdk.management` module, the `com.sun.management.ThreadMXBean` interface provides functionality to measure heap memory allocated **per thread** if supported by the VM. Measuring this example has **dynamic output**, and does not print a fixed byte value.

Create the file **`ThreadAllocationProbe.java`**:

```java
import java.lang.management.ManagementFactory;

public class ThreadAllocationProbe {
    static volatile int sink;

    static int calculation(int i) {
        int[] numbers = {i, i + 1, i + 2};
        return numbers[0] + numbers[2];
    }

    public static void main(String[] args) {
        java.lang.management.ThreadMXBean base =
                ManagementFactory.getThreadMXBean();

        if (!(base instanceof com.sun.management.ThreadMXBean bean)
                || !bean.isThreadAllocatedMemorySupported()) {
            System.out.println("thread-allocation=unsupported");
            return;
        }

        if (!bean.isThreadAllocatedMemoryEnabled()) {
            bean.setThreadAllocatedMemoryEnabled(true);
        }

        long tid = Thread.currentThread().getId();
        long before = bean.getThreadAllocatedBytes(tid);

        int local = 0;
        for (int i = 0; i < 100_000; i++) {
            local += calculation(i);
        }
        sink = local;

        long after = bean.getThreadAllocatedBytes(tid);
        System.out.println("supported=true");
        System.out.println("deltaNonnegative=" + (after >= before));
        System.out.println("checksum=" + sink);
    }
}
```

```bash
javac --release 17 ThreadAllocationProbe.java
java ThreadAllocationProbe
```

In an environment where `ThreadMXBean` is supported/enabled and returns valid counters, the program prints:

```text
supported=true
deltaNonnegative=true
checksum=1410165408
```

**Arithmetic check:** one call to `calculation(i)` returns `i + (i+2) = 2i+2`. The mathematical arithmetic sum from `i=0` to `99,999` is `10,000,100,000`; Java `int` overflows modulo 2³² so the result is `(10,000,100,000 mod 2³²) = 1,410,165,408`. On an unsupported VM, it only prints:

```text
thread-allocation=unsupported
```

**Warning:** `getThreadAllocatedBytes` can return a negative number such as `-1` in disabled/unavailable situations; production code needs to handle that case. This simple demo mainly illustrates the API and **does not print the allocation delta** to avoid citing a JIT/GC-dependent number. The JVM may also disallow changing the measurement state in some environments; the program may then require appropriate permissions/configuration.

If the goal is to compare two JIT configurations, the API should be used in a benchmark with sufficient warmup, subtracting measurement overhead, measuring repeatedly, and confirming the method is actually C2 compiled.

## 23. Checking int overflow arithmetic under scalar replacement

EA/SRA **is not permitted to change Java's arithmetic rules**. In the examples:

- `int` arithmetic wraps around modulo 2³² on overflow (in signed two's-complement representation), unless overflow-checking methods like `Math.addExact` are used.
- Scalar replacement only changes how fields are stored/passed, not the result of integer operations.
- Object field initialization/default values must still be preserved: if a field is not assigned in the constructor, Java has default values 0/false/null according to type.
- Side effects in a constructor (writing to static, I/O, throwing exceptions) cannot be arbitrarily removed just because the local object does not escape; the compiler must preserve observable behavior.

### Example of a constructor with a side effect

```java
static int constructed;

static final class LoggedPoint {
    final int x;
    LoggedPoint(int x) {
        constructed++;
        this.x = x;
    }
}
```

This is a fragment. The compiler may not need to physically allocate `LoggedPoint` if appropriate, but **must not omit the effect of incrementing `constructed`** if that state can be observed under Java semantics. Do not use “scalar replacement = remove all statements in constructor” as a rule.

## 24. Relationship to Garbage Collection and live set

EA/SRA is not a GC algorithm. GC reclaims **objects that were allocated and are no longer reachable**, whereas scalar replacement can allow some logical objects to **never have to exist as a heap allocation on the hot path**.

Hypothetical example (this is not a benchmark):

```text
Before:
  1,000,000 operations/s
  each operation creates a temporary 24-byte object on the heap
  => about 24 MB/s payload/object layout depending on runtime

After successful EA/SRA:
  many temporary object allocations are eliminated
  => heap allocation rate can decrease significantly
  => young GC activity may decrease if the workload corresponds
```

Do not use 24 bytes as the “exact size” for a Java class: header, compressed oops, field alignment, and JVM flags determine the real object size.

**If an object does not escape but scalar replacement fails**, it can still be heap-allocated normally and then reclaimed by GC when no longer reachable. Thus, the Java model “objects are GC-managed on the heap” and EA/SRA optimization do not conflict at the user-behavior level.

## 25. Does scalar replacement make caches, listeners, or ThreadLocal leak less?

Not in the sense of removing objects held by **strong reference paths**. If an object is stored in a static cache, held by a callback, or placed in a long-lived `ThreadLocal`, it has a retention path that the VM must respect. EA must not “scalarize and make disappear” an object that the application can still access via that reference.

In those situations, the lifecycle must be fixed:

- Caches with capacity/weight bounds and eviction/invalidation.
- Listener/observer unsubscription when the owner closes.
- `ThreadLocal` remove/restore in `finally` after a request/task.
- Queues/backpressure limiting the number of concurrently retained objects.

EA is useful for **temporary allocations in hot methods**; it does not replace the garbage collector and does not fix **logical memory leaks** in an application.

## 26. Escape scenarios with records, StringBuilder, and wrappers

### Record does not automatically mean scalarized

Java 17 supports **records**:

```java
record PointRecord(int x, int y) {}

static int calculate(int n) {
    PointRecord p = new PointRecord(n, n + 1);
    return p.x() + p.y();
}
```

This is a fragment inside a suitable class. A record is a class with references/object identity in Java 17, not a primitive/value object. C2 can inline the accessor and scalar-replace the instance if eligible, but **record syntax does not guarantee allocation elimination**.

### StringBuilder in string concatenation

Some string concatenations in modern Java may be implemented using `invokedynamic`/StringConcatFactory and optimized with their own strategies. Do not conclude just because source has `new StringBuilder` or `+` that there is one allocation per operation, nor attribute every string concatenation optimization to EA/SRA. Use an allocation profiler for the exact JDK version.

### Boxing

`Integer.valueOf` may use a cache for certain values, or the JIT may unbox/optimize. Reduced boxing allocations have many causes: primitive specialization, caching, inlining, EA/SRA. Do not assert that every `Integer` wrapper seen in source is definitely scalar-replaced.

## 27. When should you write “EA-friendly” code?

Focus on writing **semantically clear** code:

1. Create temporary immutable-ish objects when it makes code easier to understand; do not manually pool every Point/DTO.
2. Keep lifetimes and ownership clear; avoid publishing references unnecessarily.
3. If a helper only reads fields, design the API to be inlinable; but do not fragment/force-inline code by intuition.
4. Avoid holding temporary graphs in static caches/listeners/ThreadLocal just for “debugging convenience”.
5. Use primitive locals when a value is truly scalar and the code is simpler, instead of forcing an awkward object model.
6. Do not replace a clean API with complex manual code just because EA has not been measured yet.
7. Do not manually remove synchronization when an object is shared.
8. Measure **allocation bytes/op**, GC pressure, and end-to-end latency before/after with a valid benchmark.
9. When C2 does not optimize, check control flow merges, method inlining, unknown calls, array indexes, and identity-sensitive operations.
10. Cross-check the exact **JDK 17 build**: C2 EA has improvements across 17u updates.

An important benefit of EA/SRA is that **the JVM can automatically optimize normal object-oriented code**. Clear, non-escaping, and appropriately inlined code can sometimes be both maintainable and fast.

## 28. Practice: designing a verifiable microbenchmark

On Java 17, you can create a JMH benchmark (JMH must be added as a separate dependency/setup; it is not a standalone Java SE class):

```java
// Conceptual fragment for a JMH benchmark; requires dependencies,
// JMH annotations and full build configuration.
@Benchmark
public int localPoint(BenchmarkState state) {
    Point p = new Point(state.value, state.value + 1);
    return p.x + p.y;
}
```

**This is a JMH fragment**, which will not compile with just `javac --release 17` without providing JMH and the declarations. Proper measurement approach:

1. Run sufficient warmup so C1/C2 have a chance to optimize the hot path.
2. Use multiple independent forks and multiple measurement iterations.
3. Vary data appropriately, avoiding the benchmark being completely constant-folded.
4. Check the `gc` profiler for bytes/op and normalized allocation rate.
5. Compare against `-XX:-DoEscapeAnalysis` on **a separate fork/experiment**.
6. Measure p50/p99/time/op/throughput depending on the goal.
7. Repeat on the same host, JDK vendor/build, and heap/GC settings.
8. If the delta is significant, analyze inlining/C2 compilation to support the cause.

Do not measure only `System.nanoTime()` on a single run. In a real application, reducing allocation bytes/op may not reduce end-to-end request latency if the bottleneck is I/O or locks.

## 29. Quick diagnostic table

| Symptom | Plausible hypothesis | What to check |
| --- | --- | --- |
| Many temporary Points but low GC allocation | C2 may be eliminating allocations | Warmup/JMH bytes/op, flags, inlining |
| `new` appears in `javap` bytecode | Bytecode preserves allocation semantics | Do not infer machine code definitely allocates |
| Scalar replacement does not happen | Object escapes or compiler conservatively bails | Inlining, merges, identity, arrays, runtime build |
| Object returned from method | Escapes at method boundary | Whether caller inlining/scalarization happens across graph |
| Static field holds Pair | Reference can be used outside method | This is an escape; GC must still preserve the object |
| Local `synchronized` has no visible overhead | Lock elimination may have occurred | JMH/compiler diagnostics and JMM semantics |
| Disabling EA increases bytes/op | EA/SRA may be helping the workload | Compare same JDK, tiers, profiler, and forks |
| JFR sees no allocation | May be optimized away or not sampled | Event/sampling semantics, alternative counters |
| Heap used does not drop right after fix | Heap commit/GC timing differs from allocation | Post-GC occupancy and GC/cgroup metrics |
| `PrintEscapeAnalysis` errors as invalid option | Product VM may not support debug-only flag | Use supported diagnostics; do not force the flag |
| Method is C2 compiled but still allocates | NoEscape is not enough; transformation has limits | JMH allocation, generated code/JIT logs |
| Workload polymorphism changes after warmup | Inlining/call graph and EA opportunities change | JFR/PrintInlining, compilation history |

## 30. Common misconceptions

| Misconception | What is true |
| --- | --- |
| “Every object with `new` must reside on the physical heap” | The compiler can eliminate the allocation if Java semantics are preserved |
| “Escape analysis is GC” | EA is a compiler analysis; GC reclaims already-allocated heap objects |
| “Non-escaping objects are always stack-allocated” | HotSpot C2 typically **scalar-replaces**, rather than performing object stack allocation as claimed |
| “NoEscape guarantees zero allocation” | Still subject to SRA eligibility, inlining, and graph/implementation limits |
| “Returning an object from a helper always forbids EA” | Caller/callee inlining can keep the allocation from escaping the compiled graph |
| “An object passed as an argument is GlobalEscape” | The callee may not retain it; ArgEscape/inlining/interprocedural analysis |
| “Static publication is unrelated to escape” | It exposes the reference to an owner outside the scope, which is crucial |
| “Scalar replacement turns a class into a primitive” | It is only an optimizer transformation; the class retains Java identity semantics |
| “EA deletes the entire constructor” | Side effects/exceptions/initialization semantics must be preserved |
| “Scalar values must live on the stack” | They can be in registers, compiled spills/stack slots, or optimized further |
| “Identity hash code is the object's address” | No; it is an identity-based hash, which can collide for different objects |
| “Lock elimination allows deleting all synchronized in source” | Shared synchronization/JMM must still be correct |
| “Debug-only PrintEscapeAnalysis always runs on production JDK” | Many product builds do not have that flag |
| “JFR has no event so it definitely didn't allocate” | Sampling/event thresholds can hide allocations |
| “C2 compilation definitely removes all temporary objects” | Depends on escape graph, size, merges, calls, and compiler heuristics |
| “`-XX:-DoEscapeAnalysis` only changes one `new`” | It can affect many optimizations/CPU/GC; benchmarks need to be controlled |
| “Increasing `-Xmx` enables SRA” | Heap sizing does not guarantee JIT scalar replacement |
| “Reducing allocation always reduces latency proportionally” | Throughput/latency depend on the entire workload |
| “Heap dump missing object X means X was definitely scalar-replaced” | The object could also have died/been GC reclaimed or not be in the dump |
| “Java 17 record is an identity-less value type” | Java 17 records are still reference classes with identity |

## 31. Self-check questions

**Question 1:** In `new Point(3,4)` followed only by reading `x+y`, what allows the JIT to eliminate the allocation?

**Answer:** EA determines the object does not escape and SRA is eligible to turn fields into scalar values, while Java-visible semantics remain unchanged.

**Question 2:** Does NoEscape necessarily mean zero heap allocations?

**No.** NoEscape is an analysis result; SRA still has constraints and the compiler/JVM runtime may not have optimized it yet.

**Question 3:** A method returns `Pair` to its caller. Can it still be scalar-replaced?

**Possibly**, if the JIT inlines the method into the caller and the entire compiled graph does not need an actual reference object, though it is not guaranteed.

**Question 4:** Why can calling a non-inlined helper make EA harder?

The compiler may not see whether the helper publishes the object, so it must analyze conservatively.

**Question 5:** Is scalar replacement allocating a full Point object on the Java stack?

**No.** It can eliminate the object allocation and replace fields with registers/scalars; that is an important distinction.

**Question 6:** Can an object stored in a static shared field disappear completely via SRA?

If the reference can be observed later, the compiler must preserve object semantics; it cannot simply delete the object and pretend the assignment never happened.

**Question 7:** What synchronization can SRA/EA eliminate?

Lock elimination can apply to a private/non-escaping monitor if eligible; however, it must not remove synchronization between threads sharing an object.

**Question 8:** Why might deoptimization need to “materialize” an object?

An interpreter-compatible state may need to contain the logical object with the right fields/identity, whereas previously the optimized code only held scalar values.

**Question 9:** Is a `new int[3]` guaranteed to be eliminated?

No. Constant indexes/small arrays can help, but array indexing, aliasing, and compiler limits still matter.

**Question 10:** If JFR records no Point allocation events, can we assert SRA is active?

**No.** Event sampling/thresholds and GC timing can prevent us from seeing them; appropriate profiling/counters are needed.

**Question 11:** `javap -c` still shows `new`, so could HotSpot have eliminated the allocation?

**Possibly.** `javap` reads class-file bytecode, not C2's compiled machine code.

**Question 12:** What is the benefit of scalar replacement for GC?

If heap allocation is actually eliminated, the number of objects/bytes to manage on the heap decreases, which can reduce allocation/GC pressure.

## 32. Authoritative sources and further reading

- [Oracle Java SE 17 — Java HotSpot Virtual Machine Performance Enhancements, Escape Analysis](https://docs.oracle.com/en/java/javase/17/vm/java-hotspot-virtual-machine-performance-enhancements.html): escape states, scalar replacement, lock elimination, and the fact that HotSpot does not apply general stack allocation.
- [OpenJDK — Escape Analysis and Scalar Replacement Status](https://cr.openjdk.org/~cslucas/escape-analysis/EscapeAnalysis.html): flow-insensitivity, control-flow merges, loop-carried cases, inlining/interprocedural limitations.
- [OpenJDK JDK 17 update branch — C2 Escape Analysis](https://github.com/openjdk/jdk17u/blob/master/src/hotspot/share/opto/escape.cpp): implementation/connection graph; when researching, pin the commit and 17.0.x build.
- [OpenJDK JDK 17 update branch — MethodData](https://github.com/openjdk/jdk17u/blob/master/src/hotspot/share/oops/methodData.hpp): profiling structures serving dynamic compilation decisions; varies by JDK build.
- [Microsoft Java Engineering — Improving OpenJDK Scalar Replacement](https://devblogs.microsoft.com/java/improving-openjdk-scalar-replacement-part-1-3/): inlining, C2 EA/SRA, and areas for improvement.
- [Java SE 17 — `java` command reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): VM options, diagnostics, classpath, GC/heap settings.
- [Java SE 17 — `javap` tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): distinguishing `new` bytecode from optimized machine code execution.
- [Java SE 17 — `ThreadMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html) and [`com.sun.management.ThreadMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/ThreadMXBean.html): per-thread allocation counters on supported implementations.
- [Java SE 17 — JFR API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/module-summary.html): runtime/allocation diagnostics events.
- [JVMS Java SE 17 — Run-Time Data Areas](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.3): heap allocation semantics at the specification level.
- [JMH — OpenJDK Java Microbenchmark Harness](https://github.com/openjdk/jmh): benchmarking tool avoiding many warmup/DCE/loop optimization pitfalls.

**Conclusion:** **Escape analysis** analyzes whether objects can escape the compiled graph/thread scope; **scalar replacement** can replace temporary objects with **field values** and thereby eliminate actual allocations; **lock elimination** can remove useless monitors when proven safe. Effectiveness depends on **C2, inlining, aliasing, control flow, identity, exceptions, compiler budgets, and runtime build**. Do not interpret this as “every `new` becomes a stack object”; measure with **warmed-up benchmarks, bytes/op, JIT diagnostics, and the same JDK 17 configuration**.
