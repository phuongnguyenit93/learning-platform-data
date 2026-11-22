# Type-Based Devirtualization and the Limits of Assumptions

**Devirtualization** is a group of JIT compiler optimizations aimed at turning a call capable of **dynamic dispatch** to multiple implementations into a **direct call path** to the appropriate target, or into **type-checked branches** where the common branch can execute directly. Once the target is known, the JIT gains further opportunities for **method inlining**, constant propagation, dead-code elimination, escape analysis, and other optimizations.

In the **HotSpot JVM**, the information used can come from:

1. **Certain static knowledge**, such as when the receiver has a proven exact runtime type or the method cannot be overridden.
2. **Class Hierarchy Analysis (CHA)**: analyzing the classes/hierarchies **currently known to the JVM** to find a unique method target; if the program can load new classes, compiled code must have a mechanism to track/revoke assumptions.
3. **Type profiling**: data HotSpot collects at a **call site** about actual concrete receiver classes, for example a site that almost only sees one type.
4. **Constraints from flow analysis**: type checks, casts, allocations, and branch checks can narrow the set of receiver types on an execution path.

**Do not misunderstand** devirtualization as changing Java semantics. Java must still invoke the right implementation according to the **runtime class of the receiver**, obeying dynamic class loading, overload/override, null checks, exceptions, and the Java Memory Model. Speculative optimizations can be invalidated via **deoptimization** or fall through to a **fallback dispatch path** when an assumption is wrong.

This article focuses on these optimizations in **HotSpot with JDK 17+**. CHA, type-profile-based speculation, inline caches, compiled nmethods, and C1/C2 are **implementation details**, not a guarantee that every JVM uses the same algorithm or always devirtualizes every virtual call.

## 1. What is Dynamic Dispatch?

Consider an interface:

```java
interface Payment {
    int calculate(int amount);
}

final class StandardPayment implements Payment {
    @Override
    public int calculate(int amount) {
        return amount + 2;
    }
}

final class PremiumPayment implements Payment {
    @Override
    public int calculate(int amount) {
        return amount * 2;
    }
}
```

These are valid classes/interfaces, but this snippet **does not yet have a `main`**. A method using the interface:

```java
static int pay(Payment payment, int amount) {
    return payment.calculate(amount);
}
```

If placed in a valid class, the static type of `payment` is `Payment`. However, at runtime, `payment` may point to `StandardPayment` or `PremiumPayment`; the two implementations return different values.

```text
Call site: payment.calculate(amount)
                    │
                    ▼
          runtime receiver class?
                /       \
               /         \
    StandardPayment   PremiumPayment
       amount + 2       amount * 2
```

**Java-level semantics:** the target depends on the receiver runtime type. Do not infer from the **variable declaration of type `Payment`** that the JVM will definitely call a specific class.

### Characteristics of Polymorphism

- **Overloading**: selecting a method signature according to Java's compile-time rules; this is a different matter.
- **Overriding**: a subclass/interface implementation defines the corresponding method; runtime dispatch chooses the appropriate implementation.
- **Dynamic dispatch**: controls method selection by runtime type when the call instruction has dynamic-dispatch semantics.
- **Devirtualization**: optimizes how dispatch is executed; **it does not remove the right to override** that Java allows.

**Key point:** the same call site bytecode can invoke different concrete methods at different times if the receiver types differ.

## 2. Related Bytecode: invokevirtual and invokeinterface

The JVM has different method invocation instructions:

| JVM opcode | Primary role | Relation to devirtualization |
| --- | --- | --- |
| `invokevirtual` | Instance method call dispatched by runtime class | HotSpot can eliminate dispatch when the target is determined |
| `invokeinterface` | Method call through an interface; finds the matching implementation | Can be optimized using CHA/type profile |
| `invokespecial` | Calls constructors, `super`, and certain instance methods under special rules | Not equivalent to generic virtual dispatch |
| `invokestatic` | Calls a static method | Not a dynamic receiver call |
| `invokedynamic` | Dynamic call site linked via a bootstrap method | Separate linkage mechanism; do not equate with `invokevirtual` |

In the example above, `payment.calculate(amount)` is typically compiled by `javac` into **`invokeinterface`** because the call site signature uses an interface. If the static type is a non-interface class, the instance method call may be represented by **`invokevirtual`**.

**Important regarding terminology:** an `invokevirtual` bytecode **does not prove** the CPU must perform a vtable lookup on every execution. The JIT can turn it into a direct call or inline it; `javap -c` still prints the old bytecode because the JIT does not modify the class file.

### Direct Binding Differs from JIT Devirtualization

If a method is `static`, the JVM already uses `invokestatic`; that is **not** the problem of eliminating dynamic dispatch at a potentially polymorphic call site. Similarly, `super.method()` and constructors use `invokespecial` under separate rules.

A `final` method or `final` class can allow the compiler to determine the target statically even when the bytecode remains `invokevirtual`. What matters is **overridability/actual target**, not just the opcode name.

## 3. Execution Path Before and After Optimization

**Before optimization (logical model):**

```text
load receiver
  │
  ├─ null? → NullPointerException per semantics
  │
  ▼
resolve/dispatch to concrete target
  │
  ▼
call the right implementation
```

**After the JIT has evidence for a common target:**

```text
load receiver
  │
  ├─ null semantics must still hold
  │
  ▼
check receiver type == HotClass?
       │              │
      yes             no
       │              │
       ▼              ▼
inlined/direct     generic virtual dispatch
HotClass path      or uncommon trap
       │              │
       └──────────────┘
                 │
                 ▼
            correct Java result
```

This is a conceptual diagram. In actual machine code, the null check may use an **implicit null check**, guards may be reordered/merged, and the miss branch may use **deoptimization**, a **runtime stub**, or a fallback virtual call. There is no guarantee that all HotSpot versions insert an exact `instanceof` or `getClass()` check in the order shown.

