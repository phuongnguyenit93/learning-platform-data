# Inserting Helper Calls Instead of Rewriting the Entire Application Algorithm

In Java instrumentation, we often only need to add a measurement point to a compiled program: counting API calls, recording an event, starting a span, or collecting metrics before an invocation. **The safe approach in terms of modification scope is to insert a call to a helper and preserve most of the original bytecode**, rather than rewriting the entire business algorithm yourself.

With the Class-File API, we can parse a class file, enter the method body using `ClassTransform`, emit a helper call in `CodeTransform`, and forward the original instruction via `builder.with(element)`. This lesson goes from the operand stack to an executable demo and the conditions for use in a Java agent.

**Version:** The standard `java.lang.classfile` API is finalized in **JDK 24** (JEP 484), following preview versions in JDK 22/23. Therefore, the transformation tool in this lesson **requires JDK 24+** and cannot be compiled with Java 17/21. The sample application class uses standard Java syntax, while the demo commands consistently use JDK 24+ to ensure the Class-File API library is present.

## 1. Problem: Needing a Hook Without Changing the Business Logic

Consider the application class:

~~~java
public static int compute(int x) {
    int positive = Math.abs(x);
    return Math.max(positive, 10);
}
~~~

We want to know when the method calls `Math.abs` or `Math.max`. Conceptually, the bytecode after insertion is equivalent to:

~~~java
public static int compute(int x) {
    Probe.onCall("abs");
    int positive = Math.abs(x);
    Probe.onCall("max");
    return Math.max(positive, 10);
}
~~~

This is an **illustrative interpretation for learning**: the tool does not edit the Java source file, but modifies the bytecode instructions in the `.class` file. The important point is that the original call still exists and is still executed after the helper. If the input is `-7`, the business result is still `10`, provided the helper does not break the execution path.

A transformer that rebuilds the entire method body risks dropping `if` branches, loops, `try/finally`, exception handlers, monitors, local slots, labels, or stack-map frames. Inserting a small call makes the scope of change clearer and easier to inspect with `javap`, the JVM verifier, and business tests. **Smaller does not mean completely harmless**: a helper can cause class loading, runtime errors, lock contention, and overhead, so it still must be evaluated.

## 2. Model Layers of the Class-File API

~~~text
Sample.class (byte[])
     |
     v
ClassFile.of().parse(...)  -> ClassModel
     |
     v
ClassTransform
     |-- other fields/attributes/methods: kept unchanged
     |
     +-- method compute
             |
             v
          CodeTransform
             |-- when encountering InvokeInstruction:
             |      add ldc for call name
             |      add invokestatic Probe.onCall
             |-- builder.with(element): keep original CodeElement
     |
     v
ClassFile.transformClass(...) -> new byte[]
~~~

| Component | Responsibility |
| --- | --- |
| `ClassFile.of()` | Service for reading, building, and transforming class files |
| `ClassFile.parse(byte[])` | Reads bytes into a `ClassModel`, with parts parsed on demand |
| `ClassModel` | Class structure: fields, methods, attributes |
| `MethodModel` | Method name, descriptor, and Code |
| `ClassTransform` | Transforms class elements, selects methods to modify |
| `CodeTransform` | Processes code elements sequentially within a method |
| `CodeBuilder` | Emits new instructions and forwards old elements |
| `InvokeInstruction` | Model of a method invocation in bytecode |
| `ClassDesc` | Describes the helper class name without loading the class into the tool |
| `MethodTypeDesc` | Describes the JVM signature of the helper |
| `ClassFile.transformClass` | Rebuilds class bytes from the model and transform |

At the insertion point, the core pattern is:

~~~java
CodeTransform transform = (builder, element) -> {
    if (element instanceof InvokeInstruction call) {
        // Insert helper instructions before the original call.
    }
    builder.with(element); // Keep the original element.
};
~~~

The snippet above is only an **illustrative code fragment**, not standalone runnable code; `builder.with(element)` is of key importance. If you do not forward the original element, the builder may **drop that element from the new file**. When that element is the very invocation you want to observe, you have accidentally deleted the original computation.

## 3. The Operand Stack and Why the Helper Call Does Not Consume Arguments

JVM bytecode uses an operand stack. `Math.abs(int)` has descriptor `(I)I`, meaning it pops one `int` and returns one `int`:

~~~text
Before Math.abs:
    stack [ x:int ]
    invokestatic java/lang/Math.abs (I)I
    stack [ abs(x):int ]
