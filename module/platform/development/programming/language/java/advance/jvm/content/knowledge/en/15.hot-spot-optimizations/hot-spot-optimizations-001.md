# Method Inlining and Analysis Scope Expansion in HotSpot

## 1. What Problem Does Inlining Solve?

Java encourages splitting programs into many small methods so that code is clear, reusable, and easy to test:

~~~java
static int twice(int value) {
    return value * 2;
}

static int plusOne(int value) {
    return value + 1;
}

static int pipeline(int value) {
    return plusOne(twice(value));
}
~~~

The three methods above are **illustrative snippets that need to reside in a class**. At the source level, `pipeline` calls two methods. At the bytecode level, `javac` usually still emits `invokestatic` instructions. However, when the HotSpot JIT compiles a hot caller, it can **insert the callee's logic into the caller's intermediate representation (IR)** right at the call site: that is **method inlining**.

One way to visualize it:

~~~text
Before inlining (model):
  pipeline(x)
      |
      +--> twice(x)     : 2*x
      |
      +--> plusOne(...) : +1

After JIT inlines into pipeline's IR (model):
  result = 2*x + 1
~~~

**Inlining does not modify the Java source and does not necessarily modify the `.class` file on disk.** It is a compiler decision at runtime when generating **native compiled code**. The original bytecode may still contain method calls.

**Two main benefits:**

1. **Reduces call overhead:** fewer call/return steps, argument setup, and control-transfer paths when the compiler actually eliminates the call.
2. **Expands analysis scope:** the compiler sees code on **both sides of the method boundary** in the same IR, so it can perform constant propagation, dead-code elimination, value/range analysis, escape analysis, scalar replacement, devirtualization, and other optimizations across method boundaries.

**The second benefit is often more important than "saving a call instruction."** In many programs, a small method has only a few bytecodes; inserting it into the caller can unlock optimizations far stronger than the initial invocation cost.

### An Upfront Caveat

HotSpot **does not guarantee inlining every method**, including `private`, `static`, `final`, or single-line methods. The decision depends on the compiler tier, bytecode size, call-site frequency, recursion, call depth, profile types, compilation graph budget, and other constraints.

## 2. Layers to Distinguish: Source, Bytecode, IR, Machine Code

| Layer | What it represents | Changed when JIT inlines? |
| --- | --- | --- |
| **Java source** | `pipeline` calls `twice` and `plusOne` | No; source remains unchanged |
| **Class-file bytecode** | `invokestatic`, `invokevirtual`, `invokeinterface`… | Not necessarily; `javap -c` still sees calls |
| **Compiler IR / call graph** | Nodes for calls, operations, types, control flow | **Possibly**: callee body is expanded into the caller graph |
| **Compiled native code** | Optimized CPU instructions | May no longer have a separate call at that site |
| **Runtime semantics** | Results, exceptions, synchronization, type safety | **Must be preserved** |

Do not use `javap -c` output to conclude "the JIT has not inlined": `javap` reads the class file, not the disassembled native nmethods of the currently running JVM. To inspect HotSpot's decisions, you need **`-XX:+PrintInlining`** or appropriate compiler/JIT tools.

### "Inserting the Method Body" Is Not Copying Java Text

The JIT does not simply copy the source snippet between two braces. It analyzes **bytecode/IR and the context at the call site**, builds the equivalent IR, maps arguments/receiver and locals, connects control-flow edges, return values, exceptions, and related effects.

For example, inlining two methods can mean:

~~~text
IR caller:
    parameter x
    call twice(x)
    call plusOne(result)

Inline twice:
    v1 = x * 2

Inline plusOne:
    v2 = v1 + 1

Further optimization:
    v2 = x * 2 + 1
~~~

This is a **hypothetical IR diagram**, not an exact dump from C2 or node names in OpenJDK. The real compiler also manages safepoints, GC maps, debug state, memory effects, alias information, and speculative guards.

## 3. The Call Site Matters More Than the Method Name

Inlining is usually **a decision at a specific call site in a compilation**.

For example:

~~~java
static int helper(int value) {
    return value * 5;
}

static int hotCaller(int x) {
    return helper(x) + 1;
}

static int coldCaller(int x) {
    return helper(x) - 1;
}
~~~

These are illustrative methods. The JIT may inline `helper` in **`hotCaller`** because the profile shows the call site is very hot, yet not inline it in **`coldCaller`** because the method is cold, the budget differs, or it has not been compiled yet. It may also choose to compile both or compile neither.

**Do not say "method `helper` has been marked inline across the entire JVM."** The same callee can be inlined into multiple callers, some call sites may still keep the call, and subsequent recompilations may make different decisions. `PrintInlining` logs are tied to the caller's compilation and a specific inlining tree chain.

### Inlining and Dynamic Dispatch

