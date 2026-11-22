# Reporting Hypotheses, Bytecode Evidence, Execution Results, and Limitations of a Java Agent

## 1. From "the agent runs" to a verifiable report

When experimenting with Java instrumentation, the conclusion **"instrumented successfully"** is only credible if accompanied by independently verifiable evidence. A log line `agent started` proves that the JVM invoked the agent's entry point; it does **not** prove that the transformer matched a class, generated valid bytecode, that the method actually executed the new instruction, or that business data remained intact.

A good report must connect the following chain:

~~~text
Proposal / hypothesis (falsifiable)
        |
        v
Experimental conditions + baseline + negative controls
        |
        v
Structural evidence: original .class vs transformed .class
        |
        v
Execution evidence: JVM verifier + input/output + side effects
        |
        v
Analysis: which results support which hypothesis?
        |
        v
Limitations, assumptions, failures that could slip through, and next tests
~~~

This Knowledge article provides **a complete experimental report**, from the research question to source code, run commands, verified stdout, `javap` excerpts, a standalone bytecode verification program, and properly scoped conclusions.

Practical example: a Java agent using the **standard JDK 24 Class-File API** inserts exactly **one `Probe.hit()` call at the start of `PriceService.price(int)`**. The report checks normal method return, the exception-throwing path, an unselected method in the same class, and a control class not matched by the matcher.

**Key point:** this article is about **the methodology for proving agent results**, not a claim that a single log, a screenshot, or a single successful run is enough to prove production safety.

## 2. Six concepts that must be separated in a report

| Component | Definition | Example in this article |
| --- | --- | --- |
| **Hypothesis (H)** | A concrete statement capable of being falsified by experimental results | "The output class has exactly one `INVOKESTATIC Probe.hit:()V` in `price(int)`." |
| **Prediction** | What can be measured before running | Baseline probe count 0, with agent probe count 2 |
| **Procedure** | Conditions, commands, inputs, steps to produce evidence | `javac --release 24`, `-javaagent`, `javap`, verifier |
| **Observation** | Data actually returned by the tools | `transformed.price.probeCalls=1` |
| **Interpretation** | Reasoning linking observations to hypotheses | One helper callsite was added to the `price` method |
| **Limitation** | What the observations **cannot yet** prove | Does not prove all loaders/JVMs/methods/threads are safe |

A **tested assertion** should live at the observable layer. For example, "bytecode changed" should be confirmed by instruction traversal or `javap`, **not** by relying solely on a message printed by the transformer itself. Similarly, "no business impact" should have at least control inputs and exception cases, yet even then it holds only **for the cases that were run**.

### 2.1. Distinguishing direct evidence from inference

**Direct evidence:** the JDK Class-File API reads the post-transform class and finds the instruction:

~~~text
INVOKESTATIC demo/agent/Probe.hit:()V
~~~

**Reasonable bounded inference:** the transformed `price` method now contains a static callsite to the helper, and when executed through the test code path, the helper counter increments.

**Overreach:** "Every method in every module will be instrumented", "there will never be a `VerifyError`", "overhead is zero", or "every exception is measured". Those claims **must not** be inferred from a small test.

### 2.2. A report must have stopping and failure criteria

Before writing the transformer, define:

- **PASS:** how many helper calls must exist, in which method; what stdout must appear; which exception type must be preserved; the JVM verifier must report no errors.
- **FAIL:** wrong owner/opcode/descriptor, zero or double instrumentation, business output changed, control class affected, wrong exception type, JVM load failure.
- **INCONCLUSIVE:** unable to run the right JVM version, no transformed bytes, broken verification tool, or missing required controls.

Do not report "PASS" when only compiling without running, nor treat "transformer returned non-null" as sufficient evidence.

## 3. Research question and four falsifiable hypotheses

**Question:** Can a load-time agent add a helper call at the entry of exactly one method while leaving selected business observations unchanged?

In the test environment:

- Target class: `demo.report.PriceService`.
- Target method: `public static int price(int)` with JVM descriptor `(I)I`.
- Helper: `demo.agent.Probe.hit():void`, descriptor `()V`.
- Same-class control: `PriceService.label()`.
- Other-class control: `demo.report.ControlService`.
- Two inputs for target: `price(3)` (normal return) and `price(-1)` (throws).

| ID | Hypothesis declared **before running** | Clear falsification criteria |
| --- | --- | --- |
| **H1 — targeted transformation** | Output `PriceService.class` has exactly **1** `INVOKESTATIC Probe.hit:()V` in `price(int)`, at the first instruction; original has 0 | Missing hook, more than 1, wrong opcode/owner/type, or hook not at the start |
| **H2 — no spillover to control methods** | `label()` still has **0** calls to `Probe.hit`; transformer does not actively select `ControlService` | Verifier finds a hook in `label` or control no longer has expected behavior |
| **H3 — selected outputs/exceptions preserved** | Both with and without the agent yield `price(3)=21`, `price(-1)` throws `IllegalArgumentException`, `label=SAFE`, `ControlService.twice(5)=10` | Any of the four results differs from baseline |
| **H4 — hook side effect actually occurs** | Without agent: `Probe.hits=0`; with agent: after two calls to `price`, `Probe.hits=2` | Counter differs from prediction or JVM verifier/load fails |

H1 is **class-file structure** evidence. H2 uses controls in the same class and a separate control class. H3 is **behavior evidence on the test input set**. H4 is **runtime execution** evidence and confirms the hook is invoked at the entry of both normal/throw paths; it does **not** prove the agent classifies return vs. throw outcomes, because the demo only counts entries.

### 3.1. Why are negative controls also needed?

If you only see counter 2 after two calls, `Probe.hit()` could have been written directly in the source, called from `Main`, or the agent could have accidentally instrumented too broadly. Controls and bytecode diffs help rule out several alternative explanations:

- Source `PriceService` does **not** call the helper.
- The agentless baseline has `probe.hits=0`.
- `PriceService.label()` has no helper invocation in the original **and** transformed versions.
- `ControlService.twice(5)` returns 10 in both modes.
- Only `price(int)` has the new instruction at the start of its body.

Negative controls increase confidence, **but still do not prove** that all other classes in the JVM are never instrumented: the experiment only observes a specific scope.

