# Distinguishing allocation elimination from the assumption that objects are always moved onto the stack

When reading about **escape analysis (EA)** in the HotSpot JVM, we often encounter the explanation: “If an object does not escape the method, the JVM moves it from the heap onto the stack.” This statement **does not accurately describe HotSpot C2's optimization in Java 17**. Escape analysis is the process of **analyzing whether references to an object can escape a scope**. When an object is proven eligible, C2 can apply **scalar replacement**: replacing operations on the object with its component values, and even **eliminating the object allocation operation completely**.

In other words:

- **Allocation elimination:** an object allocation represented in source/bytecode may **no longer be performed** in the optimized machine code.
- **Scalar replacement:** the object's fields can be handled as scalars, compiler temporaries, or registers/stack slots as needed by the machine code. **An intact object does not necessarily exist on the stack.**
- **Stack allocation:** an object with structure/identity stored in a stack frame instead of the Java heap. This is **a different technique**; HotSpot's escape analysis documentation explicitly states that C2 does not simply perform stack allocation for an object just because it does not escape.
- **Normally**, if the object actually still has to be materialized/allocated, HotSpot still manages it on the **Java heap** via the appropriate allocation path, typically through Eden/TLAB. There is no contract that “every local object resides on the stack.”

This article belongs to the **HotSpot Optimizations** section, using the context of **HotSpot C2 on Java 17**. The content distinguishes concepts, optimization conditions, escape states, compiler limitations, deoptimization/materialization, GC impact, along with **compilable/runnable Java 17** examples and measurement methods without drawing conclusions from guesswork.

## 1. Four layers to distinguish: source, bytecode, machine code, and runtime allocation

```text
Java source:
    Pair p = new Pair(a, b);
    return p.left() + p.right();
                 │
                 ▼ javac
Class file bytecode:
    new Pair
    dup
    invokespecial Pair.<init>
    invokevirtual Pair.left ...
                 │
                 ▼ interpreter / C1 / C2
JIT optimized machine code (one possibility):
    result = a + b
    [no new Pair needed, no object header needed]
                 │
                 ▼ runtime
    There is not necessarily a heap object Pair corresponding to each call.
    It does not mean an intact Pair is placed on the native stack.
```

**Source `new` is not a guarantee of creating a measurable allocation on every execution** after the JIT has optimized it. It expresses semantics: create a new object with the appropriate value/identity **if identity is observed**. The compiler is free to perform an internal transformation as long as Java behavior remains correct.

**`javap -c` showing `new` also does not prove the runtime allocated an object**: `javap` prints bytecode, not the optimized machine code that C2 will use later.

### 1.1. A local variable is a reference, not the physical location of the object

```java
Object obj = new Object();
```

`obj` is a local variable holding a **reference** in terms of Java semantics. That does **not** prove the object was placed on the JVM stack. In the interpreter, local variables reside in the method invocation's **frame**; the reference may reside in the local variable array. In compiled code, the reference/value may be held in a register, a stack slot, or optimized away.

The **JVM stack frame** holds execution state such as locals and the operand stack according to the JVMS model; the **Java heap** is where most actual Java object allocations are managed. Avoid using “the local variable is on the stack” to infer backward that “the object the variable points to is also on the stack.”

### 1.2. The JVM stack and native stack are not the heap

Terminology:

| Concept | Function | What cannot be inferred |
| --- | --- | --- |
| Local variable/reference | Holds or represents a reference to an object | The target object definitely resides in the same frame |
| Operand stack per JVMS | Intermediate operation model of bytecode | Every operand remains intact like that in optimized machine code |
| Native thread stack | Execution memory of native/JIT frames and spilled registers | HotSpot C2 will turn every non-escaping object into a stack object |
| Java heap | Space managing Java object allocations | Every `new` keyword always creates a heap allocation after JIT |
| TLAB | Thread-local region for fast allocation from the heap | A “thread stack” for objects |
| Code Cache | Holds compiled native machine code | The Java heap holds business data objects |

The word **stack** is used interchangeably for multiple mechanisms, leading to a core misunderstanding: “a reference/scalar field resides in a stack slot” is completely different from “an intact object is stack-allocated.”

## 2. Escape analysis is a proof condition, not just looking at local variables

HotSpot C2 analyzes **reference paths within the scope of the compiled graph** to decide where else the object can still be observed. An object created inside a method can still **escape** through a return value, a static/shared field, JNI, or a call the compiler cannot prove; conversely, `return new Pair(...)` still has a chance to be optimized if the caller is inlined and the object is not published outside the graph.

In HotSpot documentation, the states are commonly called **NoEscape**, **ArgEscape**, and **GlobalEscape**. These are **internal compiler** classifications, not annotations or properties on a Java object. `NoEscape` only opens the **possibility** of scalar replacement, it does not guarantee C2 can eliminate the allocation; `ArgEscape` and `GlobalEscape` also require examining how the call graph/aliasing/side effects are actually analyzed.

**The specific focus of this article:** an object that *may not escape* still has no rule requiring it to **be allocated on the native stack**. To understand why, we must examine how C2 replaces the entire object with scalars and distinguish three outcomes: heap allocation, scalar replacement, and stack object allocation.

## 3. Scalar replacement: dropping the monolithic object representation

Consider an example in a class with `Pair(int left, int right)` and two fields `int left, right`:

~~~java
static int sum(int a, int b) {
    Pair p = new Pair(a, b);
    return p.left + p.right;
}
~~~