An `invokestatic` call has a clear target according to bytecode/linking; `invokevirtual` and `invokeinterface` usually require runtime method selection based on the receiver type. Still, the compiler can inline virtual calls when there is sufficient evidence for correctness, for example:

- The declared target is effectively a suitable single implementation.
- The call site's type profile predominantly sees one concrete class.
- Class hierarchy analysis (CHA) indicates at compilation time that one call target is viable.
- The compiler adds a **type guard** or dependency to handle cases when the assumption no longer holds.

**Java interfaces do not inherently prevent inlining.** And **`final` does not forcibly guarantee inlining**: knowing the target only removes one obstacle, while budgets/size/profitability still have to be evaluated.

## 4. Expanding Analysis Scope: The Core Point

An optimizer that only sees the caller may have to be conservative about the callee's behavior: the method might read/write fields, throw an exception, escape a reference, call another method, or have side effects.

If inlining brings the callee body into the same IR, the compiler can analyze operations **chained across multiple methods**, exposing relationships that were previously hidden by the call boundary.

### 4.1. Constant Propagation Across Methods

~~~java
static int square(int x) {
    return x * x;
}

static int compute() {
    return square(7) + 3;
}
~~~

Illustrative methods snippet.

~~~text
Before expansion:
  call square(7) -> result unknown in caller IR

After inline (model):
  (7 * 7) + 3

Constant folding can produce:
  52
~~~

**`compute()` returns 52** according to Java semantics. Inlining lets the compiler see that the argument is a constant directly inside `square`'s body. The compiler can sometimes deduce the result using other techniques without inlining, so one should not state "only inlining can constant-fold."

### 4.2. Dead-Code Elimination and Branch Simplification

~~~java
static int choose(boolean enabled, int value) {
    return enabled ? value * 2 : value * 3;
}

static int fastPath(int input) {
    return choose(true, input);
}
~~~

If `choose(true, input)` is inlined, the `enabled` condition is known, and the compiler can keep only the `input * 2` branch instead of keeping both branches. This reduces code/runtime work and opens optimizations for subsequent operations.

**Do not assume** that a branch with side effects can be eliminated if the condition can still select that branch at runtime. The optimizer must prove the eliminated path cannot execute in the compiled context.

### 4.3. Range Check Elimination

~~~java
static int readFirst(int[] numbers) {
    return numbers[0];
}

static int readKnownLength() {
    int[] data = new int[] {4, 8, 12};
    return readFirst(data);
}
~~~

In this context, after inlining `readFirst`, the compiler can see that the array length and index 0 are known, allowing it to eliminate **unnecessary bounds checks** if proven safe. Null checks are also only omitted when there is evidence the object is non-null or protected by a valid guard.

**There is no guarantee** the JIT always eliminates both the allocation and all checks in the example; compiler tier, profile, deoptimization requirements, and implementation conditions decide.

### 4.4. Loop Optimization

Suppose a loop calls a small helper on every iteration. Inlining the helper can let the optimizer see arithmetic/field reads within the same loop body to perform:

- hoisting an invariant computation outside the loop;
- common-subexpression elimination;
- strength reduction;
- loop unrolling or vectorization **if valid and supported**.

Inlining **is not a sufficient condition** for a loop to be automatically vectorized. Memory aliasing, data dependencies, exceptions, and architecture constraints can still prevent optimization.

## 5. Escape Analysis and Scalar Replacement Across Call Boundaries

This is a prominent example of why inlining matters.

~~~java
static final class Pair {
    final int left;
    final int right;

    Pair(int left, int right) {
        this.left = left;
        this.right = right;
    }
}

static int score(Pair pair) {
    return pair.left * 2 + pair.right;
}

static int makeScore(int base) {
    Pair pair = new Pair(base, base + 1);
    return score(pair);
}
~~~

This snippet illustrates declarations within the same class.

If the compiler inspects `makeScore` without understanding the effects of `score`, it may have to assume `pair` is used in a way that requires the object to exist. After inlining `score` (and related parts), the compiler sees `Pair` only has its fields read within a known scope; **escape analysis** can determine that the object does not need to be materialized on the heap.

~~~text
Before inline (model):
  p = new Pair(base, base+1)
  result = call score(p)
  return result

After inline:
  p = new Pair(base, base+1)
  result = p.left*2 + p.right
  return result

After scalar replacement if eligible:
  left = base
  right = base+1
  return left*2 + right

Further simplify:
  return base*3 + 1
~~~

On HotSpot C2, **scalar replacement** can eliminate the heap allocation and field loads/stores; it is not "moving every non-escaping object onto the JVM stack." The Oracle HotSpot Performance Enhancements documentation clearly explains the approach of eliminating allocations and associated locks under appropriate conditions.