### Devirtualization Is Not Necessarily Inlining

- **Devirtualization**: determining or narrowing the **callee target** to avoid generic dispatch on the hot path.
- **Inlining**: placing the called method's logic **into the caller's code**, eliminating the need for a separate call boundary on that path.
- It is possible to **devirtualize without inlining**, if the callee is too large, the compiler budget is exhausted, or heuristics see no benefit.
- It is possible to **inline multiple targets** in guarded polymorphic call site branches.
- Inlining opens the door to many cross-method optimizations, but increases code size, which can put pressure on the **code cache** and instruction cache.

Do not treat a “`inline (hot)`” log as a certification that **every** interface call in the application has turned into direct/inlined code.

## 4. Cases Where the Target Can Be Determined with Certainty

There is information that allows the JIT to **prove** a method call does not have multiple valid targets on the relevant execution path.

### 4.1. `final` Class

```java
final class FixedCalculator {
    int compute(int x) {
        return x + 1;
    }
}
```

`FixedCalculator` cannot have valid subclasses under Java rules. If the receiver has this exact runtime class and the specific method has no other dispatch variants, determining the target is very straightforward. However, **optimization still depends on compiler policy**: there is no contract that the method will always be inlined or that the code will consist of just a single addition.

### 4.2. `final` Method

```java
class Base {
    final int stable(int x) {
        return x + 3;
    }
}
```

Subclasses cannot override `stable(int)`; the compiler has more information about the target. **It is not** that the `final` keyword automatically produces faster machine code on every call: the JIT still considers method size, execution frequency, inlining budgets, and profiling.

### 4.3. Exact Runtime Type Proven from Flow

```java
static int use() {
    FixedCalculator c = new FixedCalculator();
    return c.compute(10);
}
```

This is an illustrative method, which needs to be placed in a class that can access `FixedCalculator`. In the case above, the compiler can deduce the exact type of `c` at the call site, regardless of whether a particular build chooses to inline it.

However, if you write `Base b = loadFromExternalSource();`, there is no proof of exact type yet. The static type name `Base` does not by itself assert that the runtime type is always `Base`.

### 4.4. Sealed Types in Java 17

```java
sealed interface Token permits TextToken, NumberToken {}

final class TextToken implements Token {}

final class NumberToken implements Token {}
```

Java 17 supports sealed classes/interfaces to restrict which types are **directly** permitted to extend/implement them. This is useful structural information, but **not enough to claim the JIT definitely knows a single method target**: a sealed hierarchy can still have multiple concrete classes, non-sealed branches within a suitable hierarchy, and JIT policy may not exploit that information in every runtime.

**Do not equate “closed hierarchy” with “monomorphic call site”.** A sealed interface with two implementations can easily receive both types at the same site.

## 5. Class Hierarchy Analysis (CHA)

**CHA** analyzes the relationships between classes/interfaces and the concrete method targets that the JVM **already knows or can prove under the constraints it manages**.

Suppose:

```java
abstract class Handler {
    abstract int run(int x);
}

final class OnlyHandler extends Handler {
    @Override
    int run(int x) {
        return x * 3;
    }
}
```

At a point when the JVM only knows `OnlyHandler` as a concrete subtype of `Handler`, a call `handler.run(x)` through `Handler` may **currently have a single unique concrete target**. HotSpot can use that information to devirtualize/inline.

### But the Class Hierarchy Can Change

Java allows **dynamic class loading** according to class loader/runtime rules. A new class loaded after code has been JIT-compiled can introduce another concrete implementation.

```text
Time T1:
  Handler
     └── OnlyHandler    (unique loaded concrete target)

JIT at T1: uses CHA assumption → optimized call path

Time T2:
  Handler
     ├── OnlyHandler
     └── AnotherHandler (loaded later)

JVM must reconcile compiled assumptions with the
new hierarchy: invalidate/deopt/recompile when needed.
```

**Safety principle:** if the JIT optimizes based on the assumption “there is only one **currently known** concrete target”, that assumption **is not invariant for the lifetime of the process**. HotSpot tracks the relevant **compiled-code dependencies** and can mark an nmethod non-entrant, deoptimize, or recompile when hierarchy invalidation occurs.

You cannot take a snapshot at T1 and claim the JVM will call `OnlyHandler` when receiving an `AnotherHandler` object at T2. If Java semantics require calling the new override, the VM must do so correctly.

### CHA Differs from Type-Profiling-Based Devirtualization

| Information source | Nature | Limitations |
| --- | --- | --- |
| **CHA** | Based on the class hierarchy and the set of known targets | Dynamic loading can invalidate old assumptions |
| **Runtime type profile** | Based on the receiver types actually observed at the **call site** | Workload/traffic can change; profile may miss rare types |
| **Exact type proof** | Based on certain static/dataflow constraints on a path | Only applies where the compiler can prove it |
| **Final method/class** | Prevents overriding or subclassing per appropriate Java semantics | Does not by itself guarantee the compiler chooses to inline |

These sources of information **can be used in combination**, not as four mutually exclusive algorithms.

## 6. Type Profiling: A Call Site Can Be Monomorphic or Polymorphic

A type profile describes **behavior at a call site**, not simply “how many implementations of the interface the application has”.

| Call site type | Common observation | Optimization opportunity |
| --- | --- | --- |
| **Monomorphic** | Site almost only sees one concrete receiver type | Guarded/direct devirtualization and inlining are favorable |
| **Bimorphic/small polymorphic** | Site sees a few concrete types, perhaps two | Can generate multiple guarded paths/inlining targets |
| **Megamorphic** | Site sees many receiver types; profile does not well represent a small set | Generic dispatch may be more economical and stable |
| **Unprofiled/cold** | Not enough runtime evidence yet | Interpreter/C1 or generic call path |