~~~

Helper design:

~~~java
public static void onCall(String method)
~~~

The descriptor is `(Ljava/lang/String;)V`: it pops exactly one `String` and returns `void`. Bytecode inserted before `Math.abs`:

~~~text
    stack [ x:int ]
    ldc "abs"
    stack [ x:int, "abs":String ]
    invokestatic Probe.onCall (Ljava/lang/String;)V
    stack [ x:int ]
    invokestatic java/lang/Math.abs (I)I
    stack [ abs(x):int ]
~~~

The helper only consumes the newly pushed string on top; `x` remains on the stack for the original invocation to use. Similarly, before `Math.max(int,int)`, the two operands are already present and remain in their exact positions when the helper returns `void`.

If the helper returns an object or a `long` that the builder does not handle, the stack will have leftover values. If the signature in the constant pool does not match the actual helper code, the verifier or linker may report an error. And even if the stack is valid, **a helper throwing an exception will prevent the original invocation from running**. Both **bytecode correctness** and **business semantics** must be verified.

## 4. Common Insertion Points

| Location | What Is Observed | Limitations |
| --- | --- | --- |
| Before `InvokeInstruction` | Execution path reached the call site | Does not prove the original call succeeded |
| After invocation | Invocation returned normally | Does not run if the invocation throws an error |
| Method entry | Method execution started | Constructors have an uninitialized `this` state |
| Before return | Normal return occurred | Does not automatically cover exceptional exits |
| Before explicit `athrow` | Explicit throw instruction executed | Does not cover all exceptions thrown inside other calls |
| Wrapping the entire method like `finally` | Measures both normal and exception exits | Requires modifying labels, handlers, frames, and preserving the original exception |

The practical example chooses **before invocation** because it only needs to emit `ldc` then `invokestatic`, without having to rearrange return values or rebuild the exception table. Do not assume that merely adding hooks at `return` is a full replacement for `finally`.

## 5. JDK 24+ Demo: Three Java Files

Place the three files below in **a separate test directory**, using JDK 24 or later. Do not use Maven/Gradle, ASM, or Byte Buddy. This is an **offline class-file transformer**: it transforms a class file on disk for easy inspection. A later section explains hooking into a Java agent.

### 5.1. File `Sample.java`

~~~java
public final class Sample {
    public static int compute(int x) {
        int positive = Math.abs(x);
        return Math.max(positive, 10);
    }

    public static void main(String[] args) {
        System.out.println("RESULT=" + compute(-7));
    }
}
~~~

### 5.2. File `Probe.java`

~~~java
public final class Probe {
    public static void onCall(String name) {
        System.out.println("HOOK_BEFORE=" + name);
    }
}
~~~

`System.out.println` helps learners see the output. Production helpers should minimize I/O, allocations, locks, and exceptions; typically they only update a counter or a bounded queue and let a reporter process it off the hot path.

### 5.3. File `InjectHelper.java`

~~~java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassTransform;
import java.lang.classfile.CodeTransform;
import java.lang.classfile.instruction.InvokeInstruction;
import java.lang.constant.ClassDesc;
import java.lang.constant.MethodTypeDesc;
import java.nio.file.Files;
import java.nio.file.Path;

public final class InjectHelper {
    private static final ClassDesc PROBE = ClassDesc.of("Probe");
    private static final MethodTypeDesc PROBE_TYPE =
            MethodTypeDesc.ofDescriptor("(Ljava/lang/String;)V");

    public static void main(String[] args) throws Exception {
        Path input = Path.of("Sample.class");
        byte[] original = Files.readAllBytes(input);
        ClassFile classFile = ClassFile.of();

        CodeTransform insertHelper = (builder, element) -> {
            if (element instanceof InvokeInstruction call) {
                builder.ldc(call.name().stringValue())
                       .invokestatic(PROBE, "onCall", PROBE_TYPE);
            }
            builder.with(element);
        };

        ClassTransform selectedMethods =
                ClassTransform.transformingMethodBodies(
                        method -> method.methodName().equalsString("compute"),
                        insertHelper);

        byte[] changed = classFile.transformClass(
                classFile.parse(original), selectedMethods);

        Files.write(input, changed);
        System.out.println("PATCHED=Sample.class");
    }
}
~~~

**Explanation:**