**There is no guarantee** the small program above will definitely be JIT compiled or scalar-replaced on the first run. While the `new Pair` bytecode is still present in `javap`, the JIT can eliminate the allocation **in runtime compiled machine code**; conversely, if the object genuinely escapes, the VM must preserve the required identity/visibility.

### Propagating Benefits Across Multiple Methods

~~~text
Caller -> createPair() -> scorePair() -> normalize()

If the small calls are all inlined:
  The compiler can see the graph of object creation -> field reads -> final computation.

Potential results:
  constant propagation
  scalar replacement
  dead-store elimination
  elimination of redundant null/bounds checks
  register-based execution
~~~

Therefore, inlining **expands the boundary of interprocedural analysis** within a compilation. Precisely because it expands the IR, it has a **cost**, forcing the compiler to use heuristics rather than inlining indefinitely.

## 6. Speculative Inlining Mechanism for Virtual/Interface Calls

Consider a call site using an interface:

~~~java
interface Operation {
    int apply(int x);
}

static final class AddOne implements Operation {
    @Override public int apply(int x) { return x + 1; }
}

static final class MultiplyTwo implements Operation {
    @Override public int apply(int x) { return x * 2; }
}

static int execute(Operation operation, int value) {
    return operation.apply(value);
}
~~~

The declarations above are **illustrative**, not a standalone Java file.

At runtime, the call site of `operation.apply` can be:

- **Monomorphic**: almost exclusively sees one receiver type, such as `AddOne`.
- **Bimorphic/polymorphic**: sees more than one receiver type with varying frequencies.
- **Megamorphic**: sees so many receiver types that inlining a specific target may not be beneficial.

The HotSpot JIT can use **profile-based type guards** to inline the common target:

~~~text
if (receiver matches AddOne):        // actual check depends on the compiler
    result = value + 1                // AddOne.apply inlined
else:
    result = genericVirtualDispatch(receiver, value)
~~~

This is a conceptual **guarded inlining** diagram. The VM may use deoptimization instead of a generic fallback or multiple different guarded targets, as long as it preserves Java dynamic-dispatch semantics.

### What If a New Class Appears Later?

Suppose the program previously ran only with `AddOne`, then class `MultiplyTwo` is loaded and a new object is passed to the call site. The JVM **must not** return `x+1` for a `MultiplyTwo` receiver just because `AddOne` was inlined. It must:

- let the guard fail and take the correct call path;
- or **deoptimize** the compiled code when assumptions no longer hold;
- or apply an equivalent invalidation/recompilation/virtual dispatch mechanism.

**Deoptimization is not a Java business-logic error**. It is part of adaptive optimization that keeps compiled code correct even when a previous profile ceases to be representative.

### Class Hierarchy Analysis (CHA)

CHA allows the optimizer to use currently loaded/known class hierarchy information to recognize that a call site has a unique target. However, with dynamic class loading, the assumption can become invalid when a new subclass/implementation appears; HotSpot has appropriate dependency tracking and deoptimization.

One must not conclude that `invokevirtual` is always too expensive to inline or that every interface call must always generate a native indirect call.

## 7. Both C1 and C2 Can Inline, But With Different Budgets/Policies

HotSpot supports **tiered compilation** in common configurations:

| Execution tier | Role | Inlining |
| --- | --- | --- |
| Interpreter (level 0) | Executes bytecode, accumulates profiling | Does not produce JIT native code/inlining in the compiler sense |
| C1 (common levels 1–3) | Compiles faster, with profiling levels | Has inlining with its own constraints/heuristics |
| C2 (common level 4) | Optimizing compiler, invests deeply in hot code | Has deep inlining linked with many global optimizations |

Not every method needs to go through 0→1→2→3→4. A compilation of a caller can inline a callee even if the callee has not been compiled separately; conversely, a callee already compiled into an nmethod does not force the caller to inline it.

**A call site can have different decisions across recompilations.** C1 and C2 have different policies; hotter code, different receiver type profiles, or changes in graph size can change the inlining outcome.

## 8. Why Might HotSpot Refuse to Inline?

Inlining aids optimization, but it also **increases code size at the call site**. If a caller invokes the same callee in many places, repeated inlining can bloat the graph/machine code.

Potential costs:

- **Compilation CPU/time:** more IR nodes, optimizer takes longer to process.
- **Code cache pressure:** more native machine code, consuming JVM process memory.
- **Instruction-cache locality:** overly large code makes the CPU instruction cache less effective.
- **Register pressure:** complex graphs can increase spills/reloads.
- **Deoptimization metadata:** the compiler must store state/debug mappings to recover execution correctly.
- **Recursion/call depth:** the compiler must have limits so it does not inline infinite recursion.
- **Exception/monitor/control-flow complexity:** a callee body that is too complex may not be worth inlining or may not be valid for a specific optimization path.

### Inlining Budget and Method Size