## 4. Experimental design for a fair comparison

Run **two separate JVM processes**:

~~~text
Arm A — baseline:
    app-classes + agent JAR on classpath
    NO -javaagent
    call price(3), price(-1), label(), twice(5)
    print Probe.hits

Arm B — treatment:
    SAME app-classes + agent JAR
    WITH -javaagent:report-agent.jar
    WITH -Xverify:all
    call SAME inputs and order
    print Probe.hits

Collect additional evidence:
    original PriceService.class
    transformed PriceService.class
    javap original / transformed
    VerifyEvidence reads both files and asserts structure
~~~

**Kept identical:** compiler `javac --release 24`, source, inputs, classpath, and how business methods are invoked. **Intentionally varied:** arm B has the startup flag `-javaagent`, causing the JVM to invoke `premain` and register `ClassFileTransformer`.

Placing the agent JAR on the classpath **in both arms** ensures `Probe` is present so `Main` can read the counter, while **only arm B** runs `premain`. This avoids the misconception that "just adding the agent JAR to `-cp` makes the agent active".

### 4.1. Factors not fully controlled

Do not equate two JVMs with the exact same process: the JVM may choose different JIT timing/GC/scheduling. This article **does not compare execution time**, so those variables do not invalidate assertions that **count specific instructions, counters, and outputs**. If measuring overhead later, you need sufficient iterations, warmup, statistical analysis, and a stable environment.

In real applications, class loading can happen earlier than expected. The agent must be registered before the target class definition; if the target is already loaded, a simple `addTransformer(..., false)` does not retroactively transform that class.

## 5. Environment and tools recorded in the report

**Environment used to verify the example:**

| Property | Experimental value |
| --- | --- |
| OS/shell | Windows, PowerShell |
| Compiler | `javac 24.0.2` |
| Runtime | Zulu/OpenJDK **24.0.2** |
| Bytecode level | `javac --release 24`, class-file major **68** |
| Class-file manipulation | `java.lang.classfile`, standardized in **JDK 24** (JEP 484) |
| Agent mechanism | `java.lang.instrument`, `premain` with `-javaagent` |
| JVM verification | `-Xverify:all` on both runs |
| Opcode inspection | `javap -c -p` |
| Automated verification | `VerifyEvidence` reads bytes using JDK 24 Class-File API |
| Third-party libraries | No ASM/Byte Buddy |
| Inputs | `3` and `-1` for `price`; `5` for control |

**Version is a mandatory factor:** JDK 17/21 do not support the standard **`java.lang.classfile` package** shown in this JDK 24 sample. Do not report `COMPLETED/RUN_PASS` from a JDK 17 machine without an actual test run using a different API.

**Information to record in a real report:** execution timestamp, git revision or content hashes of source files, full `java -version`/`javac -version`, architecture, module/classpath, command line, test inputs, exit codes, logs, and SHA-256 of artifacts. Do not assume sample data from one machine is a mandatory value on every machine.

### 5.1. `ClassFileTransformer` contract

The Javadoc confirms that the transformer is called **before the JVM defines the class**, returning `null` if no change is made, or **a new `byte[]` array** if changed; it **must not** modify the input `classfileBuffer` array. Multiple transformers may be chained, so you must not assume the final bytes are determined by a single agent alone.

The Javadoc also states that an uncaught exception in a transformer does not necessarily stop class loading; the JVM still tries subsequent transformers and continues loading as if the transformer returned `null`. Therefore, **asserting on the actual output class** is more important than a log line from the transformer.

Source: [Java 24 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/24/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html).

## 6. Project structure for reproducibility

~~~text
agent-evidence-report/
  agent-src/demo/agent/
    Probe.java
    ReportAgent.java
  app-src/demo/report/
    PriceService.java
    ControlService.java
    Main.java
  tool-src/
    VerifyEvidence.java
  MANIFEST.MF
  agent-classes/                    (created by javac)
  app-classes/                      (created by javac)
  tool-classes/                     (created by javac)
  report-agent.jar                  (created by jar)
  transformed/demo/report/
    PriceService.class              (dumped by agent during test)
~~~

There are **6 complete Java files**. `Probe` is packaged in the agent JAR; `Main` references `Probe.hits()` but does not call `Probe.hit()` directly. `VerifyEvidence` is a standalone program using the same JDK 24, **not running inside the transformer callback**, avoiding reliance on self-reported agent logs.

All paths here are relative to the **project root directory**. The dump under `transformed` is only a verification artifact; production does not need to write classfiles to disk on the hot path.

## 7. Application source code: business results and controls

### 7.1. `app-src/demo/report/PriceService.java`

~~~java
package demo.report;

public final class PriceService {
    public static int price(int units) {
        if (units < 0) throw new IllegalArgumentException("units");
        return units * 7;
    }

    public static String label() {
        return "SAFE";
    }
}
~~~

In `price(int)` there are **two exit paths**: `return units * 7` and `throw IllegalArgumentException`. The `label()` method in the same class is a **negative control** to check that the matcher does not accidentally insert hooks into all methods.

### 7.2. `app-src/demo/report/ControlService.java`

~~~java
package demo.report;

public final class ControlService {
    public static int twice(int number) {
        return number * 2;
    }
}
~~~

This is a **different class** that the agent **does not select**. That it still returns `10` for input `5` serves as a behavioral control. It does not represent every other class in the JVM: the test does not scan the entire system.

### 7.3. `app-src/demo/report/Main.java`

~~~java
package demo.report;
import demo.agent.Probe;

public final class Main {
    public static void main(String[] args) {
        System.out.println("price3=" + PriceService.price(3));
        try {
            PriceService.price(-1);
        } catch (IllegalArgumentException expected) {
            System.out.println(
                    "error=" + expected.getClass().getSimpleName());
        }
        System.out.println("label=" + PriceService.label());
        System.out.println("control=" + ControlService.twice(5));
        System.out.println("probe.hits=" + Probe.hits());
    }
}
~~~

**Why does `Main` use `Probe.hits()`?** To print the counter after two invocations. `Main` does **not** call `Probe.hit()`, so when the counter increments in the treatment, combined with bytecode evidence it can be attributed to the new call in `price`.