This is a **code snippet**; `Pair` must be defined before compiling. After inlining the constructor and sufficiently strong reference analysis, C2 **can** replace operations on the object with `left=a`, `right=b` and leave only `return a+b`. Then **no corresponding heap allocation is needed per call** in the optimized path, yet **no full `Pair` object is moved onto the stack either**.

Scalar values can be in registers, spilled stack slots, or further constant-folded; physical placement is not a Java API contract. One must distinguish **escape analysis (analysis condition)**, **scalar replacement (replacing the object with values)**, **allocation elimination (not allocating an actual object)**, and **dead-code elimination (removing parts that do not affect behavior)**. An allocation not appearing in a profile **does not by itself prove** which optimization caused it.

The practical conditions and limitations of EA were analyzed in depth in the previous article; the rest of this article focuses on answering why **allocation disappears ≠ stack allocation**.

## 4. Why should we not teach “NoEscape objects always go on the stack”?

Public research sources on **HotSpot Escape Analysis and Scalar Replacement Status** state: **HotSpot does not perform stack allocation** as a default result of C2 escape analysis. Oracle's documentation on HotSpot performance also describes that the compiler **eliminates scalar-replaceable allocations** and **does not replace heap allocation with a stack allocation** for non-global-escaping objects.

Comparison:

| Mechanism | Full object header? | Object still has materialized identity? | What can happen |
| --- | --- | --- | --- |
| Normal heap allocation | Yes in the heap object | Yes | `new` is executed via the VM allocation path |
| True stack allocation | May have an object representation in the stack frame in another VM | May exist in the frame | **Not the default description of HotSpot C2/Java 17** |
| Scalar replacement / allocation elimination | **Does not necessarily have an object header** | May not need to be materialized yet | Fields are replaced with scalars and the allocation is eliminated |
| TLAB fast allocation | **Has a real object on the heap** | Yes | Cheap allocation, but not an eliminated allocation |
| Escapes but field reads optimized | May still have a heap object | Yes | The compiler can still inline/copy-propagate some fields even if the object escapes |

A more accurate explanation:

> “If C2 proves an allocation does not escape and is eligible for scalar replacement, it **can eliminate that allocation**. This is not equivalent to **allocating the same object on the thread stack**.”

### 4.1. Does the Java specification require every physical object to reside on the heap?

The JVMS describes **the heap as the runtime data area from which memory for all class instances and arrays is allocated**, while allowing implementations to use unobservable optimizations as long as semantics are preserved. Developers should not claim “stack allocation for all objects” solely based on local variable rules. For current C2 within the scope of this article, the technique to focus on is **scalar replacement**, not stack object allocation.

The debate “is the object on the heap or the stack” needs to clarify **does the materialized runtime object actually exist?** If the compiler deletes the allocation and computes the result using constants/scalars, the question “is the object on the stack or the heap” can become a **question with a false premise**.

## 5. TLAB: heap allocation can be very fast without needing the stack

**TLAB (Thread-Local Allocation Buffer)** is HotSpot's mechanism to optimize the allocation path for **heap objects** by reserving a region of space belonging to Eden/young heap for a thread to perform fast allocations. When there is enough room in the TLAB, an allocation is usually close to a bump-pointer operation, avoiding shared locks.

```text
Java heap (e.g., Eden region):
  ├─ Thread A's TLAB ─► object1, object2, object3
  ├─ Thread B's TLAB ─► object4, object5
  └─ other regions / allocation slow paths

The TLABs above are still in the JAVA HEAP.
They are not on the thread's native call stack.
```

Therefore:

- “The object is created too fast, it must be on the stack” is wrong.
- An allocation still happening but cheaply thanks to TLAB is **different** from an allocation being completely eliminated.
- GC still has to manage objects created in a TLAB if they actually materialize on the heap.
- When the JIT eliminates an allocation, it reduces work for both the allocator and GC in a way different from TLAB optimization.

**Not every allocation goes through TLAB**, for example certain large objects/slow paths or special compiler/collector behavior; this does not make TLAB a separate GC generation.

## 6. When can an object escape?

### 6.1. Returning a reference from a method

```java
static Box makeBox(int value) {
    return new Box(value);
}
```

At the source method boundary, it returns `Box` to the caller. If the caller can retain it, compare identity, or pass the object elsewhere, the compiler usually needs a materialized object. However, **after inlining**, the JIT can see that the caller only reads a field and drops the reference; in a larger compiled region it can still eliminate the allocation.

Do not use “method returns object ⇒ absolutely cannot scalarize” as a program-wide law.

### 6.2. Storing into a static field

```java
private static volatile Object shared;

static void publish(Box box) {
    shared = box;
}
```

The object is published via a field accessible from other code and other threads. When the assignment actually occurs and the object can be observed, the compiler must preserve the Java memory model/object identity; it cannot simply delete the object and lose the observable reference.

`volatile` here makes the cross-thread publication model clearer; it is **not** the only cause of escape. An ordinary shared static field can also retain an object.

### 6.3. Putting an object into a long-lived container

```java
private static final java.util.List<Object> CACHE =
        new java.util.ArrayList<>();

static void remember(Object value) {
    CACHE.add(value);
}
```

An object stored in `CACHE` has a strong path from a static collection. It can outlive the lifetime of the method that created the object and cause retained heap memory. Even so, the JIT can still eliminate other temporary objects on the execution path if they do not escape.