**There is no invariant threshold where “megamorphic = exactly 3 classes”.** HotSpot has capacities/caps for recording type profiles depending on build/flags, while making inlining decisions based on budgets, probabilities, and hotness. A framework with hundreds of implementations across the entire process where each site only receives one type can still have **monomorphic sites**.

### Example of Two Different Call Sites

```java
static int siteA(Payment p, int x) {
    return p.calculate(x);
}

static int siteB(Payment p, int x) {
    return p.calculate(x);
}
```

These are illustrative methods in a class. If `siteA` only receives `StandardPayment` while `siteB` receives both implementations, **their type profiles can differ** even though both have the same Java signature and the same source-level interface call.

The JIT can inline `siteA` and keep dispatch at `siteB`. There is **no contradiction**: per-call-site optimization is a property of the runtime path, not a global decision for every invocation of the interface.

### A Call Site Can Also Reside Inside a Compiled Caller After Inlining

If a method `route(Payment p)` is inlined into another caller, compiler transformations can create new exact type specialization opportunities. Therefore, when reading logs, consider the **inlining tree context and BCI**, not just a method name.

## 7. Guarded Devirtualization and Polymorphic Inline Caches

When the profile indicates that a type `FastPayment` appears most of the time, the JIT can use the pattern:

```text
if (receiver is FastPayment) {
    // direct call or inline FastPayment.calculate()
} else {
    // fallback virtual/interface dispatch
    // or uncommon trap → deopt/reprofile
}
```

This is **pseudocode**, not actual Java source that HotSpot must generate. What matters is that the **guard protects speculation**:

- If the receiver is the predicted type, run the fast path.
- If the receiver is different, **it must not call the wrong** implementation.
- If the receiver is null, it must preserve the `NullPointerException` result per semantics.
- If the class hierarchy changes, compiled dependencies must be handled safely.
- Exceptions/side effects of the target method must remain semantically unchanged.

**Polymorphic Inline Cache (PIC)** is a concept commonly used for a dispatch path where several receiver shapes/types are cached/checked for speedup. HotSpot has inline cache mechanisms, profile-based type guards, and compiled call optimizations, but **one should not claim every optimized call site is implemented with the exact same PIC structure**. The term describes a family of techniques; actual machine code depends on the VM/CPU/JDK.

### Two Hot Targets

If a site frequently sees `FastPayment` and `DiscountPayment`, the VM may choose the illustrative logic:

```text
receiver == FastPayment klass?
  yes → optimized FastPayment path
  no  → receiver == DiscountPayment klass?
           yes → optimized DiscountPayment path
           no  → general dispatch / deoptimization
```

The compiler **is not obligated to generate exactly two guards**. If code size/branch prediction/inline budget is unfavorable, it may choose generic virtual dispatch even though the profile sees few types.

## 8. Limits of Assumptions: Why Is Deoptimization Needed?

A profile assumption can become wrong over time. For example:

- An endpoint previously only received `StandardPayment`.
- At runtime it begins receiving `PremiumPayment` as well when traffic changes.
- A plugin loader loads a new implementation.
- Dynamic proxies or generated classes produce multiple receiver types.
- Optimized inlining assumed a single hierarchy target, but class loading changed the hierarchy.

This is not a Java bug or proof that the compiler compiled incorrectly: **HotSpot must have a fallback exit**.

### Uncommon Trap and Code Invalidation

The JIT can emit an **uncommon trap** when a rare branch occurs or an assumption no longer holds. The JVM can:

1. Stop execution of the compiled path at a valid point.
2. Reconstruct the necessary bytecode frames/locals/operand stacks state.
3. Continue via the interpreter or other compiled code.
4. Update the profile/trap history and recompile if the method remains hot.

Previous native code can be marked **not entrant** so it no longer accepts new calls; reclaiming compiled code must safely respect executing threads.

### A Guard Failure Does Not Necessarily Equal “Deopt”

A compiler can also arrange a **fallback virtual dispatch** when a guard fails, without needing to deopt every time. Thus, seeing a callsite become polymorphic **does not prove** a specific uncommon trap occurred; actual JVM compiler diagnostics are needed.

### Deoptimization Does Not Cause the Program to Return Wrong Results

For example:

```java
Payment p = obtainPayment();
int result = p.calculate(10);
```

This is a snippet inside a method; `obtainPayment()` is not defined. Even if the JIT previously observed `p` to be mostly `StandardPayment`, if this time it receives `PremiumPayment`, the JVM must still return **20** (per the `PremiumPayment` definition in the earlier example), not **12**. If the guard detects a different type, it selects the valid implementation.

**Core point:** assumptions are allowed to **speed up the common path**, not to **narrow the set of valid Java behaviors**.

## 9. Dynamic Class Loading and the Limits of CHA

On a JVM supporting dynamic loading, an unloaded class may exist on the classpath/JAR or be generated at runtime. Its absence from the current hierarchy **does not prove it cannot appear in the future**.

Points to note:

- CHA relies on the facts and dependency management the VM is able to maintain.
- Changes to the inheritance tree can force invalidation of compiled code.
- A loaded class does not necessarily produce instances that actually enter a hot call site.
- Conversely, a new type may appear at a call site even though it was loaded earlier; in that case, the type profile used for optimization may change.
- Class loader identity is part of **runtime type identity**. The same class name in two class loaders is not always the same runtime class.
- Reflection, dependency injection, and plugin systems can make the hierarchy more “open” over time.

**Do not** automatically conclude from having a plugin architecture that the JIT cannot devirtualize at all. A call site can still be monomorphic for the majority of traffic; the VM uses guards/dependency checks to preserve correctness.

### Interface Default Methods and Method Resolution