The Oracle JDK 25 `java` manual describes these flags:

| HotSpot Flag | General Meaning | Notes |
| --- | --- | --- |
| `-XX:+Inline` / `-XX:-Inline` | Enables/disables method inlining | HotSpot flag; usually enabled by default |
| `-XX:MaxInlineSize=N` | C2: maximum bytecode size for a **cold method** considered for inlining under the relevant mechanism | Not the sole rule deciding every inline |
| `-XX:FreqInlineSize=N` | C2: size limit for a **hot method** | Can be larger than the cold threshold |
| `-XX:InlineSmallCode=N` | C2: code size limit of an already-compiled callee under certain inline conditions | Distinct from bytecode size |
| `-XX:C1MaxInlineSize=N` | C1: cold method size per policy | Do not apply C2 values verbatim to C1 |
| `-XX:MaxTrivialSize=N` | C2: limit for very small/trivial methods | Does not mean the method always inlines |
| `-XX:MaxNodeLimit=N` | Limit on nodes in a single method compilation | Changing it can slow compilation and increase memory use |

Flags may change across JVM releases and are not portable Java APIs. Values in the manual are **defaults/examples for specific versions/configurations**, not memorized rules to apply to every HotSpot instance.

### Common Reasons in `PrintInlining`

Logs may express reasons such as:

- `inline (hot)`: inlined because it is hot/profile fits.
- `inline (hot)` after virtual call analysis or `accessor` in some cases.
- `callee is too large`: callee is too large for the current budget.
- `hot method too big` or similar expressions: method is hot but exceeds the limit.
- `already compiled into a big method`: compiled body is large.
- `recursive inlining too deep`: inline recursion limit.
- `virtual call` / target not sufficiently determined: compiler may keep dispatch.
- `not inlineable` or other constraints: compiler does not inline due to method/body policy.

**Reason strings in logs are not guaranteed to have a fixed format across all JDKs.** Look at the **caller's inlining tree and compile tier**; do not read a single isolated line and conclude all call sites behave the same.

## 9. Runnable Java 17+: Two Small Methods Called in a Hot Loop

Create file **`InliningLab.java`**:

~~~java
public class InliningLab {
    private static volatile long result;

    static int twice(int x) {
        return x * 2;
    }

    static int plusOne(int x) {
        return x + 1;
    }

    static int pipeline(int x) {
        return plusOne(twice(x));
    }

    static long calculate(int iterations) {
        long total = 0;
        for (int i = 0; i < iterations; i++) {
            total += pipeline(i);
        }
        return total;
    }

    public static void main(String[] args) {
        result = calculate(100_000);
        System.out.println("total=" + result);
        System.out.println("single=" + pipeline(7));
    }
}
~~~

Compile/run:

~~~bash
javac -g InliningLab.java
java InliningLab
~~~

**Exact stdout in normal execution, without diagnostics enabled:**

~~~text
total=10000000000
single=15
~~~

Because:

~~~text
pipeline(i) = 2*i + 1
sum(i=0..99999) = 2*(99999*100000/2) + 100000
                = 10,000,000,000
pipeline(7) = 2*7+1 = 15
~~~

`total` is `long` so it can hold 10 billion; `twice(i)` is `int` but `i < 100000` so it does not overflow.

### Trying Runtime Strategies

On a HotSpot supporting these flags:

~~~bash
java -Xint InliningLab
java -Xmixed InliningLab
java -XX:-Inline InliningLab
~~~

**The program output must still be the two lines above** when run successfully. Under `-Xint`, there is no JIT compilation; `-XX:-Inline` adjusts HotSpot JIT policy without changing how methods are called in source and is not a "run everything through the interpreter" flag.

You cannot use timing differences from three short runs like this to claim inlining "speeds things up by N times." JVM startup, tiered warmup, loop OSR, compiler queues, and OS scheduling all add noise to the measurement.

### Comparing `javap` with JIT

~~~bash
javap -c -p InliningLab
javap -v -p InliningLab
~~~

In `pipeline`, you typically see two `invokestatic` instructions calling `twice`/`plusOne` in the class file. After the HotSpot compiler inlines at runtime, the native code may contain the arithmetic inside the caller **without those two native calls at the call sites**.

`javap` **cannot confirm** whether inlining did or did not occur in actual execution, because it does not display C1/C2 machine code.

## 10. Runnable Java 17+: Scope Expansion Helps Analyze Objects

Create file **`ScopeExpansionDemo.java`**:

~~~java
public class ScopeExpansionDemo {
    static final class Pair {
        final int left;
        final int right;

        Pair(int left, int right) {
            this.left = left;
            this.right = right;
        }
    }

    static int score(Pair pair) {
        return pair.left * 2 + pair.right;
    }

    static int makeScore(int base) {
        Pair pair = new Pair(base, base + 1);
        return score(pair);
    }