### 6.4. Passing into another method

```java
static int readValue(Box b) {
    return b.value;
}

static int caller(int n) {
    Box b = new Box(n);
    return readValue(b);
}
```

Passing `b` as an argument **does not by itself prove global escape**. If C2 can inline `readValue`, sees the callee only reads a field, and the object graph is simple enough, the allocation can still be eliminated.

Conversely, if the callee is a native method, a reflective/dynamic call, or a method too large to be inlined, the compiler may not be able to prove the object does not escape and must materialize it.

### 6.5. Capturing a reference in a lambda/closure or handing it to a thread

If a closure/lambda/task holds a reference and is stored in an executor queue or another thread, the object can outlive the method that created it. Avoid inferring “the lambda is declared inside the method” so all captures reside on the method stack.

The compiler can optimize non-escaping lambdas in simple situations; however, capture graphs require analysis rather than concluding from source appearance.

## 7. Not escaping a thread is not enough to eliminate an allocation

An object held in a `ThreadLocal`:

```java
static final ThreadLocal<Box> LOCAL = new ThreadLocal<>();

static void store(int v) {
    LOCAL.set(new Box(v));
}
```

**Thread confinement** can help reason about data races/locking, but the object can still exist after `store()` finishes and be retrieved from `LOCAL.get()`. It **escapes the method** even though it is normally not used by another thread.

This is a classic example: “not touched by another thread” does **not** mean “once the method ends, the object no longer needs to exist.” The semantics of `ThreadLocal` require object identity/state to exist when it needs to be retrieved.

### 7.1. NoEscape, ArgEscape, and GlobalEscape are not public memory locations

Escape classifications describe what the compiler knows about references. They do **not** automatically map to:

```text
NoEscape       ⇒ stack
ArgEscape      ⇒ survivor
GlobalEscape   ⇒ old
```

All three arrows above are **wrong**. Eden/Survivor/Old are **GC generations**, whereas escape analysis is **compiler dataflow reasoning**. A GlobalEscape object can be allocated in Eden and then promoted; a NoEscape object can still materialize on the heap if the optimizer cannot or chooses not to perform scalar replacement.

## 8. Trade-offs and limitations of scalar replacement

An “intuitively non-escaping” object can still fail to have its allocation eliminated because:

- The compiler has not compiled the method with C2 yet, or the method is not “hot” enough.
- Call paths are not inlined, limiting the analysis scope.
- Complex object graphs, heavy aliasing, or control-flow merges that are hard to analyze.
- Large arrays, runtime-unknown index accesses at compile time, or element counts exceeding the JVM's scalarization limit.
- Escape analysis/compiler budgets/timeouts/heuristics limit the work.
- Identity-sensitive operations and APIs require a materialized object.
- JVMTI/debugging/instrumentation, safepoints, or deopt capability need appropriate state preserved.
- Native/reflective calls have semantics hard to prove from IR.
- Optimization is disabled via flags or the JVM does not use a compiler with similar support.

**Not every item above is an absolute blocker in every program.** Some field reads/aliases/calls can still be optimized through inlining, constant folding, and version-specific improvements.

### 8.1. Identity and `System.identityHashCode`

```java
Box a = new Box(7);
Box b = new Box(7);
boolean same = a == b;  // false for two independently observed allocations
```

If the compiler optimizes away materialization, it must still preserve `same == false` according to Java semantics. Not having an actual heap allocation **must not change the result of observable identity comparisons**.

Calling `System.identityHashCode(obj)`, using an object monitor, or passing an object to an API that might retain a reference can make materialization necessary or restrict scalar replacement. However, do not mechanically say “merely using `==` or `synchronized` forces every compiler to create a heap object” — some comparisons/locks can still be resolved or eliminated when proven safe.

### 8.2. Arrays and scalar replacement

`new int[2]` in a small computation can be an optimization candidate when size/indices are clear enough:

```java
static int sumTwo(int a, int b) {
    int[] values = {a, b};
    return values[0] + values[1];
}
```

However, `new int[100_000]` with dynamic accesses differs greatly in scalarization feasibility and compiler costs. Avoid concluding “local arrays are always on the stack” or “arrays never scalarize”; size, accesses, aliasing, and compiler version all matter.

### 8.3. Boxing, records, and value-like temporary objects

`Integer` boxing, small immutable records, and tiny holder objects are candidate examples for optimization when object identity does not need to be observed. However:

- Autoboxing can use a **cache**, so it does not necessarily create a new object even before EA.
- A Java 17 `record` is still a **reference class**, not a primitive value type in the way advanced value-type JVM projects have proposed.
- `record Pair(int x, int y)` can be a candidate for scalar replacement, **there is no contract that records are always unboxed**.
- Code size and polymorphism still limit JIT inlining capability.

Do not conflate scalar replacement with primitive specializations or Project Valhalla proposals from other versions/proposals.

## 9. Complete Java 17 program: creating local objects and escaping objects

Save the file **`EscapeAnalysisDemo.java`**:

```java
public class EscapeAnalysisDemo {
    record Pair(int left, int right) {}

    private static volatile Pair keepAlive;

    static long localSum(int n) {
        Pair pair = new Pair(n, n + 1);
        return (long) pair.left() + pair.right();
    }

    static Pair makePair(int n) {
        return new Pair(n, n + 1);
    }

    public static void main(String[] args) {
        long total = 0L;
        for (int i = 0; i < 100_000; i++) {
            total += localSum(i);
        }

        Pair retained = makePair(7);
        keepAlive = retained;

        Pair first = makePair(1);
        Pair second = makePair(1);

        System.out.println("sum=" + total);
        System.out.println("retainedValue=" +
                (retained.left() + retained.right()));
        System.out.println("distinctObjects=" + (first != second));
        System.out.println("sameRecordValue=" + first.equals(second));
    }
}
```

Compile/run (JDK 17+):

```bash
javac --release 17 EscapeAnalysisDemo.java
java EscapeAnalysisDemo
```

**Exact stdout when the program completes, without logging enabled:**

```text
sum=10000000000
retainedValue=15
distinctObjects=true
sameRecordValue=true
```

**Explanation:**

1. Each iteration calls `localSum(i)`, which semantically creates `Pair(i, i+1)` and then only adds the two fields. This is a good candidate for **scalar replacement / allocation elimination** when C2 optimizes this code region.
2. The sum of `2×i+1` for `i=0..99_999` is **100,000² = 10,000,000,000**, and is held in a `long` to avoid overflow.
3. `makePair(7)` returns a reference; `retained` is published into `static volatile keepAlive`, so the object can be observed by other code. One cannot assume this call has its allocation eliminated.
4. `first` and `second` are two separate allocations. `first != second` is **true**, whereas record `equals` compares field contents so it is `true`.
5. Java-level stdout is identical whether the compiler uses the interpreter, C1, or C2; **no line indicates whether the allocation in `localSum` was actually eliminated in this run**.

### 9.1. Different results between source and runtime

`javap` can still show:

```bash
javap -c -p EscapeAnalysisDemo
```

where the bytecode of `localSum` contains `new` to create the record object. At runtime, optimized C2 code **may** not perform that allocation.

Therefore **`javap -c` does not prove stack allocation, heap allocation, or runtime scalar replacement**. It is only a starting point when learning bytecode and what the JVM is permitted to optimize.

### 9.2. Comparing execution modes without fabricating GC stdout

```bash
# Normal: JVM profiles and tier-compiles automatically if appropriate
java EscapeAnalysisDemo

# HotSpot interpreter-oriented, without normal JIT compilation
java -Xint EscapeAnalysisDemo

# HotSpot JDK 17: disable escape analysis
java -XX:-DoEscapeAnalysis EscapeAnalysisDemo
```

**All three commands must produce the same four lines of Java-level stdout** upon successful execution. However, runtime allocations, warm-up cost, GC activity, and elapsed time may differ. `-Xint` can be significantly slower; do not use a single short run to claim a speedup factor.

## 10. Second program: escaping via field and via return

Create the file **`EscapePathsDemo.java`**:

```java
public class EscapePathsDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    private static volatile Box published;

    static int localOnly(int n) {
        Box b = new Box(n);
        b.value += 2;
        return b.value;
    }

    static Box returnsReference(int n) {
        return new Box(n);
    }

    static void publish(Box b) {
        published = b;
    }

    public static void main(String[] args) {
        System.out.println("local=" + localOnly(40));

        Box returned = returnsReference(5);
        System.out.println("returned=" + returned.value);

        Box first = new Box(9);
        publish(first);
        System.out.println("published=" + published.value);

        Box second = new Box(9);
        System.out.println("sameIdentity=" + (first == second));
    }
}
```

Compile/run:

```bash
javac --release 17 EscapePathsDemo.java
java EscapePathsDemo
```

**Exact stdout:**

```text
local=42
returned=5
published=9
sameIdentity=false
```

**What do we learn?**

- `localOnly` creates a `Box` used only for a primitive result; it has the potential to scalarize.
- `returnsReference` gives the caller a reference. If the JIT inlines it and sees the caller only reads the field, **there are still cases** where the compiler eliminates the allocation in a larger region.
- `published` is a shared field, which can be read by other threads; the target object needs to exist according to observable Java semantics.
- Two `new Box(9)` calls create two conceptually distinct objects. The JIT must not turn `sameIdentity=false` into true.
- This is an **example for analyzing escape paths**, not a tracer that determines physical allocation locations.

### 10.1. Is returning an object always GlobalEscape?

HotSpot documentation describes returning a reference as an example of **GlobalEscape** within the scope of the analyzed method. However, after method inlining, the compiler can know that the caller does not retain the reference outside the optimized region. Therefore, the interpretation in code review should be:

> “Returning a reference is an **escape edge at the method boundary**, making allocation elimination more complex; the compiler may still optimize it if it analyzes the caller as well.”

Do not turn that into “returning from any method creates a permanent heap object” or “if there is no explicit return, it cannot escape via a field.”

## 11. Third program: lock elimination does not mean a stack object

Another effect of EA is **lock elimination**: if the compiler can prove a lock on an object is unnecessary for synchronizing with other threads and removing the lock does not violate observable semantics, it can eliminate certain monitor enter/exit operations.

Create the file **`LocalLockDemo.java`**:

```java
public class LocalLockDemo {
    static int calculate(int n) {
        Object guard = new Object();
        synchronized (guard) {
            return n + 1;
        }
    }

    public static void main(String[] args) {
        long total = 0L;
        for (int i = 0; i < 100_000; i++) {
            total += calculate(i);
        }
        System.out.println("total=" + total);
    }
}
```

Compile/run:

```bash
javac --release 17 LocalLockDemo.java
java LocalLockDemo
```

**Exact stdout:**

```text
total=5000050000
```

`guard` is created for internal use inside `calculate`; since the code does not publish it outside, the compiler **can** prove the monitor operations are unnecessary and remove the lock, and even eliminate the allocation. However:

- `synchronized` Java semantics do not disappear: if there is an exception or monitor-observable behavior, the compiler must preserve valid behavior.
- Do not claim every local lock in every JVM is elided.
- This is **not** proof that `guard` was stack-allocated.
- If `guard` is replaced with a shared lock field, removing mutual exclusion may be invalid because other threads need synchronization.

**Note:** “lock elimination” is different from the programmer deleting the `synchronized` keyword. In source code, keep necessary synchronization; the JVM only removes it mechanically when proven valid.

## 12. Deoptimization: scalarized objects may need materialization

A major challenge of scalar replacement is that **the JIT may need to deoptimize** and fall back to the interpreter when a speculative assumption no longer holds.

Suppose:

```text
Java-level:
  Pair p = new Pair(3, 4);
  doSomething();
  use(p.left, p.right);

Optimized machine state:
  scalar_left = 3
  scalar_right = 4
  [no physical Pair heap allocation]

Suddenly, deoptimization occurs at a point needing to resume in the interpreter:
  JVM uses scope/debug info and virtual-object metadata
  to reconstruct Java-level frames, locals, operand stack,
  and materialize the Pair object if identity/reference is actually needed.

After materialization if needed:
  a Pair heap object may exist so Java code continues correctly.
```

That does **not** mean:

- The compiler must keep a “Pair object on the stack” ready throughout optimized execution.
- Deopt always creates an object for every scalarized allocation, regardless of whether Java state needs to observe it.
- Deopt re-runs the entire method from the beginning and repeats side effects.
- Because an allocation appears after deopt, all previous calls must have allocated the object.

More accurately: **the runtime has enough metadata to restore an equivalent Java state**, including virtual objects/frames when needed. Deoptimization/materialization is an essential part that allows **allocation elimination and speculative JIT optimization to still preserve correctness**.

### 12.1. Why doesn't a stack snapshot show an object on the stack?

An optimized stack frame can contain scalar fields, references, spills, or metadata used for reconstruction. A tool seeing a few int values in a native stack frame **does not prove** an intact `Pair` resides there.

To analyze this for real, one must examine compiler IR/machine code/VM metadata on an appropriate build; a Java stack trace mainly describes call scopes, not physical object allocation.

### 12.2. Materialization can change allocation metrics

During most of execution, eliminated allocations reduce pressure on GC. However, if a program frequently deopts/reconstructs objects, some allocations may appear at points different from what one would intuit from source. Therefore, do not take a single-moment GC allocation histogram and claim objects “are always placed on the stack.”

**GC logs do not report a field “stack allocations eliminated by EA”**. When seeing reduced GC activity, the cause could be EA, dead-code elimination, allocation batching, TLAB sizing, or workload changes; controlled experiments are required.

## 13. What happens when an object's allocation is not eliminated?

Suppose an application creates 100,000 `Box` instances and holds all of them in a collection:

```java
java.util.List<Box> boxes = new java.util.ArrayList<>();

for (int i = 0; i < 100_000; i++) {
    boxes.add(new Box(i));
}
```

This is a **snippet**, not a standalone file; it uses the `Box` class from the previous example.

If the list remains reachable and other code can access the Boxes, the runtime needs to keep the actual object graph. On HotSpot with generational GC, physical allocations typically reside in the young/Eden heap via the appropriate path, and can be promoted if they live long enough.

The compiler can still optimize constructor field stores, remove redundant bounds checks, or inline methods; **not eliminating an allocation does not mean there are no optimizations at all**.

### 13.1. Heap allocation is not necessarily expensive

With TLAB and generational GC, creating small objects that die young usually has very low cost on HotSpot. Therefore, the advice “never use `new` in a hot method” is overly extreme.

What matters are **allocation rate, survival/retention, cache locality, and GC pause/CPU metrics**. Turning every object into a mutable reusable buffer can create aliasing bugs, leaked stale data, and lock contention; sometimes simple, easy-to-optimize immutable code is even faster.

### 13.2. Compiler optimization is possible without making code hard to read

A small, immutable holder object used to represent a pair of values in helper methods can make code clearer than passing multiple primitives. If performance profiling does not show an issue, prioritize correctness/maintainability first. The JIT may scalarize some temporary holders, but that is an **opportunity**, not an API contract.

## 14. HotSpot Java 17 flags for experimentation

### 14.1. Disabling escape analysis for comparison

The Oracle JDK 17 `java` manual explicitly states:

```bash
-XX:+DoEscapeAnalysis       # Enable EA, default on applicable HotSpot builds
-XX:-DoEscapeAnalysis       # Disable EA
```

Run:

```bash
java EscapeAnalysisDemo
java -XX:-DoEscapeAnalysis EscapeAnalysisDemo
```

The business output of the two runs is **identical**. With other configurations or short runs, you may not see a significant memory difference; **there is no evidence from stdout determining how many objects EA eliminated**.

### 14.2. `EliminateAllocations` on HotSpot C2

In the source of **OpenJDK JDK 17 C2**, there is a VM option:

```bash
-XX:+EliminateAllocations
-XX:-EliminateAllocations
```