**Why not catch broad `Throwable`?** In the test, the caller only expects `IllegalArgumentException` on negative input. If the agent causes `LinkageError` or other errors, they must surface so the test fails instead of being hidden by a `catch(Throwable)`.

## 8. Helper and permitted side-effect contract

**File `agent-src/demo/agent/Probe.java`**

~~~java
package demo.agent;
import java.util.concurrent.atomic.AtomicInteger;

public final class Probe {
    private static final AtomicInteger HITS = new AtomicInteger();

    private Probe() { }

    public static void hit() {
        HITS.incrementAndGet();
    }

    public static int hits() {
        return HITS.get();
    }
}
~~~

This is a small helper that only increments a counter. On a real hot path, `AtomicInteger` still incurs overhead; however, compared to `System.out.println` on every invocation, it is easier to test and less intrusive.

**Measurement contract of the demo:** one entry into `price` ⇒ one call to `Probe.hit`, regardless of whether the method later returns or throws. Because the hook is inserted **at entry**, `probe.hits=2` cannot tell how many of the two calls returned vs. threw, unless combined with output/exception tests. If you need to measure **exit outcomes**, you must insert separate exit hooks/exception handlers with corresponding tests.

`AtomicInteger` is thread-safe for increments, but it does not distinguish class loaders or trace IDs. If the helper is defined in **two different class loaders**, there can be two independent static counters. The example uses a simple classpath/loader to avoid that variable.

## 9. Java agent generating new bytecode with the JDK 24 Class-File API

**File `agent-src/demo/agent/ReportAgent.java`**, complete code compiled and run:

~~~java
package demo.agent;

import java.lang.classfile.*;
import java.lang.constant.ClassDesc;
import java.lang.constant.MethodTypeDesc;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.ProtectionDomain;

public final class ReportAgent {
    private static final ClassDesc PROBE =
            ClassDesc.of("demo.agent.Probe");
    private static final MethodTypeDesc NO_ARGS_VOID =
            MethodTypeDesc.ofDescriptor("()V");

    public static void premain(String args, Instrumentation inst) {
        inst.addTransformer(new OneMethodTransformer(), false);
        System.out.println("agent.ready=true");
    }

    private static final class OneMethodTransformer
            implements ClassFileTransformer {
        @Override
        public byte[] transform(ClassLoader loader, String className,
                Class<?> redefining, ProtectionDomain domain, byte[] bytes) {
            if (!"demo/report/PriceService".equals(className)) {
                return null;
            }

            ClassFile cf = ClassFile.of();
            CodeTransform addEntry = CodeTransform.ofStateful(() ->
                    new CodeTransform() {
                @Override
                public void atStart(CodeBuilder out) {
                    out.invokestatic(PROBE, "hit", NO_ARGS_VOID);
                }

                @Override
                public void accept(
                        CodeBuilder out, CodeElement element) {
                    out.with(element);
                }
            });

            byte[] result = cf.transformClass(cf.parse(bytes),
                    ClassTransform.transformingMethodBodies(
                            m -> m.methodName().equalsString("price")
                                    && m.methodType().equalsString("(I)I"),
                            addEntry));
            try {
                Path destination = Path.of(
                        "transformed/demo/report/PriceService.class");
                Files.createDirectories(destination.getParent());
                Files.write(destination, result);
            } catch (java.io.IOException ex) {
                throw new IllegalStateException(
                        "test dump failed", ex);
            }

            System.out.println("agent.transformed=" + className);
            return result;
        }
    }
}
~~~

### 9.1. Match the class, then match the exact method descriptor

In the callback, `className` is in **slash-separated internal name form** `"demo/report/PriceService"`. Meanwhile `ClassDesc.of("demo.agent.Probe")` uses a **dot-separated binary name**. Mixing up the two representations can cause the transform not to match or fail to call the helper.

The predicate:

~~~java
m -> m.methodName().equalsString("price")
        && m.methodType().equalsString("(I)I")
~~~

is **the method-filtering code snippet**. The descriptor `(I)I` means taking one `int` and returning one `int`. It avoids accidentally instrumenting an overload `price(String)` if added later.

`ClassTransform.transformingMethodBodies` transforms the method bodies selected by the predicate; other methods are passed through unchanged in the model. Here, `label()` is not selected, so the verifier must report `transformed.label.probeCalls=0`.

### 9.2. Why `atStart` and `out.with(element)`?

`CodeTransform.ofStateful` provides a transform instance for traversal, and `atStart(CodeBuilder)` emits the instruction:

~~~java
out.invokestatic(PROBE, "hit", NO_ARGS_VOID);
~~~

It places an `INVOKESTATIC` at entry, before the original code. `accept(...){ out.with(element); }` forwards **every existing code element** into the builder. Forgetting `out.with(element)` can drop the method body.

`NO_ARGS_VOID` is the descriptor `()V`, matching `public static void Probe.hit()`. In this test, the helper takes no arguments and returns no value, so it does not disturb the operand stack used to compute `units * 7`.

**Do not overgeneralize:** constructors, class initializers, native/abstract methods, complex exception handlers, synchronized methods, or bytecode with complex stack maps have their own constraints. An `atStart` operation that works on `price(int)` is **not** automatically safe for every method.

### 9.3. The dump file is an evidence-gathering tool, not a required agent operation

The transformer writes the new bytes to `transformed/demo/report/PriceService.class` via `Files.write` **only for independent testing**. Dumping is not required for the JVM to receive the bytes; the returned `byte[] result` is what feeds the next JVM steps.

In production, synchronous I/O inside `transform` can block class loading, cause recursion/circularity, and fill disks. Automated reporting systems should dump only under a debug flag in test environments, limit the number of classes, hash/deduplicate, and clean up appropriately.

### 9.4. What the agent does not do

The test version **does not**:

- Edit `PriceService.java` source;
- Overwrite the original `app-classes/demo/report/PriceService.class`;
- Modify constructors or `label()`;
- Instrument `ControlService`;
- Measure elapsed time/CPU;
- Use `retransformClasses` for already-loaded classes;
- Insert hooks before `return` or after exceptions;
- Guarantee the helper is always available across all modules/class loaders;
- Perform production benchmarking.