    public static void main(String[] args) {
        long total = 0;
        for (int i = 0; i < 10_000; i++) {
            total += makeScore(i);
        }

        System.out.println("total=" + total);
        System.out.println("one=" + makeScore(7));
    }
}
~~~

~~~bash
javac -g ScopeExpansionDemo.java
java ScopeExpansionDemo
~~~

**Exact stdout:**

~~~text
total=149995000
one=22
~~~

Because:

~~~text
makeScore(base) = 2*base + (base+1) = 3*base+1
sum(i=0..9999) = 3*(9999*10000/2)+10000
               = 149,995,000
makeScore(7) = 3*7+1 = 22
~~~

**Key takeaway:** if HotSpot inlines `score` and analyzes that the `Pair` object does not escape, it **can** scalar-replace `Pair`, eliminating the allocation, field loads, and part of the related operations in optimized machine code.

**Do not infer** from the result `149995000` that scalar replacement definitely occurred. A short program may run in the interpreter/C1/C2 depending on workload and JIT thresholds. The output only proves Java semantics and the computation path.

If you want to inspect inlining, you can run the program with `PrintCompilation`/`PrintInlining` and observe compilation of `makeScore`/`score`; if you want to prove allocation elimination, you need an appropriate profiler/instrumentation, JIT compilation state, and sufficient warmup.

## 11. Runnable Java 17+: Virtual Calls and Receiver Profiles

Create file **`ReceiverInliningDemo.java`**:

~~~java
public class ReceiverInliningDemo {
    interface Adjuster {
        int apply(int value);
    }

    static final class AddTwo implements Adjuster {
        public int apply(int value) {
            return value + 2;
        }
    }

    static final class TimesThree implements Adjuster {
        public int apply(int value) {
            return value * 3;
        }
    }

    static int call(Adjuster adjuster, int n) {
        return adjuster.apply(n);
    }

    public static void main(String[] args) {
        Adjuster common = new AddTwo();
        Adjuster other = new TimesThree();

        int sum = 0;
        for (int i = 0; i < 10_000; i++) {
            sum += call(common, 4);
        }

        System.out.println("common-sum=" + sum);
        System.out.println("other=" + call(other, 4));
    }
}
~~~

~~~bash
javac -g ReceiverInliningDemo.java
java ReceiverInliningDemo
~~~

**Exact stdout:**

~~~text
common-sum=60000
other=12
~~~

`AddTwo.apply(4)` returns 6; repeated 10,000 times, the sum is 60,000. `TimesThree.apply(4)` returns 12.

**What the program demonstrates:** a call site through an interface can encounter different receiver types and must preserve correct dynamic dispatch.

**What the program does not prove:** whether the call site was monomorphic-optimized, whether `AddTwo` was inlined, or whether it deoptimized upon encountering `TimesThree`. A JVM might not have compiled the method yet or might have a compiled fallback; only logs/compiled-code instrumentation can verify.

## 12. Observing HotSpot Inlining Directly

Per the Oracle JDK 25 `java` manual, enable diagnostics:

~~~bash
java -XX:+PrintCompilation InliningLab
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining -XX:+PrintCompilation InliningLab
~~~

If a method is not hot enough for the compiler to log events, **there is no promise** that logs for `pipeline` or `twice` will appear. You can try increasing workload/iterations in a test environment and ensuring sufficient compilation time, but do not draw benchmark conclusions from a single run.

### Reading the Inlining Tree

An **illustrative format** log, not mandatory output:

~~~text
   @ 3   InliningLab::twice (4 bytes)   inline (hot)
   @ 6   InliningLab::plusOne (4 bytes) inline (hot)
~~~

Typically, indentation represents nested inlining, `@ BCI` represents the call site offset in the caller, and the accompanying reason shows how the compiler evaluated it. The bytecode size in bytes in the example is **illustrative and hypothetical**, not to be memorized; `javac` versions and class contents may produce different numbers.

**You must pair `PrintInlining` logs with the compilation under consideration**: if a compiler is compiling `calculate`, the tree may show `pipeline`, and then `twice`/`plusOne` nested inside. Do not interpret indentation as a runtime Java call stack.

### Reading Rejection Reasons

Hypothetical log format examples:

~~~text
@ 12  SomeClass::largeHelper (350 bytes) callee is too large
@ 21  SomeClass::virtualCall (20 bytes)  virtual call
@ 33  SomeClass::recursive (8 bytes)     recursive inlining too deep
~~~

The reasons are hints as to **why a specific candidate was rejected at a call site**. They do not mean the method "cannot be inlined in any program."

### Compilation Logs Can Be Written to a File

With HotSpot diagnostic support:

~~~bash
java -XX:+UnlockDiagnosticVMOptions -XX:+LogCompilation InliningLab
~~~