This option controls C2's EA-based allocation elimination branch. When using a supported HotSpot build, try:

```bash
java -XX:-EliminateAllocations EscapeAnalysisDemo
```

However, **do not infer that disabling the option guarantees every source `new` will create a heap allocation**: there are other optimizations such as dead-code elimination, constant folding, intrinsics, boxing caches, and compiler policy. Also do not treat this option as a portable Java SE API.

**Note:** If the JVM/vendor responds with `Unrecognized VM option`, stop the experiment and check the version/`PrintFlagsFinal`; do not force HotSpot internal options onto other JVMs.

### 14.3. Disabling JIT to cross-check semantics

```bash
java -Xint EscapeAnalysisDemo
```

`-Xint` on HotSpot runs bytecode primarily in interpreter mode, so C2 scalar replacement optimizations are not in the same code path; yet Java semantics/output remain correct. Performance can drop drastically; do not use it to run production throughput benchmarks.

`-XX:-TieredCompilation` **does not mean disabling JIT**. It changes the tiering policy, and another compiler can still optimize.

### 14.4. Checking available flags instead of memorizing names from old tutorials

```bash
java -XX:+PrintFlagsFinal -version
```

You can combine shell/platform filtering to inspect `DoEscapeAnalysis`, `EliminateAllocations`, `EliminateLocks`, and related flags.

Be careful with `PrintEscapeAnalysis` or `PrintEliminateAllocations`: on many HotSpot **product/release builds**, these are options only available in **non-product/debug VMs**. Do not present a `-XX:+PrintEscapeAnalysis` command as if it must work on every OpenJDK 17 production build.

## 15. Measuring allocation elimination properly

A Java program running faster when toggling EA does not by itself prove the entire difference comes from a specific allocation site. There may also be JIT warm-up, inlining, tiering, code cache, GC policy, and CPU scheduling.

**Minimum procedure:**

1. **Fix JDK vendor/version**: record the exact `java -version`, architecture, and server/client VM.
2. **Keep workload representative**: inputs, object lifespans, and method polymorphism similar to production.
3. **Warm up properly**: let the JIT profile/compile before taking steady-state metrics.
4. **Compare three configurations**: baseline, `-XX:-DoEscapeAnalysis`, and (if supported by the build) `-XX:-EliminateAllocations`.
5. **Compare against `-Xint` for semantics**, but do not use interpreter performance to infer C2 allocation cost.
6. **Use JFR/allocator counters/profiler** to compare allocations, GC pauses, heap allocation rates, and hotspots with identical settings.
7. **Use multiple forks/repetitions**, do not trust a single 100 ms run.
8. **Avoid dead benchmarks**: do not let the compiler delete the entire computation just because the result is unused.
9. **Measure CPU and throughput alongside allocations**: reducing allocations does not automatically improve end-to-end p99 or total CPU.
10. **Do not claim physical stack location** without corresponding machine-code/runtime-level evidence.

### 15.1. Why doesn't `new` in a loop mean 1 million allocations?

```java
static long sum(int limit) {
    long result = 0;
    for (int i = 0; i < limit; i++) {
        Pair pair = new Pair(i, i + 1);
        result += (long) pair.left + pair.right;
    }
    return result;
}
```

This is a **snippet**, requiring a `Pair` class with `left/right` fields. If C2 inlines/optimizes, sometimes the object is no longer materialized. With the interpreter or if optimization does not apply, allocations may still be performed.

Counting the `new` keyword or loop iterations only counts **source-level allocation expressions**, not actual heap allocations. Conversely, if JFR shows fewer allocation events, understand that JFR may use sampling/throttling depending on events/settings rather than being exact per-object tracing.

### 15.2. JFR for method-level measurement

Launch:

```bash
java -XX:StartFlightRecording=filename=ea-test.jfr,settings=profile \
     EscapeAnalysisDemo
```

A very short recording may have few events or insufficient warm-up. Java Flight Recorder has many event types/thresholds/sampling settings. In JDK 17, monitor allocation/GC/compilation events with an appropriate configuration, then inspect in JDK Mission Control or JFR tooling.

JFR **is not an oracle confirming C2 stack-allocated an object**. When allocation rate drops, what may be true is that allocations were eliminated; stack allocation would still require separate implementation evidence, not inference solely from the number of alloc events.

### 15.3. GC logs can help, but cannot isolate EA alone

```bash
java -Xms256m -Xmx256m \
     -Xlog:gc*:file=gc-ea.log:uptime,level,tags \
     EscapeAnalysisDemo
```

In a real workload, one can compare allocation rate and GC frequency with EA on/off. However:

- GC logs usually only show **collector events**, not a list of every `new`.
- A small program might not trigger any GC during a test run.
- Fewer GC events do not prove exactly which allocation was eliminated.
- Committed heap/RSS does not necessarily drop immediately even if allocations decrease.
- A profiler/JIT compiler analysis is needed when you want to pinpoint a specific allocation site.

## 16. Microbenchmarking: avoid “measuring” the compiler eliminating all the work

**Counterexample:**

```java
long start = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    new Pair(i, i + 1);
}
long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
```

This is an **anti-pattern snippet**, not a standalone class. If creating `Pair` has no observable effects, the JIT can delete all the work; the measured result may reflect an empty loop or less work than expected. One cannot conclude “stack allocation is ultra-fast” from such a benchmark.

**Better approach:**