Java interfaces can have `default` methods and resolution rules that are more complex than a class-only hierarchy. HotSpot must obey the JVM's method lookup/linkage rules, including interface resolution and the errors defined when a program becomes invalid after binary-compatible changes.

Therefore, “knowing the receiver's class” is a very important part, but **does not mean an `invokeinterface` is always optimized simply by comparing a class name string**. The VM also resolves the target method according to runtime metadata and JVM linkage rules.

## 10. Inlining Amplifies the Benefits of Devirtualization

Suppose the compiler determines `calculate` always calls the implementation:

```java
final class AddFee {
    int calculate(int x) {
        return x + 2;
    }
}

static int finalAmount(AddFee fee, int base) {
    return fee.calculate(base) * 3;
}
```

This is illustrative code placed in a valid class/compilation unit. If the JIT inlines the small method, the operation can optimize to roughly:

```text
result = (base + 2) * 3
```

But this is **not measured native assembly**, only **computationally equivalent semantics**. The compiler must preserve null checking if `fee` can be null: calling `fee.calculate(...)` must throw `NullPointerException` on the required path. It cannot arbitrarily replace a call with an arithmetic expression if doing so would eliminate an observable error or side effect.

### Cross-Method-Boundary Optimizations

After inlining, the JIT can see:

- Caller constants passed into the callee.
- Unnecessary branches on a hot path.
- Array bounds checks that can be proven safe.
- Non-escaping allocations, creating opportunities for scalar replacement.
- Loop computations that can be hoisted/vectorized under the right conditions.
- Return values that can be constant-folded when inputs are fixed.

**However:** the Java Memory Model, volatile operations, locking, exception ordering, and side effects remain correctness constraints. The JIT must not delete a side effect just because a method was inlined.

### Devirtualization Does Not Automatically Make Calls Zero-Cost

A guarded path can add checks/branches, code cache pressure, instruction cache pressure, and deoptimization work. If the call target is small and hot, inlining can win; if the callsite is megamorphic or targets are too large, generic dispatch may be more economical.

## 11. C1, C2, and Warm-Up: Why Does JIT State Change Over Time?

HotSpot tiered compilation can run a method in the interpreter, then C1, and then C2 when it is hot and has sufficient profile. Typically:

- **Interpreter / C1 profiling** collects invocation/backedge counters and type/branch data.
- **C1** can generate fast code to reduce interpretation overhead while still profiling.
- **C2** can use type profiles/CHA to devirtualize and inline hot calls.
- If assumptions change, **deopt/recompile** can occur.

Not all JIT optimizations exist only in C2; C1 also has its own optimizations and guarded call mechanisms. However, C2 generally has a larger budget and deeper optimization structures.

### A Benchmark Can Go Through Multiple “Generations” of Compiled Code

```text
Startup:
  call site still cold → interpreter/generic dispatch

Warm-up A:
  receiver = ClassA frequent → monomorphic profile
  → C1/C2 can create optimized ClassA fast path

Traffic phase B:
  receiver = ClassB appears
  → guard fail/fallback or deopt

Warm-up B:
  profile has more types
  → recompile or generic dispatch
```

**Do not infer** performance results after 1,000 calls from the state of the same method after 1 million calls. Compiler thresholds, queue length, code cache, and CPU quotas also have an effect.

## 12. Runnable Java 17+: One Call Site Receiving Multiple Receiver Types

To observe the principle, create the file **`DevirtualizationDemo.java`**:

```java
public class DevirtualizationDemo {
    interface Operation {
        int apply(int x);
    }

    static final class PlusTwo implements Operation {
        @Override
        public int apply(int x) {
            return x + 2;
        }
    }

    static final class TimesTwo implements Operation {
        @Override
        public int apply(int x) {
            return x * 2;
        }
    }

    static final class MinusOne implements Operation {
        @Override
        public int apply(int x) {
            return x - 1;
        }
    }

    private static volatile long sink;

    // Same invokeinterface call site in invoke's bytecode.
    static int invoke(Operation operation, int value) {
        return operation.apply(value);
    }

    static long phase(Operation operation) {
        long sum = 0;
        for (int i = 0; i < 100_000; i++) {
            sum += invoke(operation, i % 10);
        }
        return sum;
    }

    public static void main(String[] args) {
        Operation plus = new PlusTwo();
        Operation times = new TimesTwo();
        Operation minus = new MinusOne();

        long first = phase(plus);
        long second = phase(times);

        int a = invoke(plus, 10);
        int b = invoke(times, 10);
        int c = invoke(minus, 10);

        sink = first + second + a + b + c;

        System.out.println("first phase: " + first);
        System.out.println("second phase: " + second);
        System.out.println("plus(10): " + a);
        System.out.println("times(10): " + b);
        System.out.println("minus(10): " + c);
        System.out.println("checksum: " + sink);
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 DevirtualizationDemo.java
java DevirtualizationDemo
```

**Exact standard output (without JIT/GC logging enabled):**

```text
first phase: 650000
second phase: 900000
plus(10): 12
times(10): 20
minus(10): 9
checksum: 1550041
```

### Arithmetic Explanation

- In each `phase`, `i % 10` produces the sequence **0..9**, repeated for 10,000 cycles.
- `PlusTwo.apply(i % 10)` yields 2..11; the sum of one cycle is **65**; `first = 65 × 10,000 = 650,000`.
- `TimesTwo.apply(i % 10)` yields 0,2,...,18; the sum of one cycle is **90**; `second = 900,000`.
- `PlusTwo.apply(10) = 12`; `TimesTwo.apply(10) = 20`; `MinusOne.apply(10) = 9`.
- `checksum = 650,000 + 900,000 + 12 + 20 + 9 = 1,550,041`.
- The `volatile sink` field ensures the corresponding assignment and read have observable meaning; however, the compiler **can still perform many other valid optimizations**.

### What the Demo Proves and Does Not Prove