Usually, the VM writes compilation XML/logs to a file specified by `-XX:LogFile` or a version-dependent default. This is useful with appropriate inlining-tree/JITWatch analysis tools; logs can be very large, so do not leave them enabled continuously in production without managing retention/disk.

### Compiler Control (Advanced)

The Oracle JDK 25 VM Guide covers **Compiler Control**, which allows applying directives at the method/pattern level, including directives to inline or not inline within the applied scope. This is a research/diagnostics tool, **not the default way to optimize Java code in production**.

Do not write Java code relying on a hypothetical "`@Inline`" annotation as a public Java standard. HotSpot has internal annotations/intrinsics, but they are not portable APIs that applications should treat as a language contract.

## 13. Inlining and Target Selection: `static`, `private`, `final`, Virtual, Interface

| Call type | How clear is the target usually? | What other factors remain? |
| --- | --- | --- |
| `invokestatic` | Target is determined by resolution according to bytecode | Compiler budget, side effects, class-init/linking semantics |
| `invokespecial` | Constructor/private/super calls with appropriate semantics | Method size, recursion, exceptions, and costs |
| `invokevirtual` | Runtime selection by receiver | Type profiles, class hierarchy, guards, fallback |
| `invokeinterface` | Runtime interface dispatch | Receiver types, devirtualization, and guards |
| `invokedynamic` | Dynamically linked call site from bootstrap | Call-site target stability, MethodHandle graphs, compiler rules |

**This is not a table of "which opcodes get inlined / which opcodes do not."** All call forms can be inlined by the compiler when correctness and profitability are satisfied. The main difference is the certainty of target information and the conditions for guarding assumptions.

A `final` method may make target determination easier, but HotSpot can still decline to inline it if the method is too large. Conversely, an interface call with a stable receiver type profile can be inlined very effectively.

**`@Override` is not an inline hint.** This annotation tells the compiler to check Java overriding correctness; it does not instruct HotSpot to inline.

## 14. Inlining Must Not Change Java Behavior

For example:

~~~java
static int safelyDivide(int a, int b) {
    return a / b;
}

static int caller(int value) {
    return safelyDivide(value, 0);
}
~~~

This is an illustrative method, not a standalone file. If the compiler inlines `safelyDivide(value,0)`, **`ArithmeticException`** must still occur when the code path is executed according to Java semantics. The compiler must not silently return 0 because of inlining.

Other rules must also be preserved:

- **Null checks:** dereferencing `null` must follow Java `NullPointerException` semantics when appropriate.
- **Array bounds:** out-of-bounds access must still throw `ArrayIndexOutOfBoundsException`.
- **Class initialization/linkage:** the compiler must preserve observable actions and errors strictly according to the JVM specification.
- **`synchronized`/monitors:** monitor operations may only be eliminated when proven equivalent under the Java Memory Model.
- **`volatile`:** memory ordering/visibility effects cannot be arbitrarily removed.
- **Exceptions and stack traces:** the runtime has debug/scope metadata to reconstruct logical Java frames when needed, even when native frames are inlined.

### Stack Traces and Inlined Frames

A method can be inlined while a debugger/profiler still displays it as a **logical Java frame**. The JIT maintains metadata to restore call context, exceptions, and deoptimization. Therefore, **seeing a method in a stack trace does not prove the JIT did not inline it**.

Also, do not treat the number of Java stack frames in a profiler sample as the actual number of native call instructions after inlining.

## 15. Excessive Inlining Can Slow Down a Program

Suppose `BigHelper` is long and is called at 20 different call sites. If the JIT copies its logic into every caller:

~~~text
Caller1  +  Body(BigHelper)
Caller2  +  Body(BigHelper)
...
Caller20 +  Body(BigHelper)
~~~

Total native code size can grow much larger than keeping a shared nmethod and calls. Consequences:

- Code Cache fills up faster.
- CPU instruction cache misses and iTLB pressure may increase.
- Register allocation becomes harder, causing more spills.
- JIT compilation time and CPU usage increase.
- Deoptimization metadata becomes more complex.
- Startup/warmup latency may worsen.

Therefore, the statement **"the more you inline, the faster it gets"** is false. A small callee called very frequently is usually a good candidate; a huge callee with many cold branches may not be worth duplicating.

**Compiler heuristics are pragmatic compromises**, not promises of global optimality. The `MaxInlineSize` and `FreqInlineSize` flags are tuning/diagnostics tools, not values to increase arbitrarily.

## 16. Differences Between Inlining and Easily Confused Optimizations