Explicitly stating what it **does not** do prevents readers from interpreting a PASS result as untested agent capabilities.

## 10. Independent verifier: turning report claims into assertions

**File `tool-src/VerifyEvidence.java`**

~~~java
import java.lang.classfile.*;
import java.lang.classfile.instruction.InvokeInstruction;
import java.lang.constant.ClassDesc;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public final class VerifyEvidence {
    private static final ClassDesc HOOK =
            ClassDesc.of("demo.agent.Probe");

    private static void check(String label, Path file)
            throws Exception {
        ClassModel model = ClassFile.of()
                .parse(Files.readAllBytes(file));
        for (String name : new String[] {
                "price", "label"}) {
            var method = model.methods().stream()
                    .filter(m -> m.methodName().equalsString(name))
                    .findFirst().orElseThrow();
            var code = method.code().orElseThrow();
            List<Instruction> instructions =
                    code.elementStream()
                            .filter(e -> e instanceof Instruction)
                            .map(e -> (Instruction) e).toList();

            long probes = instructions.stream()
                    .filter(VerifyEvidence::isProbe)
                    .count();
            System.out.println(label + "." + name
                    + ".probeCalls=" + probes);

            long expected = label.equals("transformed")
                    && name.equals("price") ? 1 : 0;
            if (probes != expected) {
                throw new AssertionError(
                        label + "." + name + " count");
            }

            if (name.equals("price")) {
                boolean first =
                        isProbe(instructions.getFirst());
                System.out.println(label
                        + ".price.firstIsProbe=" + first);
                if (first != label.equals("transformed")) {
                    throw new AssertionError(
                            label + ".price first instruction");
                }
            }
        }
    }

    private static boolean isProbe(Instruction instruction) {
        return instruction instanceof InvokeInstruction call
                && call.opcode() == Opcode.INVOKESTATIC
                && call.owner().asSymbol().equals(HOOK)
                && call.name().equalsString("hit")
                && call.typeSymbol()
                        .descriptorString().equals("()V");
    }

    public static void main(String[] args)
            throws Exception {
        check("original", Path.of(
                "app-classes/demo/report/PriceService.class"));
        check("transformed", Path.of(
                "transformed/demo/report/PriceService.class"));
        System.out.println("verification=PASS");
    }
}
~~~

Unlike merely printing counts, this tool throws an **`AssertionError` when results do not match**; it prints `verification=PASS` only after **all assertions pass**.

It does not ask the transformer "what did you insert?", but independently parses **two different files** from the file system. The `isProbe` check verifies:

- Opcode is `INVOKESTATIC`;
- Owner is `demo.agent.Probe`;
- Method name is `hit`;
- Descriptor is `()V`.

Do not verify by searching for the string `Probe` in the constant pool: a class can contain that string in metadata without **any instruction calling the method**.

**Control inside the verifier:** `price` is expected to change 0→1, while `label` stays 0→0. Checking the first instruction of `price` also catches cases where the hook is placed at the wrong position even if the total count is still 1.

## 11. Manifest and compile/run commands

**File `MANIFEST.MF`**

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.ReportAgent

~~~

The main attributes must end with a blank line. The example uses `premain` and `-javaagent`, not dynamic attach or `agentmain`.

### 11.1. Windows PowerShell (tested)

From the root directory `agent-evidence-report`:

~~~powershell
New-Item -ItemType Directory -Force agent-classes, app-classes, tool-classes | Out-Null

javac --release 24 -d agent-classes agent-src/demo/agent/ReportAgent.java agent-src/demo/agent/Probe.java

jar --create --file report-agent.jar --manifest MANIFEST.MF -C agent-classes .

javac --release 24 -cp report-agent.jar -d app-classes app-src/demo/report/PriceService.java app-src/demo/report/ControlService.java app-src/demo/report/Main.java

# A: baseline
java -Xverify:all -cp "app-classes;report-agent.jar" demo.report.Main

# B: agent
java -Xverify:all -javaagent:report-agent.jar -cp "app-classes;report-agent.jar" demo.report.Main

# Independent verification, after arm B has created transformed/
javac --release 24 -d tool-classes tool-src/VerifyEvidence.java
java -cp tool-classes VerifyEvidence
~~~

PowerShell uses a **semicolon** as the classpath separator. Each command can be run individually and its **exit code** should be checked; do not treat clean stdout as success if `javac`/`java` returned an error code.

### 11.2. Linux/macOS Bash

~~~bash
mkdir -p agent-classes app-classes tool-classes

javac --release 24 -d agent-classes \
  agent-src/demo/agent/ReportAgent.java \
  agent-src/demo/agent/Probe.java

jar --create --file report-agent.jar --manifest MANIFEST.MF \
  -C agent-classes .

javac --release 24 -cp report-agent.jar -d app-classes \
  app-src/demo/report/PriceService.java \
  app-src/demo/report/ControlService.java \
  app-src/demo/report/Main.java

java -Xverify:all -cp "app-classes:report-agent.jar" demo.report.Main

java -Xverify:all -javaagent:report-agent.jar \
  -cp "app-classes:report-agent.jar" demo.report.Main

javac --release 24 -d tool-classes tool-src/VerifyEvidence.java
java -cp tool-classes VerifyEvidence
~~~