- Use the actual computed result (or an appropriate JMH Blackhole).
- Fix inputs while preventing the compiler from knowing/optimizing everything away in an unrepresentative manner.
- Warm up, use multiple iterations/forks, and measure memory allocations with a properly configured profiler.
- Separate **scalarization candidate** benchmarks from **object graph escape** benchmarks.
- Run JDK 17 with identical flags, heap size, and workload across control runs.
- If you want to inspect compiler IR, use appropriate tooling/diagnostic builds; do not apply “seeing less GC with the naked eye means objects are on the stack.”

### 16.1. JMH does not replace a profiler

**JMH (Java Microbenchmark Harness)** helps reduce many benchmarking mistakes regarding JIT compilation, warm-up, and dead-code elimination, but it does **not** by itself pinpoint the internal cause of every performance delta. When measuring allocation rate, you can use the JMH GC profiler/appropriate JVM diagnostic tooling and examine results in bytes/op; verify JVM/GC/JIT settings.

**Low bytes/op** does not by itself prove “objects are on the stack.” It can come from scalar replacement, allocation elimination, or complete elimination of work.

## 17. Common misconceptions when reading about memory

| False claim | Why it is wrong | More accurate phrasing |
| --- | --- | --- |
| “Local variable is on the stack → object is also on the stack.” | The variable may be a reference; the object has a different lifetime. | The JVM stack holds frames/values; materialized objects are usually on the Java heap. |
| “Non-escaping objects are always stack-allocated.” | HotSpot C2 uses scalar replacement, not default stack allocation. | A non-escaping object can **have its allocation eliminated** if eligible. |
| “Every `new` causes a GC heap object.” | The JIT can optimize the allocation away. | Distinguish bytecode allocation expressions from runtime allocations. |
| “Seeing no GC events means objects are on the stack.” | Could be due to sufficient heap space, TLAB, few allocations, or GC not having run yet. | Measure allocations/profiler and compiler behavior. |
| “TLAB is a thread stack.” | TLAB is a heap allocation buffer. | It is still heap allocation, just a fast path. |
| “Scalar replacement moves field values to the heap.” | Scalar values can be in registers, stacks, or optimized away. | The object does not need to exist monolithically if semantics allow. |
| “An object returned from a helper cannot be eliminated.” | The caller may inline the helper. | Escape must be evaluated on the compiled scope/graph. |
| “If there is no cross-thread sharing, it must be NoEscape.” | The object can outlive the method via ThreadLocal. | Thread confinement differs from method escape. |
| “EA always eliminates every lock on a local object.” | The compiler must prove correctness. | Lock elimination is conditional, not free removal of synchronization. |
| “Records are always unboxed into primitives.” | A Java 17 record is still a reference class. | It can be a candidate for scalar replacement. |
| “A heap dump not showing `Pair` means it is on the stack.” | The object may be dead/GC'd/eliminated/not yet materialized. | Runtime conditions and the compiler must be analyzed. |
| “`javap` having `new` proves the JIT allocated.” | Bytecode differs from optimized machine code. | `javap` shows source-level VM instructions. |
| “Disabling EA will break program logic.” | Optimizations must not change Java semantics. | It may change performance/allocations, not valid results. |
| “Changing a JVM flag once is enough proof.” | JIT/GC/timing vary. | Test multiple forks and a representative workload. |
| “A scalarized object cannot appear during deopt.” | HotSpot has metadata/materialization. | The runtime reconstructs Java state when needed. |
| “C2 always compiles a method immediately after 10,000 calls.” | Tiering/hotness/heuristics depend on workload/build. | Verify actual compiler activity. |

## 18. Exercises with answers

**Question 1.** In `Point p = new Point(1,2)` as a method local, can we be certain the object resides on the stack?

**Answer:** **No.** `p` is a reference; the runtime object may be allocated on the heap, or C2 may eliminate the allocation via scalar replacement; that is not equivalent to stack allocation.

**Question 2.** If C2 eliminates the entire allocation, is there still an object header for `Point` on the stack?

**Answer:** There is no reason an intact object header must exist. The compiler can just keep scalars/computed values, or even delete redundant computations altogether.

**Question 3.** An object is created and its reference is returned to the caller. Is it certain that the allocation can never be eliminated?

**Answer:** No. The caller can be inlined and the reference no longer escapes the compiled region. The actual optimized graph must be analyzed.

**Question 4.** An object is stored in `static volatile Object shared` and used from another thread. Can it simply be turned into two int locals of the caller?

**Answer:** Not in a way that breaks observable shared-reference semantics. The object may need to be materialized and maintain identity/visibility.

**Question 5.** If a benchmark does not use the result of `new Box(...)`, does an ultra-short time prove stack allocation is effective?

**Answer:** No. The compiler can dead-code-eliminate the entire object creation and unobservable computations.

**Question 6.** Is TLAB stack or heap?

**Answer:** TLAB is **a heap region**, for a thread to allocate quickly. Objects in a TLAB are still heap objects.

**Question 7.** Does `-XX:-DoEscapeAnalysis` mean the JVM skips all possible optimizations?

**Answer:** No. It disables EA per the HotSpot option, but constant folding, DCE, inlining, and other optimizations can still occur.

**Question 8.** Can we take the number of objects in a heap dump at the end of the process to calculate exactly how many `new` operations ran?

**Answer:** No. A heap dump only contains objects still alive at the snapshot; GC'd objects and eliminated allocations are not present.