| Concept | Nature | Synonymous with inlining? |
| --- | --- | --- |
| **Inlining** | Brings callee IR/body into the caller's call site | The concept being studied |
| **Devirtualization** | Selects/narrows a virtual call's target using type info | No; helps pave the way for inlining, or may just directify the call |
| **Tail-call optimization** | Transforms tail calls using a different strategy | No; Java/HotSpot does not promise general TCO for all methods |
| **Escape analysis** | Determines whether an object/reference escapes | No; inlining can expand analysis |
| **Scalar replacement** | Replaces an object with its component fields/values, eliminating allocation | No; it is a downstream optimization |
| **Constant folding** | Precomputes expressions with constants | No; inlining often exposes constants |
| **Intrinsic** | Compiler/runtime uses a specialized implementation for a method/operation | Not synonymous with the JIT copying bytecode body |
| **Loop unrolling** | Repeats the loop body in the compiled representation | No; operates on loops, may occur after inlining |
| **OSR** | Transfers into a compiled loop while a method is running | No; OSR compilation may or may not inline callees |
| **AOT** | Prepares code before runtime execution using specific technology | No; compilation timing is different |
| **`javac` optimization** | Transformations by the Java source-to-bytecode compiler | Not equivalent to C2 inlining at runtime |

**Inlining often acts as an "enabler":** on its own it can reduce call overhead, but its real value is letting the compiler see optimizations that were previously obscured by the call boundary.

## 17. How to Investigate If a Method "Does Not Inline as Expected"

A safe workflow:

1. **Confirm the method is compiled:** use `-XX:+PrintCompilation` or a runtime profiler. Not seeing the method in the log could mean it is cold or was already inlined into another caller's compilation; analyze accurately.
2. **Identify the caller and call site:** the compiler decides per site, not just by callee name.
3. **Enable `PrintInlining` in a test environment:** read the tree and reasons, distinguishing C1/C2 compile tiers.
4. **Check profiles:** is the caller hot, are receiver types mono/poly/mega, what is the method invocation/backedge frequency?
5. **Check code size/budget:** callee bytecode length, graph complexity, recursion, inline depth, native code size.
6. **Check JIT state:** has the method warmed up, is the code cache full, are compilation jobs delayed?
7. **Measure outcomes that matter:** CPU cycles, throughput, P95/P99 latency, allocation/GC metrics, code cache, compilation time.
8. **Only adjust flags with evidence:** `-XX:-Inline` for controlled comparison; changing size thresholds requires benchmarking and verification on real JDK/GC/workloads.

**Do not run `System.nanoTime()` once and conclude inlining improves performance by exactly N%.** Startup, tiered compilation, OSR, dead-code elimination, constant folding, GC, and OS scheduling all affect results. Use **JMH** for microbenchmarks with warmup/forks, and real server workloads to measure end-to-end impact.

## 18. Common Misconceptions

| Statement | What is true |
| --- | --- |
| "Inlining is copying Java source into another method." | The JIT expands **IR/body** when compiling, it does not rewrite Java source. |
| "`javap -c` has no `invoke` means it was inlined." | `javap` reads class-file bytecode; JIT inlining happens in runtime compiled code. |
| "`static` methods are guaranteed to be inlined." | The target is clearer, but compiler budgets and profitability still apply. |
| "`final` or `private` is a mandatory signal." | No. HotSpot does not promise to inline those methods. |
| "Java interface calls are never inlined." | Profile-guided devirtualization and guarded inlining are possible. |
| "Inlining only saves the overhead of one call." | It also expands IR analysis scope, which often yields large gains. |
| "C1 does not inline, only C2 inlines." | C1 also has an inlining policy. |
| "Every call site of a callee has the same inlining decision." | Decisions are usually per-call-site, per-compilation. |
| "Once a callee is compiled separately, the caller must inline it." | No. Independent compilation differs from inlining at the caller. |
| "After inlining, all checks/exceptions are removed." | Java semantics, guards, and exceptions must still be preserved. |
| "The JIT always needs to represent a separate native stack frame for each inlined method." | Debug/deopt retains logical frames, without requiring separate native call frames. |
| "Having a method in a stack trace proves it was not inlined." | No. The JIT can reconstruct logical Java frames. |
| "Every non-escaping object is moved to the native stack." | HotSpot can scalar-replace and **eliminate the allocation**, without promising general stack allocation. |
| "Increasing MaxInlineSize will definitely increase throughput." | Code growth/compile cost/cache pressure can slow things down. |
| "Once a caller is optimized, it no longer needs deoptimization." | Guard assumptions can be invalidated. |
| "Inlining changes the meaning of synchronized/volatile." | The compiler must preserve the Java Memory Model. |
| "`-XX:-Inline` turns the JVM into interpreter-only." | It disables JIT method inlining per HotSpot policy, not JIT compilation. |
| "`PrintInlining` has a fixed output across all JDKs." | Compiler decisions/format depend on JDK, tier, profile, and workload. |
| "A single-line source method is always trivial." | Bytecode and side effects, intrinsic/VM behavior still matter. |
| "A single cold benchmark is enough to know if inlining is worth it." | You must distinguish startup, warmup, and steady-state. |