**Proves:**

- An **interface type** can have multiple valid implementations.
- The `invoke` method has the same source-level call site but produces results matching each runtime receiver type.
- One phase uses one implementation repeatedly; another phase uses a different implementation.
- Java semantics remain correct even as the JIT changes its dispatch strategy.

**Does not prove:**

- `invoke` was definitely compiled at C2 level 4.
- HotSpot definitely used CHA, a specific guard, or an uncommon trap.
- The JVM is required to go through monomorphic → bimorphic → megamorphic in exactly three stages.
- Another machine will print the same number of JIT compilation events.
- A short time measurement is proof of virtual call cost in production.

The computed result is **stable**, but whether the JIT devirtualizes/inlines/OSRs **depends on the runtime**, not something guessed from loop counts alone.

## 13. Inspecting Bytecode with javap

Run:

```bash
javap -c -p DevirtualizationDemo
```

Find the method `invoke(DevirtualizationDemo.Operation, int)` (how the full name is printed depends on `javap`). You will see the `Operation.apply` call represented by **`invokeinterface`**.

This confirms **the bytecode has dynamic-dispatch semantics**. It **does not** refute that C1/C2 generates direct/inlined machine code. `javap` reads the classfile; it **does not** read the code cache of a JVM that has run a method thousands of times.

### Opcode Comparison

In another Java class, if you have:

```java
static int twice(int x) {
    return x * 2;
}

static int callStatic() {
    return twice(10);
}
```

This is an illustrative method snippet in the same class. `callStatic` typically uses `invokestatic` because `twice` is static, with no receiver polymorphism. **Do not call that a devirtualization achievement**, because dynamic dispatch was never a requirement at this call site.

## 14. Observing HotSpot's Inlining Decisions

With HotSpot JDK 17 supporting diagnostic flags:

```bash
java -XX:+PrintCompilation DevirtualizationDemo
```

To also view inlining decisions:

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintCompilation -XX:+PrintInlining DevirtualizationDemo
```

The output can be **very long**: the JVM also compiles JDK library methods, and logging interleaves with `System.out.println`. Types of information you might look for:

```text
... DevirtualizationDemo::invoke ...
... DevirtualizationDemo$PlusTwo::apply ... inline (hot)
... TypeProfile (... receiver klass ...)
... virtual call ...
... made not entrant ...
```

**These are phrasing patterns, not fixed stdout, and not all lines are required to appear.** A run using only interpreter/C1 or another optimization plan may not have the corresponding lines.

### Explaining Common Indicators

| Log fragment | Hint, not a law |
| --- | --- |
| `inline (hot)` | The JIT decided to inline a target in the printed compilation context |
| `TypeProfile` / receiver class info | The compiler is using/displaying runtime type information at a location |
| `virtual call` | The call site may not have been inlined or the dispatch path remains generic |
| `made not entrant` | An nmethod no longer accepts new entries according to VM state |
| `made zombie` | An internal state in the compiled code lifecycle |
| Compilation level 3/4 | Corresponding tiered JIT level if the log format includes levels |
| `%` in `PrintCompilation` | Typically related to OSR compilation |

**Caution:** `PrintInlining` records the decision **at the time a version is compiled**, not a complete history of all receiver types ever called across every JVM state. A method can be recompiled multiple times.

### Why Does Output Vary?

- Tiered policy chooses a different compiler level.
- Different JVM version/hardware/compiler flags.
- C1/C2 compilation queue is busy.
- Code cache is full or compiler policy is constrained.
- Workload is not hot enough or caller/callee were optimized together.
- Different class loading, receiver profile, and timing.
- Startup classes/JDK library methods get compiled first, interleaving into the log.

**Do not use “the log must contain inline (hot)” as a mandatory unit test for source code**. To benchmark, measure results/throughput/latency with appropriate tools.

## 15. Running Modes to Distinguish Bytecode and JIT

Try the following commands in **separate JVM processes**:

```bash
java -Xint DevirtualizationDemo
java -XX:TieredStopAtLevel=1 DevirtualizationDemo
java -XX:+PrintCompilation DevirtualizationDemo
java -XX:-TieredCompilation -XX:+PrintCompilation DevirtualizationDemo
```

- `-Xint` selects a primarily **interpreter-only mode for Java methods**, useful as a correctness baseline; usually slow for compute workloads.
- `TieredStopAtLevel=1` caps the compilation level in HotSpot's tiered policy, without forcing every cold method to compile.
- `PrintCompilation` helps observe compilation events.
- `-XX:-TieredCompilation` changes the **JIT compilation policy**; it does **not** mean disabling JIT like `-Xint`.

**Across all four runs**, if the JVM supports the flags and the program completes normally, the computed output **must match** section 12. The number of JIT events, compiler decisions, and speed will differ.

### Disabling Inlining Does Not Prove All Devirtualization Is Disabled

HotSpot has `-XX:-Inline` to adjust inlining on supported builds. However, **devirtualization and inlining are two different things**. Disabling inline does not necessarily force every call site back to generic interface dispatch: the VM may still know the target and call it directly.

Do not use `-XX:-Inline` in production as a “polymorphism fix” without profiler and benchmark evidence. The flag broadly interferes with JIT optimizations.

## 16. Detailed JIT Compilation Logs and Machine Code Diagnostics

If deeper evidence is needed (and creating log files is permitted in the test environment):

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+LogCompilation -XX:LogFile=jit-devirt.xml DevirtualizationDemo
```

HotSpot can write JIT logs in XML format for analysis, rather than compact stdout like `PrintCompilation`. The level of detail, event names, and reader tools depend on the JDK version. Some events relate to `uncommon_trap`, inlining, type profile, or dependencies; **do not claim every logged event is an actual runtime deoptimization** without distinguishing parse/compile/runtime actions.