1. `ClassDesc.of("Probe")` describes the helper class name in bytecode. It does not load `Probe` in the tool's JVM.
2. `MethodTypeDesc.ofDescriptor("(Ljava/lang/String;)V")` is the signature of `Probe.onCall(String)` returning `void`.
3. `ClassFile.of().parse(original)` takes the source bytes and creates a `ClassModel`.
4. `ClassTransform.transformingMethodBodies` only enters the body of the method named `compute`; the rest of the class is forwarded unchanged.
5. `CodeTransform` emits `ldc` for the called method name and `invokestatic Probe.onCall` **before** the current `InvokeInstruction`.
6. `builder.with(element)` keeps the original instruction immediately after the hook. Thus both `Math.abs` and `Math.max` calls remain intact.
7. `transformClass` produces the new bytecode; `Files.write` writes `Sample.class` back into the demo directory.

The method in the example has only one `compute` overload; if there are other overloads, you must also match the method descriptor. Similarly, if the body of `compute` contains additional invocations, the tool will instrument those new invocations as well: this is **intentional behavior for the demo**, but in a real application you must filter more strictly.

### 5.4. Compile and Run

~~~bash
javac --release 24 Sample.java Probe.java InjectHelper.java
~~~

`javac` must belong to JDK 24+ and support the `--release 24` target. A JDK 17/21 compiler will report that `java.lang.classfile` is missing; that is a version constraint, not an import error.

Run the untransformed version:

~~~bash
java Sample
~~~

Standard output:

~~~text
RESULT=10
~~~

Run the tool to patch `Sample.class`:

~~~bash
java InjectHelper
~~~

Standard output:

~~~text
PATCHED=Sample.class
~~~

Then run the application again:

~~~bash
java Sample
~~~

Standard output from the print statements in the demo:

~~~text
HOOK_BEFORE=abs
HOOK_BEFORE=max
RESULT=10
~~~

The two hooks run before the two original invocations; the computation still returns `10` for the tested input. This is a result **inferred from the code and API contract**, not proof of testing on every machine. When using a different JDK/loader/classpath, run it in practice to verify.

**Note:** `InjectHelper` overwrites the class file **in the demo directory**. If you run the tool again without recompiling `Sample.java`, it may insert hooks before the `Probe.onCall` calls created on the first run. To retest, recompile the original class before each patch, or modify the tool to keep the input immutable and write output to a separate directory.

### 5.5. Inspect Bytecode and Verify Validity

~~~bash
javap -c -p Sample
~~~

In the `compute` method, you can see the logical order (abbreviated version, **not verbatim javap output**):

~~~text
ldc           "abs"
invokestatic  Probe.onCall:(Ljava/lang/String;)V
invokestatic  java/lang/Math.abs:(I)I
...
ldc           "max"
invokestatic  Probe.onCall:(Ljava/lang/String;)V
invokestatic  java/lang/Math.max:(II)I
...
ireturn
~~~

Offsets, constant pool indices, and load/store opcodes may differ, but the original calls must remain after the hooks. `Sample.java` remains untouched; only `Sample.class` is modified.

A runtime check:

~~~bash
java -Xverify:all Sample
~~~

If the class is valid, the JVM loads and executes it; the output still contains the three lines above. `ClassFile` also provides `verify(byte[])` to check and collect a list of errors before writing. However, the verifier **does not confirm** that the hook does not alter exceptions, latency, or business behavior on unexecuted branches.

## 6. Why Must the Original Element Be Forwarded?

When a transformer receives a `CodeElement`, the builder must be given an explicit decision: **keep, drop, modify, or add**. In an insert-only technique, the code is typically:

~~~java
CodeTransform correct = (builder, element) -> {
    if (element instanceof InvokeInstruction call) {
        builder.ldc(call.name().stringValue())
               .invokestatic(PROBE, "onCall", PROBE_TYPE);
    }
    builder.with(element);
};
~~~

Compare this with an **intentionally broken** version:

~~~java
CodeTransform broken = (builder, element) -> {
    if (element instanceof InvokeInstruction call) {
        builder.ldc(call.name().stringValue())
               .invokestatic(PROBE, "onCall", PROBE_TYPE);
        // Forgot builder.with(element): the original call is lost.
    } else {
        builder.with(element);
    }
};
~~~

In the broken version, an original `Math.abs` call can be dropped, causing the bytecode to no longer return the right value or corrupting the stack. Other elements such as load/store, labels, branches, and exception metadata also need to be preserved unless you are performing an explicitly designed transformation. The Class-File API has an efficient transform/copy mechanism for unchanged parts; there is no need to rewrite loops, `if` statements, or the entire method body just to insert a call.