Bash uses a **colon** in the classpath and `\` for line continuation. The Java source is JDK 24 compatible, but **the run was performed on Windows**; on macOS/Linux you should re-test if you want to include those platforms in the verified scope.

### 11.3. Files and data to collect after running

Keep at minimum:

~~~text
evidence/
  environment.txt      (java/javac version, OS, commands)
  baseline.stdout      (output without -javaagent)
  treatment.stdout     (output with -javaagent)
  original.javap.txt   (javap -c -p of original .class)
  transformed.javap.txt(javap -c -p of new .class)
  verify.stdout        (stdout + exit code of VerifyEvidence)
  hashes.txt           (SHA-256 of .class files)
  hypothesis.md        (H1...H4 and PASS/FAIL criteria)
  conclusion.md        (evidence table, limitations)
~~~

This is a **sample evidence checklist**, not a claim that the script above automatically creates all these files. The operator can redirect stdout or use a CI artifact collector, and must keep paths/versions consistent so others do not accidentally compare outputs from different builds.

## 12. Actual run results: baseline first, treatment second

### 12.1. Baseline — without `-javaagent`

~~~text
price3=21
error=IllegalArgumentException
label=SAFE
control=10
probe.hits=0
~~~

**Interpretation of observation:** `price(3)` returns `3×7=21`, `price(-1)` throws the right exception, both controls return `SAFE`/`10`, and the helper count does not increment.

"Class `Probe` is on the classpath" does **not** mean "instrumented". `Main` reads `Probe.hits()` but does not call `hit()`.

### 12.2. Treatment — with agent and `-Xverify:all`

~~~text
agent.ready=true
agent.transformed=demo/report/PriceService
price3=21
error=IllegalArgumentException
label=SAFE
control=10
probe.hits=2
~~~

**Observed:** the JVM invoked `premain`, the transformer matched the target class, all four monitored business results remained unchanged, and the helper count increased to **2** after two calls to the target.

Because the hook is at **entry**, both `price(3)` and `price(-1)` increment the counter. You **must not** write "the agent measured 2 successes": one of the two invocations threw an exception. To classify return vs. throw, separate exit instrumentation is required.

### 12.3. A transparent before/after table

| Check | Baseline | With agent | Assessment within test scope |
| --- | --- | --- | --- |
| `price(3)` | `21` | `21` | Identical result |
| `price(-1)` | `IllegalArgumentException` | Same type | Exception type preserved |
| `label()` | `SAFE` | `SAFE` | Control method output unchanged |
| `ControlService.twice(5)` | `10` | `10` | Control class output unchanged |
| `Probe.hits()` | `0` | `2` | Hook side effect differs as predicted |
| `-Xverify:all` | JVM runs | JVM runs | Bytecode of tested classes accepted by VM |

**Why not treat `Probe.hits=2` as a performance metric?** This is a count of helper calls, not duration, allocation, throughput, number of traces stored by a backend, or sampling probability.

## 13. Bytecode evidence: which instructions actually changed?

After arm B, two files exist:

~~~text
app-classes/demo/report/PriceService.class
transformed/demo/report/PriceService.class
~~~

Run:

~~~bash
javap -c -p -classpath app-classes demo.report.PriceService
javap -c -p -classpath transformed demo.report.PriceService
~~~

### 13.1. `price(int)` in the original

Opcode excerpt, verified offsets:

~~~text
public static int price(int);
  Code:
     0: iload_0
     1: ifge          14
     4: new           #7    // class java/lang/IllegalArgumentException
     7: dup
     8: ldc           #9    // String units
    10: invokespecial #11  // Method IllegalArgumentException.<init>...
    13: athrow
    14: iload_0
    15: bipush        7
    17: imul
    18: ireturn
~~~

The original file has no `invokestatic demo/agent/Probe.hit:()V`. It has `athrow` for negative input and `ireturn` for non-negative input.

### 13.2. `price(int)` in the transformed version

~~~text
public static int price(int);
  Code:
     0: invokestatic  #31   // Method demo/agent/Probe.hit:()V
     3: iload_0
     4: ifge          17
     7: new           #7    // class java/lang/IllegalArgumentException
    10: dup
    11: ldc           #9    // String units
    13: invokespecial #11  // Method IllegalArgumentException.<init>...
    16: athrow
    17: iload_0
    18: bipush        7
    20: imul
    21: ireturn
~~~

**Evidence E1:** in the new version, the first instruction at `offset 0` is `INVOKESTATIC Probe.hit:()V`; the original code remains present afterward. Subsequent offsets shift because the new instruction takes 3 bytes in the test.

**Do not use constant-pool index `#31` or specific offsets as cross-JDK/compiler invariants.** What is more reliable is opcode + symbolic owner + method name + descriptor and the exact position. With different source/compilers, the constant pool and branch offsets can differ.

### 13.3. Control in the same class

`PriceService.label()` in both versions:

~~~text
public static java.lang.String label();
  Code:
     0: ldc           #14   // String SAFE
     2: areturn
~~~

This is **a verified excerpt with identical original instructions**. Even though `PriceService.class` as a whole changed (due to the constant pool and `price`), the `label` method **had no helper inserted**.

**Limitation:** `javap` confirms the instructions shown in the two files; it does not automatically conclude that every attribute/debug metadata item is byte-for-byte identical. To prove a class is unchanged at a specific structural level, you must define the comparison level and not confuse **semantic equivalence** with **byte-for-byte equality**.

## 14. Independent evidence: stdout of `VerifyEvidence`

After compiling and running the tool in section 10:

~~~text
original.price.probeCalls=0
original.price.firstIsProbe=false
original.label.probeCalls=0
transformed.price.probeCalls=1
transformed.price.firstIsProbe=true
transformed.label.probeCalls=0
verification=PASS
~~~

**Evidence E2:** the standalone program read the original/transformed bytes, counted exact `INVOKESTATIC Probe.hit:()V` calls, and asserted:

- `price`: **0 → 1** probe calls;
- first instruction of `price`: **not probe → probe**;
- `label`: **0 → 0** probe calls;
- on wrong expected count or position, the tool **throws `AssertionError`** instead of printing `PASS`.

**This is not an agent "self-report".** The tool runs **after the application JVM has exited**, on artifact files generated in the same experiment directory. It verifies exactly what was stated in H1/H2.

However, a tool parsing successfully still does not prove all execution paths are safe. Therefore `-Xverify:all` and runtime behavior tests are **two complementary layers of evidence** that should not be skipped.

## 15. Size, SHA-256, and artifact integrity

In the described test run:

| Artifact | Size | SHA-256 |
| --- | ---: | --- |
| Original `PriceService.class` | 478 bytes | `5720381FD6619E0921094173C7C7D0718E7E8AECCEAD88154163025EC3791DF5` |
| Transformed `PriceService.class` | 519 bytes | `A9550ADD556B25665C10978C14FC93B4495BC4BB71D71232F98864AFB1198059` |

Hashes were taken **directly from the two tested files** (JDK 24.0.2, exact code and build path shown here). Two different hashes are evidence that the bytes differ; **they do not by themselves prove the class bytes are valid** or that only the expected change occurred.