### Printing Assembly

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintAssembly DevirtualizationDemo
```

Depends on **hsdis** matching the JDK/OS/architecture and diagnostic setup. Without a disassembler, you may not see machine instructions even though the JIT compiled normally. Assembly can also be very long; use it on an isolated test process or with appropriate analysis tools.

### jcmd for Running Processes

```bash
jcmd -l
jcmd PID help
jcmd PID Compiler.queue
jcmd PID Compiler.codelist
jcmd PID Compiler.codecache
```

Replace `PID` with the actual process ID; do not type the literal placeholder. The demo program may finish too quickly to attach; to view live JIT state, use a service or a test process that stays alive long enough. `jcmd` only has the commands supported by the binary and requires appropriate attach permissions.

**These commands do not directly say “method X used CHA”**; they provide compile/code cache context, which must be combined with logs/assembly if you want to know actual devirtualization.

## 17. Interface Calls in Real-World Code: Do Not Jump to Conclusions Too Early

Codebases use interface polymorphism extensively:

- Service interfaces and dependency injection.
- Strategy/State/Command patterns.
- Plugin APIs with runtime-loaded implementations.
- Collections and iterators through interfaces.
- Logger interfaces, adapters, and generated proxies.
- ORM/session abstractions, proxy subclasses.
- Lambdas/method references via functional interfaces.

**Common misconception:** “Java interfaces are always slow because of virtual calls”. HotSpot has very strong type profiling/CHA/inlining; an interface callsite with a stable receiver type can be optimized close to direct/static code.

**Opposite misconception:** “The JIT can always optimize every interface call”. A truly megamorphic site, large targets, code cache pressure, warm-up latency, or complex class loading can prevent/alter optimization.

### Framework Proxies Can Change the Types at a Callsite

A codebase has many decorators/proxies that differ in the actual runtime classes received. For example:

```text
Service s = JDK dynamic proxy
or
Service s = concrete implementation
```

This is a **model**, not complete Java source. Depending on where the caller receives the reference, the type profile may see a concrete class, a proxy class, or multiple classes. That affects the ability to inline each dispatch path. However, **do not automatically infer that having a proxy makes inlining impossible**.

### Code Structure Optimization Should Be Goal-Driven

- Prioritize **API clarity, testability, and correct polymorphism**.
- Avoid manually replacing every interface with `switch(instanceof)` just to “help the JIT”.
- For a genuine hot path, profile first, identify the type distribution, and measure the cost.
- If a polymorphic site is a bottleneck, consider reducing the number of target types, separating callsites by business path, or making exact type dataflow clearer **while preserving proper design**.
- Benchmark end-to-end and use properly designed microbenchmarks when isolated cost verification is needed.

## 18. Compiler Assumptions Are Also Subject to Other Semantic Constraints

### Null Receiver

```java
Payment p = null;
p.calculate(10);
```

This is a snippet inside a method, which will throw `NullPointerException` when executing the instance call. If the JIT inlines/eliminates dispatch, **it must still preserve the appropriate exception result**, even when the null check is implicit or combined with another check.

### Side Effects, Exceptions, and Locks

The callee may:

- Write a `volatile` field.
- Execute `synchronized`.
- Throw checked/unchecked exceptions.
- Touch class initialization/field access.
- Call a native method.
- Perform I/O, update shared data.

The call target may be inlined or called directly, but the Java Memory Model and observable behavior **are not exempted**. The compiler must not turn an interface call with side effects into a non-equivalent operation.

### Class Loader Identity and Visibility

Two classes with the same binary name but from different defining class loaders can be different runtime types. CHA/type profiles work with **runtime class identity/metadata**, not by comparing class name strings and treating them as the same target.

### Linkage Exceptions

`invokevirtual`/`invokeinterface` are also subject to the JVM's resolution/linking rules. The JIT must preserve valid semantics when method resolution or class loading leads to linkage errors under the JVM Specification. It must not “guess” a target and skip all required checks.

## 19. How Do Devirtualization and Escape Analysis Relate?

**Devirtualization** identifies the target; **inlining** brings the callee into the caller; then **escape analysis** and other optimizations can see more facts.

```text
Virtual/interface call
    │
    ▼
JIT proves or predicts target (devirtualization)
    │
    ▼
Inline implementation if worthwhile
    │
    ▼
Can see allocations/field accesses across methods
    │
    ▼
Escape analysis / scalar replacement / constant folding
    │
    ▼