## 7. Filtering Call Sites by Owner/Name/Type

Filtering the enclosing method by the name `compute` is only one layer. In production, you also need to filter **the specific call**:

~~~java
// Snippet inside CodeTransform where PROBE and PROBE_TYPE are already defined.
if (element instanceof InvokeInstruction call
        && call.owner().asInternalName().equals("java/lang/Math")
        && call.name().equalsString("abs")
        && call.typeSymbol().descriptorString().equals("(I)I")) {
    builder.ldc("abs")
           .invokestatic(PROBE, "onCall", PROBE_TYPE);
}
builder.with(element);
~~~

This snippet only attaches a hook before `Math.abs(int)`. It does not match `Math.abs(long)`, `Math.max`, or another class with a method of the same name. Values to understand:

- `owner().asInternalName()` uses `/` slashes in the JVM internal name.
- `name().equalsString(...)` compares the method name in the constant pool.
- `typeSymbol().descriptorString()` distinguishes overloads; `(I)I` means int → int.
- `opcode()` can check `INVOKESTATIC`/`INVOKEVIRTUAL`/`INVOKEINTERFACE`/`INVOKESPECIAL` when needed.
- `invokedynamic` is a separate case; not every invocation in source becomes an `InvokeInstruction`.

When a class has both `compute(int)` and `compute(String)`, you need to add the method descriptor to the predicate of `ClassTransform.transformingMethodBodies` so you do not instrument both. Reading the actual bytecode with `javap` before finalizing the filter is a good verification practice.

## 8. Designing a JVM-Compliant Helper Contract

A bytecode call requires:

~~~text
opcode      INVOKESTATIC
owner       Probe
name        onCall
descriptor  (Ljava/lang/String;)V
~~~

`ClassDesc` describes the owner class, and `MethodTypeDesc` describes the parameters/return type. If the bytecode says the helper is static but at runtime there is only an instance method, you may encounter `IncompatibleClassChangeError`; if the method signature is missing, you may encounter `NoSuchMethodError`; if the helper class is not present at runtime, you may encounter `NoClassDefFoundError`. These errors are not necessarily detected when an offline tool only writes the class file.

A production helper should be a small static API that does not hold long-lived `ClassLoader`/`Class<?>` references, does not traverse business data, does not send network requests synchronously, and has a telemetry error-handling policy. If the helper needs to read context, it must close the scope on the right branch and avoid context leaks in thread pools.

The helper example using `println` is for learning only. When called in a real application, a helper can run millions of times; CPU cost, allocation, contention, GC, and I/O can all degrade performance even if the computation result stays the same.

## 9. Integrating `ClassFileTransformer` in a Java Agent

The offline demo reads bytes with `Files.readAllBytes` and writes output with `Files.write`. In an agent, the JVM passes `classfileBuffer` to the callback, and the callback returns the new `byte[]`:

~~~text
OFFLINE: class bytes -> ClassFile.parse -> transformClass -> Files.write
AGENT:   classfileBuffer -> ClassFile.parse -> transformClass -> return bytes
~~~

This conceptual snippet sits **inside a transform(...) method**, where `classFile`, `selectedTransform`, and `failures` are already initialized:

~~~java
if (!"demo/app/Sample".equals(className)) {
    return null;
}
try {
    return classFile.transformClass(
            classFile.parse(classfileBuffer), selectedTransform);
} catch (RuntimeException ex) {
    failures.incrementAndGet();
    return null;
}
~~~

`return null` under the `ClassFileTransformer` contract means **do not modify the bytecode on this pass**. It differs from `builder.with(element)` in `CodeTransform`, which means forwarding an element while building new bytecode.

The catch-and-return-null policy in the snippet is **best-effort**: if instrumentation is mandatory for correctness/security, there must be an explicit failure policy rather than silently swallowing errors. The running agent must be on a JVM with the standard Class-File API (JDK 24+ for the sample code). If the agent must support a JDK 17 JVM, you must use a different suitable transformation tool or a different build/offline architecture.

Safety points for the callback:

1. Filter `className` early, remembering that it can be null.
2. Initialize helpers, parsers, and filter data before registering the transformer.
3. Do not use `Class.forName` to force-load the very class currently being defined by the JVM.
4. Do not log, acquire heavy locks, or export synchronously inside the class-loading callback.
5. Exclude the agent's own packages/helpers to avoid self-instrumentation.
6. Check support and limitations for retransform/redefine if applied after classes are already loaded.