Re-measure on PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 app-classes/demo/report/PriceService.class
Get-FileHash -Algorithm SHA256 transformed/demo/report/PriceService.class
Get-Item app-classes/demo/report/PriceService.class, transformed/demo/report/PriceService.class | Select-Object Name, Length
~~~

Re-measure on Bash:

~~~bash
sha256sum app-classes/demo/report/PriceService.class \
  transformed/demo/report/PriceService.class
wc -c app-classes/demo/report/PriceService.class \
  transformed/demo/report/PriceService.class
~~~

Hash results can differ when compiler/build options/constant pool/source differ. **Do not** make the fixed hashes above a PASS condition on every machine. The more important criterion is that **both artifacts have clear provenance**, the transformed target class has the exact new callsite, and test behavior is correct.

### 15.1. Why keep both original and transformed?

If you only save the transformed file, reviewers struggle to determine whether the instruction was already in the source or came from another build. Keeping the original from the same build and same test session enables a `diff`:

- Before: `price` starts with `iload_0`.
- After: `price` starts with `invokestatic Probe.hit`.
- After: `label` has no new hook.
- Same: selected output tests remain correct.

Traceable evidence (source → javac output → transform output → verifier output → runtime output) is far more trustworthy than a screenshot of a log snippet lacking provenance.

## 16. Conclusion table for each hypothesis

| Hypothesis | Supporting data | Properly scoped conclusion |
| --- | --- | --- |
| **H1** — one hook at `price` entry | `javap` offset 0; verifier `0→1` and `firstIsProbe=true` | **PASS** on the test build's classfile |
| **H2** — no spillover to `label` | `label.probeCalls=0` before and after; `label=SAFE` | **PASS** for the checked control method |
| **H3** — selected outputs/exceptions preserved | `price3=21`, `error=IllegalArgumentException`, `label=SAFE`, `control=10` in both JVMs | **PASS** for the specific input set |
| **H4** — hook executes twice | `Probe.hits=0` without agent, `2` with agent | **PASS** for the test call sequence |
| **Bytecode validity** | Treatment runs with `-Xverify:all` without `VerifyError` | **PASS** for this class/JVM/load path |
| **Production performance** | No load/latency benchmark or sample distribution | **NOT TESTED** |
| **Safety across all methods/JVMs** | Tested only one class, one method, one runtime | **NOT TESTED** |

There is no basis for calling the overall conclusion "a method that always works on every application". A more accurate conclusion is **"the four hypotheses of this specific experiment are supported by multiple types of evidence, within the tested configuration and data scope"**.

**Report wording:** you may write `PASS` for an assertion with clear inputs/conditions/expected/actual. Do not write "proved the agent is completely safe" just because all existing tests passed.

## 17. Confidence: evidence layers do not replace each other

| Layer | Evidence | Failures that can still slip through |
| --- | --- | --- |
| **E0 — source review** | Grep/read source shows no original helper call | Build differs from source, class already processed by another tool |
| **E1 — transform output** | New byte array, dump file, different SHA | Bytecode may be invalid or never applied by the JVM |
| **E2 — bytecode structure** | `javap` + `VerifyEvidence` instruction assertions | Independent verifier does not prove runtime semantics |
| **E3 — JVM load/verification** | `-Xverify:all` succeeds | JVM does not verify business correctness on all inputs |
| **E4 — runtime behavior** | Baseline/treatment outputs and counter 0→2 | Only a few inputs; does not prove concurrency/perf/long-run |
| **E5 — production assurance** | Soak/load/security/cross-loader/restart tests | Not present in this experiment |

**Use multiple independent layers:** if the transformer prints "insertion done", that is **self-reported E1**. If `VerifyEvidence` in another process confirms the opcode and method, you add **E2**. If the JVM loads successfully and produces the right output, you add **E3/E4**. No single layer needs to "prove everything".

Do not treat hashes as E4: hashes only prove content identity of the recorded artifacts, not that they run correctly.

## 18. Inherent limitations of the experiment

### 18.1. Method and bytecode scope

The article only selected one `public static int price(int)` with a conditional, a return, and an explicit exception. It did not test:

- Constructors `<init>` and class initializers `<clinit>`;
- `native`/`abstract` methods without `Code`;
- `long`/`double`/`void`/reference returns;
- Methods with complex try/catch/finally, synchronized, monitor enter/exit;
- Lambdas, bridge/synthetic methods, complex invokedynamic;
- Interface default methods or multiple overloads with the same name;
- Method-level security/access in named modules.

The Class-File API supports broad manipulation, but **the experiment's transform logic itself** does not yet handle these cases.

### 18.2. Observed level of impact

The article proves the **entry probe** increments the counter; it did not measure:

- Elapsed/CPU time;
- Return vs. throw classification;
- Trace correlation/baggage;
- Memory allocations, GC pauses;
- Event loss, batching, exporter retries;
- p95/p99 latency and throughput impact.

Even when business output matches baseline, the method executed an extra `AtomicInteger.incrementAndGet()`. Thus **"does not change the tested business results"** is different from **"has zero impact on the application"**.

### 18.3. Class loader, module, and concurrency boundaries

The example classpath uses a simple loader. On an application server/plugin framework:

- The target class may be defined by a custom class loader that cannot see `demo.agent.Probe`.
- A named module may lack a read edge or package export, leading to `IllegalAccessError` or linkage issues.
- Multiple `PriceService` classes with the same binary name may exist in different loaders; matching by name alone is **not enough** to bind a single class identity.
- Concurrent class loads/transformers can create races and different transformation orders.
- The helper may have multiple static counters if defined in multiple loaders.

Therefore the experiment does **not** prove correctness across all class-loader/module-layer topologies.

### 18.4. Load timing, transformer errors, and rollback

The transformer is registered in `premain` and only intercepts initial class definition; if a class is already loaded, calling `addTransformer(..., false)` does not go back in time.

If `transform` throws an exception, the Javadoc notes that the JVM may still continue loading without changes from that transformer. In production, you must have error counters/diagnostics; do not rely solely on exceptions to force fail-fast.