Fewer calls / fewer allocations / fewer loads on the appropriate path
```

This **does not** mean “devirtualization automatically eliminates all object allocations”. Escape analysis depends on whether the object escapes, aliasing, safepoints, exceptions, intrinsics, size/budget, and JIT policy. An allocation in source may still remain on the heap.

**Practical benefit:** sometimes saving the dispatch call is only a small part; the larger value is opening the path to optimize an entire computation chain across multiple methods.

## 20. Performance: Do Not Infer Directly from the Number of Virtual Calls

A site with 1 million virtual calls is not necessarily a bottleneck. CPU cost depends on:

- Is the target method hundreds of times larger than the dispatch overhead?
- Can the branch predictor predict the patterns of receiver types?
- Has the call site been JIT-inlined on the hot path?
- Instruction cache footprint after inlining.
- Code cache occupancy and compilation overhead.
- Different ratios of receiver types in production.
- GC/allocation pressure and cache locality.
- JVM warm-up/OSR/deoptimization frequency.
- CPU architecture, frequency scaling, container throttling.

### Benchmarks Are More Reliable Than “Inlining Folklore”

For microbenchmarks, use **JMH** or an equivalent harness to control warm-up, forks, observable results (avoiding dead-code elimination), inputs, and JVM flags. For services, measure **throughput, p50/p95/p99 latency, and CPU profiles** under real conditions.

A case where JIT devirtualization helps greatly in a microbenchmark may have little impact on end-to-end latency if most of the time is spent in network I/O/database. Do not change an entire public API to concrete classes just because you saw `invokeinterface` once in `javap`.

### Warm-Up Can Change Receiver Distribution

If during warm-up you only use `MockPayment` while production uses `StandardPayment`, the compiler may optimize for a non-representative profile. When production changes the distribution, you may see guard failures/deopt/recompile and initial load-hour speed differing from expectations.

Reasonable warm-up should reflect **the important shapes/receiver types of production**, but still needs to be confirmed with metrics rather than hard-coding a fixed number of calls.

## 21. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| “`invokeinterface` is always slower than `invokestatic`.” | The JIT can devirtualize/inline interface calls when enough evidence exists; performance depends on the path |
| “Devirtualization and inlining are the same thing.” | One determines the callee, the other places code into the caller |
| “Having an interface means it cannot be inlined.” | The runtime profile can be monomorphic |
| “An interface has 20 implementations so every site is megamorphic.” | Polymorphism is evaluated **per call site** |
| “Monomorphic means the interface has exactly one implementation in source.” | A site may only **observe** one type even with a large hierarchy |
| “CHA sees one target so the assumption stays true forever.” | Dynamic class loading can invalidate the dependency, requiring deopt/invalidation |
| “A `final` class always makes code faster.” | Helps determine the target, but the compiler does not guarantee inlining/perf wins |
| “`sealed` guarantees only one runtime target.” | Can permit multiple concrete subclasses |
| “A guard failure makes the JIT dispatch to the wrong method.” | The JVM must dispatch/fallback/deopt properly per semantics |
| “Deopt is a crash or exception.” | It is a runtime mechanism to transition back to general execution |
| “`javap -c` proves the JIT did not eliminate dispatch.” | `javap` only displays class file bytecode |
| “`PrintInlining` having no output means the JIT is not working.” | Logs/flags/workload/version may not be suitable |
| “C2 always devirtualizes every hot call.” | Profile, budget, method size, code cache, and policy are limits |
| “Dynamic proxy prevents JIT optimization everywhere.” | Need to observe the specific receiver profile |
| “Disabling inlining means disabling devirtualization.” | The two optimizations are not identical |
| “Every time the JVM sees a new type it definitely deopts.” | There may be a fallback/guarded path without needing to deopt |
| “A callee with side effects can still be arbitrarily eliminated after inlining.” | Observable Java semantics must be preserved |
| “Reading Class.getName() is enough to know class identity.” | Different class loaders can create different runtime types |
| “JIT decisions are based only on source-code keywords.” | Runtime types/profiles/hierarchy/flags/CPU all have an effect |
| “Benchmarking once after startup measures steady state.” | Warm-up and recompilation create multiple different performance phases |

## 22. Exercises with Solutions

### Exercise 1 — Dispatch by Runtime Receiver

Given `Payment p = new StandardPayment();` and `p.calculate(10)` per the definition in section 1.  
**Answer:** **12**. The variable type `Payment` does not determine a specific method implementation apart from the runtime receiver type.

### Exercise 2 — Changing Receiver

If `p = new PremiumPayment()` is assigned and then `p.calculate(10)` is called?  
**Answer:** **20**. The JVM must preserve dynamic dispatch; the JIT must not force calling StandardPayment's method if the runtime type differs.

### Exercise 3 — Devirtualization vs. Inlining

The JIT knows the target `StandardPayment.calculate` but does not inline because the method is too large. Can this be called devirtualization?  
**Answer:** Yes, it can. If dynamic dispatch is eliminated into a direct call, it has been devirtualized, even though a call boundary remains.

### Exercise 4 — Large Interface but Site Has Only One Type

An interface has 12 concrete implementations. A hot call site only receives one implementation. Is that site automatically megamorphic?  
**Answer:** No. Type profiling at the call site can be monomorphic.

### Exercise 5 — Two Sites with the Same Signature

One site only receives `StandardPayment`; another site receives both Standard and Premium. Must the JVM optimize them identically?  
**Answer:** No. Callsite profiles and optimization contexts differ.

### Exercise 6 — Final Class

Why does a `final` class help the JIT deduce the target?  
**Answer:** It cannot have subclasses, reducing the possibility of method overriding; however, it does not guarantee inlining.

### Exercise 7 — Sealed Hierarchy

A `sealed interface` has two permitted final implementations. Is there definitely one target for every interface call?  
**Answer:** No. A site can receive both implementations.

### Exercise 8 — CHA and Class Loading

CHA optimized for a single concrete target and then a new subclass is loaded. Can the old code be kept without checking?  
**Answer:** No, if the compiled assumption depends on a hierarchy that is no longer valid. HotSpot must manage dependencies/invalidation/deoptimization or another mechanism to ensure semantics.

### Exercise 9 — What Risk Does Type Profiling Have?

Warm-up is entirely type A, real traffic switches to type B.  
**Answer:** Guard miss, fallback, or deopt/recompile can occur; a profile is not a promise that future inputs only contain A.

### Exercise 10 — Purpose of a Guard

If the JIT only inlines path A, why is a class/type guard needed in the speculative case?  
**Answer:** So that an execution path receiving B does not mistakenly run method A, preserving dynamic dispatch.

### Exercise 11 — Null

If the receiver is `null` and the JIT inlines the target, can it return a default number instead of an error?  
**Answer:** No. It must preserve `NullPointerException` per JVM rules.

### Exercise 12 — Opcode

`javap -c` shows `invokeinterface`. Does that mean the CPU must perform an interface lookup on every call?  
**Answer:** No. The HotSpot JIT can devirtualize/inline the machine code.

### Exercise 13 — Static Call

Is it reasonable to call `invokestatic` “devirtualization” after JIT?  
**Answer:** Not in the sense being discussed; a static call does not require receiver virtual dispatch.

### Exercise 14 — Machine Code No Longer Used

If code is `made not entrant`, does that prove the JVM made a mistake?  
**Answer:** No. That can be a normal part of the nmethod lifecycle, deoptimization/recompilation.

### Exercise 15 — Multiple Compiled Versions of the Same Method

Can a method have different JIT versions over time?  
**Answer:** Yes. C1/C2 levels, type profiles, OSR, deopt, and recompilation affect compiled code.

### Exercise 16 — `DevirtualizationDemo` Data

Value of `first phase` in the section 12 demo?  
**Answer:** **650000**, because each cycle 0..9 plus 2 sums to 65, and there are 10,000 cycles.

### Exercise 17 — Second Phase

Value of `second phase`?  
**Answer:** **900000**, because twice the sum of 0..9 = 90 for one cycle, repeated 10,000 times.

### Exercise 18 — Checksum

Final value of `sink`?  
**Answer:** **1550041 = 650000 + 900000 + 12 + 20 + 9**.

### Exercise 19 — Not Seeing Inline Logs

The JVM did not print `inline (hot)` during a run of the demo. Does that prove HotSpot does not support devirtualization?  
**Answer:** No. JIT level, hotness, compiler flags, logging, and runtime policy may differ.

### Exercise 20 — Disabling `-XX:-Inline`

Does this guarantee every callsite retains generic virtual dispatch?  
**Answer:** No. Disabling inline differs from disabling devirtualization; the VM can direct call without inlining.

### Exercise 21 — Reflection and Class Loaders

Can two classes with the same name but defined by two different class loaders be considered the same runtime klass because the name is identical?  
**Answer:** No. Runtime class identity is tied to the defining loader, not just the binary name.

### Exercise 22 — API Optimization

Should all interfaces be changed to concrete classes just because a small benchmark shows virtual call overhead?  
**Answer:** Not by default. Measure the workload, identify bottlenecks, check compiler logs, and evaluate design costs before changing the API.

## 23. Checklist for Investigating a Hot Virtual Call

- [ ] Identify the exact **bytecode call site** using `javap -c` and JIT context, not just the method name.
- [ ] Distinguish between `invokevirtual`/`invokeinterface`/`invokestatic`/`invokespecial` opcodes.
- [ ] Know which receiver **runtime types** actually appear at the site?
- [ ] Is the site monomorphic, a few types, or megamorphic under real workload?
- [ ] What is the current class hierarchy and likelihood of dynamic class loading?
- [ ] Does the method/class have `final`, exact type, or sealed constraints?
- [ ] Know whether the optimized assumption is based on CHA or type profile (if logs suffice)?
- [ ] Did the JIT generate guards, direct call, inline, or generic dispatch?
- [ ] Could class loading invalidation/deoptimization occur?
- [ ] Have code/branch/exception semantics been verified after optimization?
- [ ] Did you separate devirtualization from method inlining and escape analysis?
- [ ] Have you checked the effect of `TieredCompilation` and JIT flags?
- [ ] Have you observed `PrintCompilation`, `PrintInlining` in a test environment?
- [ ] Have you checked the code cache/compile queue if C2 compilation is slow?
- [ ] Have you compared performance after warm-up as well as right at startup?
- [ ] Does the benchmark have sufficient warm-up, forks, and avoid dead-code elimination?
- [ ] Does the diagnosis consider CPU, GC, allocations, I/O instead of only virtual calls?
- [ ] Are you avoiding turning JIT implementation details into Java API correctness conditions?

## 24. Summary

**Devirtualization** leverages information about the **runtime receiver type** to avoid the cost of generic dynamic dispatch on a hot path. **CHA** uses the class hierarchy and compiled dependencies; **type profiling** uses the concrete types appearing at each call site. **Exact type/final semantics** allow stronger proofs; **speculative assumptions** require guarded paths, fallback, or deoptimization when inputs/class hierarchy change.

When devirtualization yields a concrete target, HotSpot can **inline** and optimize across methods; however, **eliminating dispatch ≠ inline**, and no compiler is required to optimize every site in every situation. Dynamic class loading, polymorphism, null receivers, exception ordering, and the Java Memory Model set boundaries that optimized machine code **must not cross**.

### References

- **Java Virtual Machine Specification (Java SE 17), §2.11.8 Method Invocation and Return Instructions:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.11.8
- **Java Virtual Machine Specification (Java SE 17), Chapter 6 Instruction Set:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html
- **Oracle JDK 17 — `java` command, `PrintCompilation` / `PrintInlining` / compiler controls:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **OpenJDK HotSpot — Optimizations in HotSpot JVM** (class hierarchy analysis, devirtualization, type speculation): https://cr.openjdk.org/~vlivanov/talks/2015_JIT_Overview.pdf
- **OpenJDK HotSpot C2 — `doCall.cpp`** (guarded call, CHA target, type profile, virtual/direct call decisions; source varies by release): https://github.com/openjdk/jdk/blob/jdk-17%2B35/src/hotspot/share/opto/doCall.cpp
- **OpenJDK — Integrating Profile Caching into the HotSpot Multi-Tier Compilation System** (runtime profiling, deoptimization and class hierarchy changes): https://cr.openjdk.org/~thartmann/papers/2017-ManLang-Profile_Caching.pdf
- **Java SE 17 — JLS `8.4.3.3 Final Methods and `8.1.1.2 Final Classes:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html
- **OpenJDK JEP 197 — Segmented Code Cache:** https://openjdk.org/jeps/197/

**Final message:** do not fear interfaces because of an `invokeinterface` opcode, nor assume C2 will always turn every virtual call into a direct inline. **Measure the profile of the call site itself, check compiler decisions on the right HotSpot/JDK, and always maintain the boundary between optimization assumptions and mandatory Java semantics.**