## 10. Idempotence and Chained Transforms

If a transform runs again on already-patched bytes, hooks will be **duplicated** unless there is a guard. Preventive techniques:

- Always transform from immutable original artifacts and write separate outputs with checksums.
- Exclude invocations to the helper itself, while knowing this **does not prevent** adding a second hook before the original invocation.
- Use an idempotence marker or recognize the exact instruction pattern by owner/name/descriptor.
- Avoid registering the same transformer multiple times; check when the agent has multiple composition layers.
- If using `andThen`, remember that the later transform can receive the very instructions emitted by the earlier transform.

With JVM retransformation, the input bytecode and transformer order depend on the JVM/registration mechanism. Do not assume every retransform pass starts from the exact original `.class` file or already has hooks; test on a real JVM and write anti-duplication tests.

## 11. Class Loaders and Modules as Real-World Runtime Conditions

In the demo, `Probe.class` and `Sample.class` are on the same classpath, so linking is easy. In real systems:

- The target may be in a custom/plugin/webapp class loader, while the helper is in another loader that is not visible.
- Classes loaded by the bootstrap loader cannot automatically see helpers that only exist in the agent JAR on the system loader.
- Named modules have readability/exports constraints and are not automatically opened just by using `ClassDesc.of(...)`.
- Hot redeploys can create many class loaders; caching strong references to helpers/agents can cause leaks.
- Re-instrumenting helpers or logging/exporters can cause recursion, lock cycles, or metric explosions.

You must choose a helper distribution location that matches the target's loader/module, use bootstrap append/module adjustments **only when needed and with permission checks**, and test directly against the runtime class-loader topology. Simply having an offline tool compile is not enough to prove that the helper invocation will run in every application.

## 12. JVM Verifier, Stack Maps, and Exception Behavior

For a method to be loadable after insertion, you must preserve:

| Invariant | Risk If Violated |
| --- | --- |
| Operand stack height/type | `VerifyError` or runtime mismatch |
| `max_stack`, `max_locals` | Frame incompatible with new instructions |
| `StackMapTable` | Verification failure at branch/handler |
| Labels and branch targets | Incorrect branch routing |
| Exception handlers | Errors may be caught differently than before |
| Method reference/opcode | `NoSuchMethodError` or `IncompatibleClassChangeError` |
| Constructor initialization | Cannot use uninitialized `this` |
| Class file version | Older JVMs may fail to load |
| Attributes/metadata | Frameworks/debuggers may depend on them |

The Class-File API helps rebuild class files and manage structure, but **verification is still required**. Combine `ClassFile.verify`, `java -Xverify:all`, `javap`, and behavioral tests. If a helper throws an exception inside a `try` region of the original method, that exception can enter the original method's handler and change the result. The verifier does not detect this kind of semantic divergence.

Do not insert a hook that uses `this` at the beginning of a constructor before `super(...)` has completed without understanding uninitialized-instance rules. Do not treat adding a hook before `return` as covering all `throw` paths.

## 13. Overhead and Diagnostic Data Management

A helper call involves few instructions, yet it appears on the hot path. To measure overhead properly:

1. Unpatched baseline.
2. Patched version calling a **no-op** helper.
3. Patched version recording to a counter or bounded queue.
4. Patched version with a real exporter/collector.

Compare p50/p95/p99 latency, throughput, CPU, allocation/GC, dropped event counts, and backend cost. Limit payload size, sampling, number of labels, and retention. Avoid high-cardinality metric labels such as user IDs or raw URLs with many values. If the collector loses connectivity, the helper should not block requests indefinitely just to keep telemetry.

If business audit data requires absolute durability, use a dedicated audit/transaction channel; logs/traces in best-effort instrumentation may lose signals.

## 14. Layered QA

| Test | Permitted Conclusion |
| --- | --- |
| Original prints `RESULT=10` | Baseline for input `-7` |
| Patched prints two `HOOK_BEFORE` lines and `RESULT=10` | Insertion point is correct for the test case |
| `javap -c -p Sample` shows both `Math` calls intact | Original invocations were not deleted |
| `java -Xverify:all Sample` passes | Bytecode is valid on the tested JVM |
| Missing helper or wrong descriptor | Understands linkage/verification failure modes |
| Helper intentionally throws | Understands impacted exception contract |
| Patched a second time | Identifies duplicate/idempotence problem |
| Overloaded methods | Filter needs method descriptor |
| Target in custom loader/module | Helper visibility needs verification |
| High load and multithreading | Measures overhead, contention, drops |
| Live agent/retransform | Verifies callbacks, recursion, and JVM limitations |