`removeTransformer` only removes the registration for future transformations; **it does not automatically remove instructions already added to loaded classes**. If rollback is needed, you must design conditional retransform/redefine or restart the JVM, and verify bytes/behavior after rollback.

### 18.5. Risk when the helper fails

`Probe.hit()` runs **before** business instructions. If the helper itself throws an `Error`, `price` may not execute its body. The "preserved output" behavior tested in this article is guaranteed **only when the helper operates normally** during the test.

A production agent needs:

- Recursion guards and exclusions for agent/helper/logger/exporter;
- A fail-open policy on telemetry errors, without blindly swallowing JVM-critical `Error`s;
- Bounded queues, sampling, and clear backpressure;
- No synchronous file/log/network I/O on the hot path;
- Checks that error reports do not contain sensitive data;
- Tests that intentionally break the helper to understand impact on original exceptions/returns.

## 19. How to write the "results" section to avoid reporting bias

A common mistake is starting an experiment expecting "it must succeed", then cherry-picking log lines that look favorable. A better process:

1. Write H1–H4 and FAIL criteria **before editing the agent**.
2. Keep source/build inputs identical, changing exactly one variable: toggling `-javaagent`.
3. Run the baseline first to establish original behavior.
4. Capture stdout, stderr, **exit code**, and artifacts, even on failure.
5. Use an independent tool to assert opcode/owner/name/descriptor and position.
6. Conclude only on cases with data; mark out-of-scope items as `NOT TESTED`.
7. Re-run on a clean build if compiler flags/agent code change.
8. If a mismatch is found, **do not edit the expected table to match actual** without explaining the cause and creating a new test version.

**Citing evidence in the report:** instead of "the agent worked well", write "In the JDK 24.0.2 build, `VerifyEvidence` returned `transformed.price.probeCalls=1`, process exit code 0, and JVM `-Xverify:all` produced `price3=21` and `probe.hits=2`."

### 19.1. Recommended report statuses

| Status | When to use |
| --- | --- |
| `PASS` | Test has clear expected values, ran, and exit code and actuals match |
| `FAIL` | Ran, but an assertion failed or the JVM did not complete per contract |
| `BLOCKED` | Missing JDK/tool/permission/library prevented running |
| `INCONCLUSIVE` | Data exists, but cause cannot be isolated or evidence is missing |
| `NOT TESTED` | No test was ever run for that scope |

Do not use `SKIPPED` as a synonym for `PASS`; skipping means **not running the test**, not that the system passed.

## 20. Reusable experimental report template

In real-world work, a report should contain the following sections (abbreviated according to scale):

~~~markdown
# Java Agent Report — <feature description>

## Scope
- Selected class/method/descriptor/loader/module
- JVM/JDK version, flags, OS, revision
- Expected behaviors / out-of-scope behaviors

## Hypotheses
| ID | Prediction | PASS condition | FAIL condition |

## Test Design
- Baseline, treatment, controls
- Input samples (normal/throw/boundary)
- How stdout/stderr/exit code/bytes are collected
- Variables held constant

## Evidence
- E1: source revision and compile logs
- E2: original vs transformed class bytes, SHA-256
- E3: javap diff and opcode assertion program
- E4: JVM verifier + runtime stdout
- E5: load/concurrency/security tests if any

## Results
| H | Expected | Actual | Evidence ID | PASS/FAIL |

## Limitations and Risks
- JVM/version/loader/module/performance/coverage
- Untested failure modes
- Conclusions not permitted to be inferred

## Next Actions
- Additional tests, owner, acceptance criteria
~~~

This is a **Markdown template**; fields in `<...>` are placeholders for the report author to replace with real information, **not an executed deliverable**. Do not insert an unfilled template into a final report and claim it is complete.

## 21. Sample report filled in from the actual experiment

### Scope and hypotheses

**Target:** `PriceService.price(int)`, transformed only at initial load on JDK 24. **Change type:** add one `INVOKESTATIC Probe.hit:()V` at method entry. **Controls:** `PriceService.label` and `ControlService.twice`. **Hypotheses:** H1–H4 in section 3.

**Build:** `javac --release 24` on Zulu/OpenJDK 24.0.2; agent loaded via `-javaagent:report-agent.jar`; JVM verifier enabled with `-Xverify:all`. No ASM/Byte Buddy.

### Evidence summary mapped to requirements

| Evidence ID | Where evidence was collected | Observation |
| --- | --- | --- |
| **E-B0** | Baseline Java stdout | `price3=21`, `error=IllegalArgumentException`, controls normal, `probe.hits=0` |
| **E-T1** | Treatment Java stdout | Same business outputs, `probe.hits=2`, agent callback on target class |
| **E-BC1** | `javap -c -p` original | `price` starts with `iload_0`; no helper call |
| **E-BC2** | `javap -c -p` transformed | `price` starts with `invokestatic Probe.hit:()V` |
| **E-IV1** | `VerifyEvidence` | `price.probeCalls 0→1`, `label 0→0`, `verification=PASS` |
| **E-SHA** | `Get-FileHash -Algorithm SHA256` | Original and new files have different hashes |
| **E-VM** | `-Xverify:all`, exit code 0 | JVM accepted the bytecode in the test |

### Decision

**H1 PASS, H2 PASS, H3 PASS, H4 PASS** within the test scope above. **No conclusion** is made on ability to instrument all class loaders, no claim on production overhead, and no data on retransform/redefine, helper error handling, or multithreaded load.

**Logical next steps:** expand the test matrix to multiple loaders, overloads, methods with try/catch, concurrent calls, helper failures, other JDKs, and measure overhead on a build with `Files.write`/logging removed from the transform path.

The sample report illustrates how to tie each conclusion to **a verifiable source of evidence**, without mixing information from source code, compiler, transformed bytes, and runtime counters.

## 22. Mistakes that make a report look "good but wrong"