**Question 9.** Does scalar replacement force all fields into CPU registers?

**Answer:** No. Scalars can be register-allocated, spilled to stack slots, constant-folded, or optimized away.

**Question 10.** Why can the JVM materialize an object when deoptimization occurs?

**Answer:** Because the Java execution state after fallback may need object identity/reference; the JIT stores metadata to reconstruct the correct state.

**Question 11.** Do `new int[2]` and `new int[100_000]` have the same scalar replacement capability?

**Answer:** No. Small arrays with clear sizes/indices can be easier to optimize; large arrays/dynamic indices are harder and have compiler limits.

**Question 12.** Why is “the object does not escape the thread” not enough to say the object can be deleted?

**Answer:** It can still outlive the method via `ThreadLocal` or a thread-private structure. Method lifetime and thread visibility are two different criteria.

**Question 13.** What value does `EscapeAnalysisDemo` print for `sum`, and why?

**Answer:** **10,000,000,000**, because the sum of odd numbers `1,3,...,199999` equals `100000²`.

**Question 14.** Does the `distinctObjects=true` result change when the JIT enables scalar replacement?

**Answer:** No. The JVM must preserve the semantics of two distinct allocations when identity is observed in a comparison.

**Question 15.** If `System.identityHashCode` is present in a method, does the JIT always forbid all forms of allocation elimination in the entire method?

**Answer:** Not necessarily across the entire method; it can impose constraints on the relevant object/site, while other allocations can still be optimized. Actual compiler behavior must be observed.

**Question 16.** When code uses `synchronized` on a non-escaping local object, is lock elimination safe?

**Answer:** It can be, if the compiler proves it does not break semantics/observable synchronization; this must not be understood as meaning every `synchronized` is unnecessary.

**Question 17.** If running `-Xint` and baseline produces different stdout across the three demos, what should you do?

**Answer:** Check the code/data races/undefined assumptions and environment, because valid Java logic must preserve Java-level results; differences in performance/GC events are normal.

**Question 18.** What should be written in technical documentation instead of “HotSpot moves local objects onto the stack”?

**Answer:** “HotSpot C2 can **eliminate the allocation** of an object when escape analysis and scalar replacement prove it eligible; if the allocation still needs to be performed, the object is typically allocated on the heap.”

## 19. Summary

```text
Source:
    new Pair(a, b)
          │
          ▼
  JIT's Escape Analysis
    │
    ├─ Escapes or cannot prove NoEscape
    │       │
    │       ▼
    │    Materialized object may have to reside on Java heap
    │       ├─ TLAB/Eden fast allocation
    │       └─ other allocation path per GC/VM
    │
    └─ NoEscape + scalar replaceable + compiler chooses optimization
            │
            ▼
      Scalar replacement
        field.left  → scalar a
        field.right → scalar b
            │
            ▼
      Allocation elimination
      (object may not exist monolithically)
            │
            ▼
      Deoptimization when needed:
      reconstruct state / materialize object as appropriate

NO NECESSARY CONSEQUENCE:
  "NoEscape ⇒ place the intact Java object on the native stack".
```

**Key takeaway:** **Escape analysis** provides information about paths along which an object reference can leave a scope. On **HotSpot C2/Java 17**, the key optimization is **scalar replacement combined with allocation elimination**, which can make it unnecessary to allocate the object as an intact unit. **Stack allocation** is a different mechanism and is not the default outcome of EA in HotSpot. If an object actually has to exist and be accessed through observable references, the VM uses heap allocation per policy; **TLAB still belongs to the heap**. Measure with benchmarks/profilers and compare EA on–off; do not infer physical memory placement from the `new` keyword, local variable scope, or the silence of GC logs.

### References and cross-check sources

- [HotSpot Escape Analysis and Scalar Replacement Status](https://cr.openjdk.org/~cslucas/escape-analysis/EscapeAnalysis.html): describes EA, scalar replacement, and explicitly states that HotSpot does not perform stack allocation in the sense being debated.
- [Oracle Java HotSpot VM Performance Enhancements — Escape Analysis](https://docs.oracle.com/javase/8/docs/technotes/guides/vm/performance-enhancements-7.html): NoEscape/ArgEscape/GlobalEscape groups, scalar replacement, lock elimination, and not replacing heap allocation with stack allocation.
- [Oracle Java SE 17 — `java` launcher documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `DoEscapeAnalysis`, `PrintFlagsFinal`, `-Xint`, `-Xlog`, and JFR.
- [OpenJDK JDK 17 C2 VM options](https://github.com/openjdk/jdk17u/blob/master/src/hotspot/share/opto/c2_globals.hpp): `EliminateAllocations`, `EliminateLocks`, `DoEscapeAnalysis`, and debug-only printing flags.
- [OpenJDK JDK 17 `escape.cpp`](https://github.com/openjdk/jdk17u/blob/master/src/hotspot/share/opto/escape.cpp): connection graph, NoEscape, and scalar-replaceable allocation paths.
- [JVMS Java SE 17 §2.5 — Runtime Data Areas](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5): JVM stacks, frames, and heap model.
- [Java SE 17 Javadoc — `java.lang.Record`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): records are reference classes in Java 17.
- [Microsoft for Java Developers — Improving OpenJDK Scalar Replacement](https://devblogs.microsoft.com/java/improving-openjdk-scalar-replacement-part-2-3/): examples of limitations and complex conditions of scalar replacement.