Add tests with boundary inputs, exception branches, concurrency, and transaction behavior. Running a single sample input does not prove equivalence for every algorithm.

## 15. Common Pitfalls

- **Forgetting `builder.with(element)`:** deletes the original instruction, altering the algorithm and stack.
- **Wrong helper signature:** descriptor/opcode mismatch, causing verification or linkage errors.
- **Filtering only by method name:** accidentally instruments overloads or classes with matching names.
- **Not excluding helper calls:** creates self-hooks and recursion.
- **Running the patch multiple times:** duplicate instrumentation and increased overhead.
- **Confusing a before-call event with a successful call:** the hook runs beforehand even if the invocation later throws.
- **Assuming Class-File API exists since JDK 17:** the code requires JDK 24+.
- **Testing only with the JVM verifier:** valid bytecode can still slow down or break business logic because of the helper.
- **Ignoring class loaders/modules:** the class compiles, but the helper fails to resolve at runtime.
- **Writing logs/network directly on the hot path:** increases contention and latency.
- **Inserting at constructor entry without considering `this`:** risks violating initialization rules.
- **Treating a return-hook as `finally`:** fails to cover exceptional exits.

## 16. Self-Check Questions

1. Why does `builder.with(element)` preserve the original `Math.abs` call?
2. How does a helper with signature `(Ljava/lang/String;)V` use the operand stack without losing `int x`?
3. What advantage does `ClassTransform.transformingMethodBodies` have when you only want to modify one method?
4. What owner, name, descriptor, and opcode are needed to filter `Math.abs(int)`?
5. Why does `InvokeInstruction` not cover all forms of lambda calls?
6. If the helper throws a `RuntimeException`, is the original method guaranteed to reach the invocation after it?
7. Why can a transformation pass verification yet still increase p99 latency?
8. If there are multiple class loaders, what must you check to ensure they can access the helper?
9. What can running the tool twice without resetting do to `Probe.onCall` itself?
10. When moving from offline to an agent, how does `ClassFileTransformer`'s `return null` differ from `builder.with(element)`?
11. Why must you write additional unit tests for exception handlers and constructors?
12. If you want to load an agent on JDK 17, can you use the exact example with `java.lang.classfile` as-is?

## 17. Adoption Workflow

1. Finalize the goal and observation point, defining "before", "after", or "finally" semantics.
2. Select class/method/call site by specific descriptor, keeping the scope small.
3. Design a static helper with stable signature, visibility, and failure policy.
4. Insert new instructions and forward original `CodeElement`s via `builder.with`.
5. Generate class files from immutable original bytes; verify idempotence.
6. Inspect with `javap` and verify bytecode, preserving required class metadata.
7. Run behavioral tests across different branches and errors, and check modules/class loaders.
8. Measure latency, throughput, allocation, GC, and telemetry health.
9. If integrating into an agent, minimize work in the callback, exclude helpers, and monitor transform failures.
10. Canary deploy and prepare rollback if linkage, correctness, or overhead issues appear.

## 18. Official Documentation

- [JEP 484 – Class-File API](https://openjdk.org/jeps/484): Class-File API standardized in JDK 24.
- [Oracle JDK 24 – package java.lang.classfile](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/package-summary.html): parse/build/transform mechanisms and instrumentation guidance.
- [Oracle JDK 24 – ClassTransform](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassTransform.html): `transformingMethodBodies` and transform factories.
- [Oracle JDK 24 – CodeBuilder](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/CodeBuilder.html): `ldc`, `invokestatic`, `with`.
- [Oracle JDK 24 – ClassFile](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html): `parse`, `transformClass`, `verify`.
- [Oracle JDK 24 – ClassFileTransformer](https://docs.oracle.com/en/java/javase/24/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): Java agent hook point and returning `null` when not transforming.

**Key takeaway:** `CodeTransform` only needs to emit an additional helper call at the right position and preserve the original elements with `builder.with(element)`. Do not rewrite the entire application algorithm when you only need to observe a call site; at the same time, always verify that the helper can run safely in the real class loader, exception, and workload context.