| Misconception in report | Why it is wrong | How to fix |
| --- | --- | --- |
| "Seeing `premain` log means instrumented" | Only proves agent initialization | Verify target transform + bytecode |
| "Transformer returned non-null ⇒ bytecode is always valid" | JVM may reject it or class may misbehave | `-Xverify:all` + runtime tests |
| "`Probe` in constant pool ⇒ method was called" | Could just be metadata/string | Traverse `InvokeInstruction` for exact opcode/descriptor |
| "Different hash ⇒ logic changed by only one instruction" | Hash does not show semantic diff | `javap`/Class-File API structural diff |
| "No agent, `Probe` on classpath still instruments" | `-cp` does not trigger `premain` | Compare `-javaagent` and baseline |
| "Agent count 2 ⇒ both requests succeeded" | Hook is at entry, does not classify outcomes | Track input/exception outcomes separately |
| "`label=SAFE` ⇒ entire class byte-for-byte unchanged" | Class contains modified method/different constant pool | Only conclude on tested method output/probes |
| "JVM verifier PASS ⇒ good performance" | Verifier checks structure, not benchmarks | Load/latency/GC tests |
| "One run without errors ⇒ all inputs work" | Does not cover boundaries/concurrency | Test matrix and property-based tests |
| "No error logs ⇒ no drops/exceptions" | Logger/exporter may be disabled | Collect stderr, exit codes, counters |
| "Negative control needs no source/provenance" | Control could be built from different source | Keep revisions/hashes |
| "Tested Java 24 ⇒ tested Java 17" | API/packages/bytecode differ by version | Record exact JDK version, do not lower requirement |
| "Removing transformer rolls back bytes" | Already-loaded classes keep transformations | Conditional retransform/redefine or restart |
| "No overhead because output is identical" | Extra hook/atomic op still costs resources | Benchmark with warmup and controls |
| "Agent never touches other classes" | Seeing one callback in a test does not cover every JVM | Clear scope, more tests, and strict matchers |
| "Report only needs screenshots" | Hard to grep, diff, verify versions/hashes | Save artifacts in text/machine-readable form |

## 23. Quality checklist before publishing a report

**Hypotheses and tests**

- [ ] Exact class name, method name, and **descriptor** included.
- [ ] H1–Hn have PASS/FAIL criteria before execution.
- [ ] Baseline differs from treatment only in the intended variable.
- [ ] Same-class control and separate control class included where appropriate.
- [ ] Inputs cover normal result and at least one error path if relevant.
- [ ] Expected values are not altered after seeing actuals without stating a reason.

**Bytecode evidence**

- [ ] Original/transformed bytes from the same build are preserved.
- [ ] Exact opcode/owner/name/descriptor checked.
- [ ] Instruction position checked and no duplicate hook created.
- [ ] Unselected methods verified to have no hook.
- [ ] `javap` and independent structural program agree.
- [ ] SHA-256/size recorded as provenance, not used in place of semantic assertions.

**Execution results and environment**

- [ ] JDK/compiler, version, build flags, classpath/agent flags are clear.
- [ ] JVM `-Xverify:all` run, stderr and exit code recorded.
- [ ] Baseline and treatment have real stdout, order not manually altered.
- [ ] Return value and exception type checked on the same inputs.
- [ ] Helper/class loader/module errors considered and reported if untested.
- [ ] If not yet runnable, use `BLOCKED`/`NOT TESTED` instead of `PASS`.

**Limitations and honesty**

- [ ] Limitations on JDK, method kinds, retransform, and class loaders are clear.
- [ ] Counts are not confused with durations or end-to-end tracing.
- [ ] Class verification is not equated with production safety.
- [ ] Performance claims made only with proper benchmarking.
- [ ] Next tests listed with concrete acceptance criteria.
- [ ] Others can reproduce from the described source and commands.

## 24. Self-check questions

1. Why is `agent.ready=true` not enough to prove `Probe.hit()` was inserted?
2. What conditions would falsify hypothesis H1?
3. Why is `PriceService.label()` a useful negative control right inside the transformed class?
4. Why is a separate `ControlService` class needed even though `label()` already exists?
5. Which variables did the experiment keep identical between baseline and treatment?
6. Why must **both class files** (original and transformed) be kept instead of just one?
7. What does `javap` show that runtime stdout alone cannot prove?
8. Why is checking `INVOKESTATIC + owner + name + descriptor` better than searching for the string `"Probe"`?
9. Why does `Verification=PASS` from an independent tool increase confidence compared to a log printed by the transformer?
10. Do two different SHA-256 hashes prove that exactly one instruction was inserted?
11. Why does `probe.hits=2` not prove that both calls returned normally?
12. Why does `error=IllegalArgumentException` not prove the exception object/stack trace is identical in every detail?
13. What does `-Xverify:all` prove and what does it **not** prove?
14. Why must JDK 24 be stated explicitly instead of writing "Java 17+" generically?
15. What risks arise when the helper cannot be resolved from a custom class loader?
16. Why do constructors or native methods require different tests/designs than `price(int)`?
17. Why is `removeTransformer` not "turning off all existing hooks"?
18. In a report, when a Java compiler is missing, should `BLOCKED` or `PASS` be used?
19. If the helper itself throws an `Error`, does hypothesis H3 still hold?
20. When wanting to claim "overhead under 2%", what additional experimental design and data are needed?

**Conclusion:** A good Java agent report must state **falsifiable hypotheses**, provide **original/transformed bytecode evidence**, **runtime results with baseline and controls**, and **scope limitations**. In the experiment run on JDK 24.0.2, the agent inserted exactly one `INVOKESTATIC Probe.hit:()V` into `PriceService.price(int)`, the checked outputs/exceptions remained unchanged, and the helper count changed from 0 to 2. `javap`, the independent verifier, and JVM `-Xverify:all` were consistent. Those results support H1–H4 **for the experimental scope**, without automatically turning a prototype into a comprehensively safe production agent.

### Official references

- [JDK 24 — ClassFileTransformer and transform contract](https://docs.oracle.com/en/java/javase/24/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [JDK 24 — Instrumentation.addTransformer](https://docs.oracle.com/en/java/javase/24/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [JDK 24 — ClassFile: parse and transformClass](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html)
- [JDK 24 — ClassTransform.transformingMethodBodies](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassTransform.html)
- [JDK 24 — CodeTransform / ClassFileTransform: atStart and with](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/CodeTransform.html)
- [JDK 24 — InvokeInstruction / Opcode](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/instruction/InvokeInstruction.html)
- [JEP 484 — Class-File API standardized in JDK 24](https://openjdk.org/jeps/484)