## 19. Self-Check with Answers

**Question 1.** Why can inlining bring benefits beyond reducing call overhead?  
**Answer:** It opens the IR between caller and callee, allowing constant propagation, dead-code elimination, range analysis, escape analysis, and other optimizations to see across the method boundary.

**Question 2.** Is `private static int f(int)` guaranteed to be inlined?  
**Answer:** No. The target may be clear, but the compiler considers hotness, code size, budget, depth, and profitability.

**Question 3.** `javap -c` still shows `invokestatic` after the program has run with JIT. Does that prove no inlining occurred?  
**Answer:** No. `javap` reads the original class file; JIT inlining affects compiled IR/native code at runtime.

**Question 4.** Can two call sites calling the same callee have different inlining decisions?  
**Answer:** Yes, based on caller context/profile/budget and compiler tier.

**Question 5.** Why can inlining `score(Pair)` into `makeScore` help eliminate object allocation?  
**Answer:** After inlining, the compiler sees `Pair` only has its fields read without escaping, so it can apply escape analysis and scalar replacement.

**Question 6.** Can a virtual/interface call be inlined?  
**Answer:** Yes, via devirtualization/receiver type profiling, guards, or CHA when valid.

**Question 7.** If a new receiver type appears after optimized compilation, what ensures correctness?  
**Answer:** Runtime guards, generic fallback/deoptimization, dependency invalidation, and appropriate recompilation.

**Question 8.** Do C1 and C2 have identical inlining policies?  
**Answer:** No. They have different budgets, optimization goals, and profiles.

**Question 9.** How do `-XX:FreqInlineSize` and `-XX:MaxInlineSize` differ in C2?  
**Answer:** The former relates to the hot-method inline size limit; the latter is the cold-method bytecode inline size limit in the documented policy.

**Question 10.** Why can inlining a very large callee into 20 callers slow things down?  
**Answer:** Native code growth, instruction cache pressure, compile CPU/memory overhead, and register spills.

**Question 11.** What output does `InliningLab` produce?  
**Answer:** `total=10000000000` and `single=15` in normal execution, regardless of inlining decisions.

**Question 12.** Does `ReceiverInliningDemo` prove deoptimization occurred?  
**Answer:** No. The output only proves correct dynamic dispatch; the compiler may not have compiled yet or may have taken a fallback path.

**Question 13.** What tool is used to observe HotSpot inlining decisions?  
**Answer:** `-XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining -XX:+PrintCompilation` on a supported HotSpot.

**Question 14.** Can the JIT remove an exception in a method after inlining?  
**Answer:** Not if the exception can still occur under Java semantics; it can only remove checks/paths proven unnecessary.

## 20. Official References

- [Oracle JDK 25 — `java` Command, Advanced JIT Compiler Options](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-XX:+Inline`, `-XX:-Inline`, `MaxInlineSize`, `FreqInlineSize`, `InlineSmallCode`, `C1MaxInlineSize`, `PrintCompilation`, and `PrintInlining`.
- [Oracle JDK 25 — Java HotSpot Virtual Machine Performance Enhancements](https://docs.oracle.com/en/java/javase/25/vm/java-hotspot-virtual-machine-performance-enhancements.html): Tiered Compilation, Code Cache, escape analysis, and scalar replacement.
- [Oracle JDK 25 — Java Virtual Machine Guide](https://docs.oracle.com/en/java/javase/25/vm/index.html): HotSpot/compiler technology, Compiler Control, and performance.
- [JVMS Java SE 25 — Chapter 6, Instruction Set](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-6.html): `invokestatic`, `invokevirtual`, `invokeinterface`, `invokespecial`, and JVM bytecode semantics.
- [JVMS Java SE 25 — §4.7.3 Code Attribute](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.7.3): method code bytes and metadata required for execution.
- [OpenJDK HotSpot — C2 compiler source](https://github.com/openjdk/jdk/tree/master/src/hotspot/share/opto): compiler optimization and inlining implementation; the master branch may differ from the actual running version.
- [OpenJDK HotSpot — C1 compiler source](https://github.com/openjdk/jdk/tree/master/src/hotspot/share/c1): C1 inlining and compiler policies.
- [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/): more reliable Java performance measurement than a single cold benchmark.

**Key takeaway:** Inlining in HotSpot **brings the callee's code into the caller's analysis scope at a call site**, which can both reduce invocation overhead and pave the way for **interprocedural optimizations** such as constant propagation, escape analysis, and scalar replacement. However, excessive inlining can cause **code bloat**, consume compilation time, and worsen cache locality. HotSpot therefore uses **profiling, C1/C2 heuristics, budgets, guards, and deoptimization** to balance benefits against costs while preserving Java semantics.