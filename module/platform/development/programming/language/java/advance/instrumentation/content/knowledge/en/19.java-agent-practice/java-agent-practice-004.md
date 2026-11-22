# Using the Class-File API to Insert a Helper Call and Verify Bytecode

## 1. Experiment Goal and Results to Prove

This practice belongs to the **Agent Experiments** group of **Java Advance - instrumentation**. We will create a **real Java agent** using the **standard Class-File API of JDK 24** to add an `invokestatic` call to a helper at the beginning of a Java method, then verify it across **three layers**: analyzing bytes directly inside the transformer, independently analyzing the transformed class file, and running the application with the JVM bytecode verifier.

In this lesson, the application has the method:

~~~java
package demo.app;

public final class Greeter {
    public static String greet(String name) {
        return "Hello " + name;
    }
}
~~~

Without the agent, `Greeter.greet("Java")` simply concatenates strings and returns `Hello Java`. When run with the agent:

~~~text
Before transformation:
    Greeter.greet(String)
        -> process name
        -> return "Hello " + name

ClassFileTransformer receives class-file bytes
        |
        v
ClassFile.of().parse(...)
        |
        v
ClassTransform.transformingMethodBodies(...)
        |
        v
CodeBuilder.invokestatic(Probe.hit, ()V)
        |
        v
ClassFile.transformClass(...) -> new byte[]
        |
        v
JVM verifier and class loading
        |
        v
After transformation:
    Greeter.greet(String)
        -> invokestatic demo.agent.Probe.hit:()V
        -> process name
        -> return "Hello " + name
~~~

We will prove:

1. **Without the agent:** the helper is not called; the method still returns the correct business result.
2. **With the agent:** the transformer is called **before `demo.app.Greeter` is defined**, produces new class bytes, and verifies exactly **one `Probe.hit()` call** in `greet`.
3. **Actual execution:** the helper increments the counter exactly once, and the return value of `greet` is unchanged.
4. **Independent bytecode verification:** `javap -c -p` shows a new `invokestatic` instruction at offset 0 of `greet`; the Class-File API-based verification program compares **original=0** and **transformed=1**.
5. **JVM verification:** running the application with `-Xverify:all` succeeds with no `VerifyError`.

**Intentional scope:** only transforms a very simple `greet` method, with no try/catch, not a constructor, and no overloads. The goal is to understand and independently verify a helper-call insertion operation, **not** to claim to have built a general-purpose agent for all production bytecode patterns.

## 2. Environment Requirements: JDK 24 Is Mandatory for the Source Code in This Lesson

**The standard `java.lang.classfile` Class-File API is available starting in JDK 24** (JEP 484). In JDK 22/23, the API went through a preview phase with potential differences; **Java 17 or 21 cannot directly compile code using the standard `java.lang.classfile` shown here**.

| Component | Requirement for the experiment |
| --- | --- |
| JDK to compile | **JDK 24**, including `javac` and `jar` |
| JVM to run application and agent | **JDK 24** |
| Class-File API | `java.lang.classfile` in `java.base` |
| Instrumentation API | `java.lang.instrument` in module `java.instrument` |
| Reference docs/API | Java SE 24 Javadoc, JEP 484 |
| External libraries | **Not needed** (no ASM, Byte Buddy, or Javassist) |
| Agent loading mechanism | `-javaagent:demo-agent.jar` at JVM startup |
| Class-file verification | `javap` and Java Class-File API |
| Preview flag | **No `--enable-preview` needed on JDK 24** |

Check:

~~~bash
java -version
javac -version
jar --help
javap -help
~~~

The commands above are environment checks, not fixed stdout. If `javac` reports a JDK lower than 24, switch to JDK 24 before running the code. For example, `--release 24` ensures the compiler emits bytecode targeting Java 24, class-file major version **68**.

**Tested:** all Java programs in this lesson were compiled using **Zulu/OpenJDK 24.0.2** with `javac --release 24`, run with `-javaagent` and `-Xverify:all`. The results recorded in the following sections are experimental results, not speculated output.

## 3. Class-File API Objects to Know

| API / Type | Role |
| --- | --- |
| `ClassFile.of()` | Creates a class-file read/write/transform context with default options |
| `ClassFile.parse(byte[])` | Reads a byte array into a `ClassModel` |
| `ClassModel` | Class model containing methods/fields/attributes in a queryable form |
| `MethodModel` | Model of a method; `methodName()`, `methodType()`, `code()` |
| `ClassTransform` | Instructions for building a new class from class elements |
| `ClassTransform.transformingMethodBodies(filter, codeTransform)` | Transforms only the bodies of methods matching the filter |
| `CodeTransform` | Processes a stream of `CodeElement`; can add/remove/replace elements |
| `CodeTransform.ofStateful(supplier)` | Creates a **new stateful transform for each traversal** |
| `CodeBuilder.invokestatic(owner, name, type)` | Emits an instruction to invoke a static method |
| `ClassFile.transformClass(model, transform)` | Writes a **new class-file `byte[]`** from a model and a transform |
| `CodeModel.elementStream()` | Iterates over code elements to inspect instructions |
| `InvokeInstruction` / `Opcode.INVOKESTATIC` | Accurately identifies the helper invocation instruction |

How the layers connect:

~~~text
byte[] classfileBuffer
     -> ClassFile.of().parse(...)
     -> ClassModel
        -> MethodModel ("greet")
           -> CodeModel
              -> CodeElement: load, invokedynamic, return...
     -> ClassTransform
        -> CodeTransform
           -> CodeBuilder.invokestatic(...)
           -> CodeBuilder.with(originalElement)
     -> ClassFile.transformClass(...)
     -> byte[] transformedBytes
~~~

The model is **immutable at the API level**, but **parsing is performed lazily**, so do not assume that calling `parse` once will detect all class-file errors. The Java 24 Javadoc notes that some accessors may throw `IllegalArgumentException` when encountering malformed data, and lazily accessed models may not be thread-safe for uncontrolled sharing. In this demo, each callback has its own model and processes it sequentially within the callback itself.

### 3.1. Difference from Manual Byte-Array Manipulation

If you only scan a byte array and insert a few `invokestatic` bytes at an arbitrary position, you have to manually manage:

- `Code` length and `attribute_length`;
- constant-pool entries for owner, method name, and descriptor;
- jump instruction offsets;
- exception table ranges;
- `StackMapTable`, line numbers, and local variable metadata;
- class-file format limits and the JVM verifier.

The Class-File API supports **structural modeling and reconstruction**, reducing the risk of offset/constant-pool mistakes. However, the author still must understand **bytecode semantics**, instruction ordering, entry points, stack effects, and loader/module boundaries. The API does not automatically make every code insertion valid.

## 4. Test Project Structure

~~~text
classfile-agent-demo/
  agent-src/
    demo/agent/
      ClassFileAgent.java
      Probe.java
  app-src/
    demo/app/
      Greeter.java
      Main.java
  tools-src/
    VerifyBytecode.java
  MANIFEST.MF
  agent-classes/             (created at build time)
  app-classes/               (created at build time)
  tool-classes/              (created at build time)
  demo-agent.jar             (created at build time)
  transformed/
    demo/app/Greeter.class   (written by agent for verification in demo)
~~~

**Separation of responsibilities:**

- `ClassFileAgent` receives `Instrumentation` via `premain` and registers `ClassFileTransformer`.
- `Probe` is a helper with a static `hit()` method and a counter. Classes transformed by the agent must **see** the helper at runtime.
- `Greeter` is the target class; its source code **contains no** `Probe.hit()` call.
- `Main` is the test runner program, using the helper's counter to verify the result.
- `VerifyBytecode` is an **independent** tool that reads the original and transformed versions without relying on data reported by the transformer.

The `transformed/...` file is written **solely for experimental inspection with `javap`**, not as a requirement of `ClassFileTransformer`. In production, **do not perform synchronous file I/O inside a class-load callback** as in this example.

## 5. Helper: `Probe.hit()` Is the Method Inserted into Bytecode

**File `agent-src/demo/agent/Probe.java`**

~~~java
package demo.agent;

import java.util.concurrent.atomic.AtomicInteger;

public final class Probe {
    private static final AtomicInteger HITS = new AtomicInteger();

    public static void hit() {
        System.out.println("hook.hit=" + HITS.incrementAndGet());
    }

    public static int hits() {
        return HITS.get();
    }
}
~~~

The actual method signature is:

~~~text
Owner (internal name): demo/agent/Probe
Method name:           hit
JVM descriptor:        ()V
Opcode:                INVOKESTATIC
~~~

`()V` means **no parameters and returns `void`**. No value is left on the operand stack by `Probe.hit()` after it returns normally. This keeps the example readable: the new instruction needs no `aload`, no changes to local variables, and no handling of `greet`'s return value.

`AtomicInteger` ensures the count works accurately when multiple threads call the helper concurrently, but `System.out.println` directly inside the hook is **for demo purposes only**. In a high-load agent, synchronous logging on every method entry causes overhead and risks self-instrumentation/reentrancy. Production should use a minimal helper, bounded queues, sampling, and safeguards when an exporter fails.

**Note:** a helper is not implicitly a "special JVM function." It is a normal Java class/method. If the target cannot resolve `demo.agent.Probe`, the inserted bytecode may throw `NoClassDefFoundError` or a linkage error at runtime.

## 6. Target Class Without Helper Calls in Source

**File `app-src/demo/app/Greeter.java`**

~~~java
package demo.app;

public final class Greeter {
    public static String greet(String name) {
        return "Hello " + name;
    }
}
~~~

**File `app-src/demo/app/Main.java`**

~~~java
package demo.app;

import demo.agent.Probe;

public final class Main {
    public static void main(String[] args) {
        System.out.println("result=" + Greeter.greet("Java"));
        System.out.println("helper.hits=" + Probe.hits());
    }
}
~~~

The `Greeter` source **does not import the helper**, has no `Probe.hit()`, and has no `hook.hit=...` print statement. When running with the agent, the call can only come from the **transformed class file** (within the scope of this demo).

`Main` imports `Probe` **only to read the counter after the test call**. It does not call `hit()`. When run without the agent, `helper.hits=0`; when run with the agent, the expected count is 1.

This is a suitable example for before/after comparison because the `greet` body is very short and the business result is deterministic. For target methods with overloads, constructors, complex branching bytecode, or try/catch, separate filtering conditions and testing are needed.

## 7. Agent Using the Class-File API to Insert `invokestatic`

**File `agent-src/demo/agent/ClassFileAgent.java`** — complete class compiled and run on JDK 24:

~~~java
package demo.agent;

import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassTransform;
import java.lang.classfile.CodeBuilder;
import java.lang.classfile.CodeElement;
import java.lang.classfile.CodeTransform;
import java.lang.classfile.instruction.InvokeInstruction;
import java.lang.constant.ClassDesc;
import java.lang.constant.MethodTypeDesc;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.ProtectionDomain;

public final class ClassFileAgent {
    private static final String TARGET = "demo/app/Greeter";
    private static final ClassDesc HOOK = ClassDesc.of("demo.agent.Probe");
    private static final MethodTypeDesc NO_ARGS_VOID =
            MethodTypeDesc.ofDescriptor("()V");

    public static void premain(String args, Instrumentation inst) {
        inst.addTransformer(new HookTransformer(), false);
        System.out.println("agent=installed");
    }

    private static final class HookTransformer implements ClassFileTransformer {
        @Override
        public byte[] transform(ClassLoader loader, String className,
                Class<?> redefining, ProtectionDomain domain, byte[] bytes) {
            if (!TARGET.equals(className)) return null;

            ClassFile cf = ClassFile.of();
            CodeTransform prepend = CodeTransform.ofStateful(() ->
                    new CodeTransform() {
                boolean first = true;

                @Override
                public void accept(CodeBuilder out, CodeElement element) {
                    if (first) {
                        out.invokestatic(HOOK, "hit", NO_ARGS_VOID);
                        first = false;
                    }
                    out.with(element);
                }
            });

            byte[] changed = cf.transformClass(cf.parse(bytes),
                    ClassTransform.transformingMethodBodies(
                            method -> method.methodName()
                                    .equalsString("greet"),
                            prepend));

            long hits = cf.parse(changed).methods().stream()
                    .filter(method -> method.methodName()
                            .equalsString("greet"))
                    .flatMap(method ->
                            method.code().orElseThrow().elementStream())
                    .filter(e -> e instanceof InvokeInstruction i
                            && i.owner().asSymbol().equals(HOOK)
                            && i.name().equalsString("hit"))
                    .count();

            System.out.println("agent.transform=" + className);
            System.out.println("agent.hookCount=" + hits);
            if (hits != 1) {
                throw new AssertionError(
                        "Unexpected probe count: " + hits);
            }

            try {
                Path destination =
                        Path.of("transformed/demo/app/Greeter.class");
                Files.createDirectories(destination.getParent());
                Files.write(destination, changed);
            } catch (java.io.IOException ex) {
                throw new IllegalStateException(
                        "Demo dump failure", ex);
            }
            return changed;
        }
    }
}
~~~

**Exact APIs used in the test:**

- `ClassDesc.of("demo.agent.Probe")` takes a **dot-separated binary name**, not the slash-separated internal name string from the callback.
- `MethodTypeDesc.ofDescriptor("()V")` creates the static method call descriptor; the descriptor must match the `Probe.hit()` method **exactly**.
- `ClassTransform.transformingMethodBodies(predicate, prepend)` selects methods by `methodName` and transforms only the **`Code`** of that method.
- `CodeTransform.ofStateful(...)` creates a transform with local state per traversal. The `first` variable ensures the call is inserted **only once at the beginning**.
- `CodeBuilder.invokestatic(HOOK, "hit", NO_ARGS_VOID)` emits the `INVOKESTATIC` instruction along with the symbolic reference to the helper.
- `out.with(element)` passes **every original code element** through the builder. Omitting this line would drop them, leaving the method without its intended body.
- `cf.transformClass(cf.parse(bytes), ...)` produces a **new byte array**; the code does not mutate the input `bytes`.
- The `cf.parse(changed)` and `InvokeInstruction` lines use the same Class-File API to verify there is exactly one helper invocation.
- `Files.write(...)` only dumps the **post-transformation** class file to a test path so `javap`/independent verification can inspect it.

### 7.1. Why Does the Transformer Filter the Class Name Before Parsing Bytes?

`className` in the callback uses an **internal name**, so match:

~~~java
if (!"demo/app/Greeter".equals(className)) {
    return null;
}
~~~

This is a **code snippet extracted from the transformer**. Effects:

1. Avoids parsing every JDK/application/agent class; reduces CPU and allocations during class loading.
2. Avoids self-instrumenting `demo.agent.ClassFileAgent` and `demo.agent.Probe`, which would cause recursion or circular loading.
3. Keeps the experiment's scope to **one specific class**, avoiding accidental interference with other class loaders.
4. `className` can be `null` in certain situations; `"literal".equals(className)` remains safe.

**Do not replace slashes with dots when comparing against `className`**. However, `ClassDesc.of` requires dot-separated binary name syntax. These are two different API surfaces.

### 7.2. Why Must Inserting a Call Use the Exact Descriptor?

`INVOKESTATIC` references a specific method by **owner + name + descriptor**, not just name. In this lesson:

~~~text
demo/agent/Probe.hit:()V
    |
    +-- ClassDesc: demo.agent.Probe
    +-- Name: hit
    +-- MethodTypeDesc: ()V
~~~

If the real helper is `hit(String)` but the transform still emits `()V`, the JVM may report `NoSuchMethodError` at linkage time because no method has that descriptor. If the helper is an instance method but the transform emits `invokestatic`, `IncompatibleClassChangeError` may occur. If the helper is not visible from the target's defining loader, `NoClassDefFoundError` may occur.

The example intentionally takes no arguments to avoid having to push `this`/arguments onto the operand stack. If you want to pass the method name or a trace ID, you must design stack effects for `ldc`/`aload`/`invoke...` matching the opcode and descriptor.

### 7.3. Why Use `CodeTransform.ofStateful`?

A `CodeTransform` can be reused when processing multiple code bodies. If a `boolean first` field were held on a shared transform, inserting once in method A would prevent method B from being instrumented. `ofStateful` provides a fresh transform for each traversal per the API contract.

In this experiment there is only one `greet`, but writing it this way avoids forming a bad habit when later expanding the matcher to multiple methods.

Additionally, when processing the first code element, the builder is instructed to emit `invokestatic` **before** forwarding the original code element. On the simple `Greeter.greet`, the bytecode verifier accepts it and `javap` confirms this is the **first instruction at offset 0**.

**Do not generalize arbitrarily:** inserting before the first instruction may not be appropriate for constructors `<init>` (uninitialized `this` constraints), code with try/catch/labels, synchronized methods, or complex stack-map frames. A production agent must handle safe insertion points, labels/ranges, stack effects, and verification for each method type.

### 7.4. Why Not Transform Every Method in the Class?

`ClassTransform.transformingMethodBodies(...)` applies only to methods that have **`Code`** and satisfy the predicate. In this lesson, the predicate checks **`methodName()=="greet"`**; the demo class has only a single `greet`.

For production overloads, filter by **descriptor** as well:

~~~java
method -> method.methodName().equalsString("greet")
        && method.methodType()
                .equalsString("(Ljava/lang/String;)Ljava/lang/String;")
~~~

This is a **Java predicate snippet** used inside `ClassTransform.transformingMethodBodies`, not a standalone program. It selects only the exact `greet(String):String` signature rather than every overload with the same name. You should also exclude `<init>`, `<clinit>`, synthetic/bridge methods, or native/abstract methods depending on your goal.

### 7.5. Writing Files in the Transformer Is Only for This Lesson

The test version writes `transformed/demo/app/Greeter.class` directly inside the callback. In real products, avoid:

- Disk writes, network calls, heavy loggers, or reflective class loading directly inside the transformer;
- Naming dump files with a fixed class name if multiple class loaders define classes with the same name;
- Letting quota/filesystem issues break business results;
- Allocating/dumping every class file, causing unbounded heap/disk growth.

Dumping can be enabled in a dedicated test/debug environment, using loader/session-scoped filenames, or verified with the Class-File API directly on the new bytes and unit tests. **The transformer contract only requires returning a valid `byte[]`**; there is no requirement to create `.class` files on disk.

## 8. Manifest: JVM Calls `premain` Before `main`

**File `MANIFEST.MF`**

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.ClassFileAgent

~~~

The file needs a blank line at the end of the main attributes section. `Premain-Class` specifies the exact name of the **agent class**, not the helper or target class.

In code:

~~~java
public static void premain(String args, Instrumentation inst) {
    inst.addTransformer(new HookTransformer(), false);
    System.out.println("agent=installed");
}
~~~

This is a **snippet from the agent**; the registration call order is an experimental precondition: the target `Greeter` must **not have been loaded** before registration. `-javaagent` provides the `Instrumentation` instance; we do not instantiate this interface ourselves.

`addTransformer(..., false)` means the transformer **is not marked as retransform-capable**. The experiment only intercepts **initial class definition**, does not need `Can-Retransform-Classes: true`, does not call `retransformClasses`, and does not need dynamic attach.

Do not confuse `-javaagent:...` with `-agentlib` (native JVMTI) or `-cp`. The JVM loads the agent JAR at startup; the demo's runtime classpath also includes the agent JAR to ensure `Probe` is accessible from the application.

## 9. Build and Run Commands on Linux/macOS

Create the directory tree according to Section 4, then run from the **root directory `classfile-agent-demo`**:

~~~bash
mkdir -p agent-classes app-classes tool-classes

javac --release 24 -d agent-classes \
  agent-src/demo/agent/ClassFileAgent.java \
  agent-src/demo/agent/Probe.java

jar --create --file demo-agent.jar \
  --manifest MANIFEST.MF \
  -C agent-classes .

javac --release 24 -cp demo-agent.jar -d app-classes \
  app-src/demo/app/Greeter.java \
  app-src/demo/app/Main.java

# Baseline without agent:
java -cp "app-classes:demo-agent.jar" demo.app.Main

# Transform the real class, and verify with JVM:
java -Xverify:all -javaagent:demo-agent.jar \
  -cp "app-classes:demo-agent.jar" demo.app.Main
~~~

**Note:** `:` separates entries in `-cp` on Unix, whereas on Windows it is a **semicolon** `;`. The file `transformed/demo/app/Greeter.class` only appears after **the run with the agent**. All commands with `\` line continuations in this block use Bash syntax.

### 9.1. Equivalent Commands on Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force agent-classes, app-classes, tool-classes | Out-Null

javac --release 24 -d agent-classes agent-src/demo/agent/ClassFileAgent.java agent-src/demo/agent/Probe.java

jar --create --file demo-agent.jar --manifest MANIFEST.MF -C agent-classes .

javac --release 24 -cp demo-agent.jar -d app-classes app-src/demo/app/Greeter.java app-src/demo/app/Main.java

java -cp "app-classes;demo-agent.jar" demo.app.Main

java -Xverify:all -javaagent:demo-agent.jar -cp "app-classes;demo-agent.jar" demo.app.Main
~~~

Commands were tested in PowerShell with JDK 24. `jar` must contain the `.class` files of `ClassFileAgent`, the transformer's nested class, and `Probe`; using `-C agent-classes .` packages the entire compiled classes directory.

Do **not** run `jar --create` before `javac` compiles the agent classes. If the manifest has an incorrect `Premain-Class`, the JVM may fail to initialize the agent and not enter the application as intended.

## 10. Stdout: Comparing Without Agent and With Agent

### 10.1. Baseline Without Agent

Run:

~~~bash
java -cp "app-classes:demo-agent.jar" demo.app.Main
~~~

On PowerShell, replace `:` in the classpath with `;`. Actual output:

~~~text
result=Hello Java
helper.hits=0
~~~

**Key point:** merely putting `demo-agent.jar` on the **classpath** does not run `premain`. The `Probe` class can be loaded when `Main` reads the counter, but there is no `Probe.hit()` call inside `Greeter`, so `hits=0`.

### 10.2. When Running With the Real Java Agent

Run:

~~~bash
java -Xverify:all -javaagent:demo-agent.jar -cp "app-classes:demo-agent.jar" demo.app.Main
~~~

Exact output on Zulu/OpenJDK 24.0.2:

~~~text
agent=installed
agent.transform=demo/app/Greeter
agent.hookCount=1
hook.hit=1
result=Hello Java
helper.hits=1
~~~

Line-by-line explanation:

1. `agent=installed`: `premain` runs before application `main`.
2. `agent.transform=demo/app/Greeter`: the callback matches the exact class name.
3. `agent.hookCount=1`: after building the new bytes, the agent itself parses the output and finds **one** `InvokeInstruction` calling the helper.
4. `hook.hit=1`: when `Greeter.greet` runs, the new instruction actually calls the static helper.
5. `result=Hello Java`: the business result of the method is preserved.
6. `helper.hits=1`: the application confirms the counter incremented exactly once.

There is no `VerifyError` when running with `-Xverify:all`. This is evidence that **the bytecode passed the JVM verifier for this test**. It does not automatically guarantee that every class on every JVM or every code variant is safe.

### 10.3. Why Does Stdout Have `hook.hit=1` Before `result=...`?

In `Main`, the expression:

~~~java
System.out.println("result=" + Greeter.greet("Java"));
~~~

Java must evaluate `Greeter.greet("Java")` **before** calling `println` to print the result string. Because the helper was inserted at the beginning of `greet`, `Probe.hit()` prints the hook line first; then `greet` returns, and `Main` prints the result line.

This print order is only an observation of a **single-threaded test**, not a substitute for counting instructions in the class file.

## 11. Verifying With `javap` on Both Class Files

After running the agent, still in the project root directory:

~~~bash
javap -classpath app-classes -c -p demo.app.Greeter
javap -classpath transformed -c -p demo.app.Greeter
~~~

The first command reads the **original bytes produced by `javac`**, and the second reads the **new bytes dumped by the transformer**.

### 11.1. The `greet` Section Before Transformation

Experimental excerpt on JDK 24:

~~~text
public static java.lang.String greet(java.lang.String);
  Code:
     0: aload_0
     1: invokedynamic #7,  0
     6: areturn
~~~

Some `javap` comment details are omitted to focus on the opcodes. `invokedynamic` here is how the compiler performs string concatenation; different JDKs/compilers may emit equivalent instructions differently. **Main verification point:** there is no `invokestatic demo/agent/Probe.hit:()V` yet.

### 11.2. The `greet` Section After Transformation

Experimental excerpt:

~~~text
public static java.lang.String greet(java.lang.String);
  Code:
     0: invokestatic  #37     // Method demo/agent/Probe.hit:()V
     3: aload_0
     4: invokedynamic #7,  0
     9: areturn
~~~

**Clearly visible changes:**

- The new instruction is inserted at **offset 0**.
- JVM opcode `INVOKESTATIC` calls `demo/agent/Probe.hit:()V`.
- The original `aload_0` instruction shifted from offset 0 to offset 3; the concatenation/return instructions remain intact.
- Constant-pool index `#37` is a **detail of the tested class build**; it may differ if the compiler, constant pool, or options change. Do not write tests hardcoding `#37`.
- Subsequent offsets shift according to the size of the new instruction. Do not manually add offsets for classes with branches/exception tables/stackmaps.

The fact that `javap` displays the call **inside `greet`** shows this is a bytecode transformation of the target class, not just a `System.out.println` in `premain`.

## 12. Independent Verification Using the Class-File API

To avoid relying solely on `agent.hookCount=1` (self-reported by the transformer), create another program that **reads both class files from the filesystem** and counts the specific instruction.

**File `tools-src/VerifyBytecode.java`**

~~~java
import java.lang.classfile.ClassFile;
import java.lang.classfile.Instruction;
import java.lang.classfile.Opcode;
import java.lang.classfile.MethodModel;
import java.lang.classfile.instruction.InvokeInstruction;
import java.lang.constant.ClassDesc;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public final class VerifyBytecode {
    private static final ClassDesc HELPER =
            ClassDesc.of("demo.agent.Probe");

    private static void report(String label, Path file) throws Exception {
        MethodModel greet = ClassFile.of().parse(Files.readAllBytes(file))
                .methods().stream()
                .filter(m -> m.methodName().equalsString("greet"))
                .findFirst().orElseThrow();

        List<Instruction> instructions = greet.code().orElseThrow()
                .elementStream().filter(e -> e instanceof Instruction)
                .map(e -> (Instruction) e).toList();

        long calls = instructions.stream()
                .filter(VerifyBytecode::isHelperCall).count();

        System.out.println(label + ".firstHook="
                + isHelperCall(instructions.getFirst()));
        System.out.println(label + ".helperCalls=" + calls);
    }

    private static boolean isHelperCall(Instruction instruction) {
        return instruction instanceof InvokeInstruction call
                && call.opcode() == Opcode.INVOKESTATIC
                && call.owner().asSymbol().equals(HELPER)
                && call.name().equalsString("hit");
    }

    public static void main(String[] args) throws Exception {
        report("original",
                Path.of("app-classes/demo/app/Greeter.class"));
        report("transformed",
                Path.of("transformed/demo/app/Greeter.class"));
    }
}
~~~

**Run commands:**

~~~bash
javac --release 24 -d tool-classes tools-src/VerifyBytecode.java
java -cp tool-classes VerifyBytecode
~~~

**Exact tested stdout:**

~~~text
original.firstHook=false
original.helperCalls=0
transformed.firstHook=true
transformed.helperCalls=1
~~~

`firstHook` checks only whether the **first executable instruction** (filtering out pseudo-elements like line/label) is the helper invocation. `helperCalls` counts all `INVOKESTATIC` instructions with the exact **owner + name** in `greet`. For the demo class with only one non-overloaded `hit()`, this check is appropriate. For a production agent, also check the **descriptor** `()V`/`i.typeSymbol()` to avoid confusing overloads with the same name.

### 12.1. Why Check the Opcode Instead of Just Searching for the String `Probe`?

A class can contain the helper's name in its constant pool due to metadata, strings, or other code, yet **never actually invoke the helper**. Iterating `InvokeInstruction` and verifying:

~~~text
opcode = INVOKESTATIC
owner  = demo.agent.Probe
name   = hit
type   = ()V
~~~

is much closer to the executed instruction than searching for the string `"Probe"` in bytes or looking up the name in the constant pool.

For stricter tests, verify:

- Exactly **one** `INVOKESTATIC Probe.hit:()V` in the target method.
- No such call in unselected classes/methods.
- The instruction appears at the start of the selected method's code.
- The class can be verified by the JVM and run properly in a separate test JVM.
- The original bytecode remains in the correct order and semantics.
- Business method return values and exceptions are unchanged across test cases.

## 13. Why Looking Only at Stdout Is Not Enough to Verify Instrumentation

If you only see `hook.hit=1`, many causes could produce similar output:

- The helper call **was written in the source** instead of inserted by the agent.
- The agent simply printed `hook.hit=1` in `premain`.
- Another wrapper called the helper outside the target class.
- The code was already instrumented from a previous build, not at class-loading time.
- There were two helper calls, but the code only printed once due to sampling or a flag.

This experiment uses independent evidence:

| Evidence | What it establishes |
| --- | --- |
| `Greeter` source contains no `Probe.hit()` | Helper is not called from the original source |
| Baseline `helper.hits=0` | No transformation occurs when running without the agent |
| `agent.transform=demo/app/Greeter` | Agent callback matched the target class |
| Parsing new bytes and `agent.hookCount=1` | Class-file output contains one helper-call instruction |
| `javap` original vs transformed | Bytecode actually has the new opcode and shifted offsets |
| Independent `VerifyBytecode` run | Does not rely solely on the transformer's own log |
| JVM `-Xverify:all` and `result=Hello Java` | Test runs and business result is unchanged |

**Principle:** each tool verifies one layer. `javap` helps inspect instructions; the Class-File API enables precise assertions; the JVM verifier and runtime tests verify that the bytecode is viable on a specific JVM. Do not use one layer to replace all the others.

## 14. Why Inserting `invokestatic` Before the First Code Element Works Here

The `greet(String)` code:

~~~java
public static String greet(String name) {
    return "Hello " + name;
}
~~~

Is not a constructor, has no try/catch, holds no monitor, and the `hit()` helper:

- **Takes no arguments**, so no values need to be read from the stack/locals.
- **Returns `void`**, so it leaves no result on the operand stack.
- Does not alter `this` or constructor class initialization order.
- Does not interfere with jump targets or exception handlers in this simple method.

However, `invokestatic` **can have side effects and throw exceptions**. In the demo, the helper only prints and increments a counter; if the helper fails or the class cannot be resolved, the business method may not proceed. Therefore, "inserting a call before the body" does not guarantee **unchanged semantics** in all cases.

### 14.1. Some Situations Requiring Different Strategies

| Method form | Risk when inserting like the demo | Approach |
| --- | --- | --- |
| `<init>` | `this` has not finished initialization; strict verifier rules apply | Place hook at a safe point after the super/this constructor call by design |
| `<clinit>` | Reentrancy/class initialization order, helper triggers class loading | Instrument only intentionally, guard against circular initialization |
| Method with try/catch/finally | Labels, exception-handler ranges, and stack map offsets | Use transforms that control scope and test all exception paths |
| `synchronized` method | Cost/exceptions while holding monitor; logging deadlock | Non-blocking/guarded helper, check monitor lifecycle |
| Overloaded `greet` method | Filtering by name may instrument multiple signatures | Filter by descriptor as well |
| `native` or `abstract` method | **Has no `Code`** in the method itself | Do not use `transformingMethodBodies` to insert code directly |
| Bridge/synthetic | May be called automatically by compiler, causing double counting | Filter access flags and understand the call graph |
| Class defined by plugin loader | Target may not resolve the helper | Control loader/module visibility |
| JDK/core runtime class | Circularity or verifier/module constraints | Exclude and study separately |
| Retransformation | Risk of duplicate insertion, invalid schema changes | Idempotence, capabilities, and retransform testing |

For complex code, check stack slot counts, exception handlers, `StackMapTable`, class-loader-specific hierarchy resolution, and exceptional method exit paths. `ClassFile.of()` has options for stack maps/debug/line numbers and hierarchy resolvers; **defaults do not eliminate the need to test** on the classes the agent will handle.

## 15. Common Pitfalls With the JDK 24 Class-File API

### 15.1. JDK Version Error

~~~text
error: package java.lang.classfile does not exist
~~~

Common cause: compiling on JDK 17/21 or using the wrong JDK for compiler/runtime instead of JDK 24. Cannot be fixed with `--add-exports` because the package **does not exist** on older JDKs. Use JDK 24+ matching the example's API.

### 15.2. Wrong Descriptor or Unreachable Helper

- `NoSuchMethodError`: bytecode calls the wrong name/descriptor.
- `NoClassDefFoundError`: the target's loader cannot resolve the helper or its dependencies.
- `IllegalAccessError`: class/method/package/module does not permit access.
- `IncompatibleClassChangeError`: static/instance opcode does not match the method kind.
- `ExceptionInInitializerError`: helper class initialization failed.

In this lesson, the agent JAR is explicitly placed on the classpath as well so that `demo.app.Main`/`Greeter` and the helper reside in an interoperable class-loading environment. With plugin loaders or named modules, you must design loader visibility and JPMS reads/exports/opens, rather than assuming a demo configuration works for every application.

### 15.3. Forgetting `out.with(element)`

If you only emit `invokestatic` without forwarding the original code elements, the builder will not preserve the method body, potentially producing meaningless or invalid code. `CodeTransform` allows **replacing/dropping** elements by not calling `with` — that is an intentional feature of the API, not an implicit pass-through.

### 15.4. Duplicate Hooks on Re-transformation

If the transform is applied **twice** to bytes that already have the hook, two `invokestatic Probe.hit` calls may appear. The demo uses an initial-load transform and does not register for retransformation; it is not a general-purpose deduplication mechanism.

In a real agent:

1. Parse bytes and inspect before inserting (insert only if no matching pattern/marker is present).
2. Register the transformer with exact capabilities; avoid unnecessary callback invocations.
3. Do not use generic marker names that could collide with application code.
4. Test multiple transformers/agents running together, already-modified bytecode, and redefine/retransform passes.
5. Removing a transformer does not automatically strip hooks from already-loaded classes.

### 15.5. Unhandled Transform Errors Leading to Silent Uninstrumented Runs

The `ClassFileTransformer` Javadoc states that when a transformer throws an uncaught exception, the JVM **still continues processing** other transformers and attempting to load/redefine; in many situations this is equivalent to **returning `null`**. Therefore, **an error in transform does not mean the program will necessarily stop immediately**, and the system may run **without hooks**.

A production agent needs to log diagnostics via a safe channel, maintain transform-failure counters, and verify output. Do not rely on thrown exceptions as a dependable fail-fast mechanism for an agent. In the demo, independent verification and stdout help detect if the class was not modified.

### 15.6. Mutating Input Bytes or Sharing Models Across Threads

The `ClassFileTransformer` contract requires **not modifying the input `classfileBuffer` array**; return a new array if transformed. The demo uses `transformClass` to build `changed`, leaving `bytes` untouched.

`ClassModel` uses lazy parsing, and JDK 24 documentation warns that models may not be thread-safe when shared; do not cache a mutable/lazy model for concurrent access across callbacks without proper synchronization. If parallel processing is needed, create a model per task or synchronize/package a safe snapshot.

### 15.7. Synchronous Logging/I/O Inside the Transformer

In this lesson, `System.out.println` and `Files.write` serve as experimental evidence. In production this is an anti-pattern: it can cause circular class initialization, block class loading, increase allocations, and trigger recursive instrumentation. Narrow the matcher early and move heavy analysis/export out of the callback when appropriate.

## 16. Design Choices for Turning the Experiment Into a Production Java Agent

A sensible expansion roadmap:

1. **Select classes by internal name, loader, and module**, excluding `agent/helper/logger/exporter` before parsing.
2. **Select methods by name + descriptor**, avoiding constructors/native/abstract/bridge methods unless you have a dedicated strategy.
3. **Design a stable helper API with minimal dependencies**, fail-open guards, and no self-instrumentation.
4. **Design safe insertion points** for entry/exit, normal/exceptional exit, try/finally, synchronized methods, and constructors.
5. **Add idempotence checks** so duplicate hooks are not created if a class is transformed multiple times.
6. **Two-tier bytecode verification**: Class-File API instruction scans and JVM verification/runtime tests.
7. **Bound overhead**: sampling, bounded buffers, no heavy I/O in callbacks.
8. **Respect classloaders/JPMS**: the target may not see the helper; use a shared bridge or appropriate configuration.
9. **Define lifecycle**: disabling the helper is different from removing the transformer; rolling back loaded classes requires conditional retransform/redefine.
10. **Test across diverse class patterns**: methods with branches/exceptions/lambdas, packages/modules, multi-loader setups, and concurrency.

**Important note on stack maps:** the Class-File API can automatically generate or update certain structural information when rebuilding class files depending on options/defaults. However, the agent remains responsible for **correct type flow and class hierarchy**: if referenced classes are not visible to the default resolver, you must provide an appropriate hierarchy resolver or another testing/transformation strategy. Do not strip `StackMapTable` to "bypass" the verifier.

### 16.1. When to Use `javap` vs. When to Use API Verifiers?

| Method | Where is it strong? | Limitations |
| --- | --- | --- |
| `javap -c -p` | Learners immediately see opcodes/offsets/symbolic references | Text output format or constant-pool indices may change |
| `ClassFile.of().parse` + `InvokeInstruction` | Machine-checkable assertions on owner/name/opcode/type | Only a structural check; does not run on the JVM |
| `java -Xverify:all` | JVM verifies and executes the real class file | Does not prove business semantics for all inputs |
| Unit/integration tests | Verifies returns, exceptions, concurrency, performance | Covers only the cases actually tested |
| Bytecode dump diff | Makes debugging transformations clear | Should not dump every class in production |

Combine multiple layers of testing rather than treating a single `"success"` from a transformer as sufficient proof.

## 17. Practice Checklist

- [ ] Use **JDK 24** and `javac --release 24` for this Class-File API code.
- [ ] Agent has the correct `Premain-Class` and is run with `-javaagent`.
- [ ] Transformer is registered **before `Greeter` is loaded**.
- [ ] Matcher selects only `demo/app/Greeter`, not the helper/agent.
- [ ] `ClassDesc` uses `demo.agent.Probe`, while callback `className` uses `demo/app/Greeter`.
- [ ] Descriptor `()V` matches `public static void hit()`.
- [ ] `CodeTransform` inserts only once and preserves all original `CodeElement`s via `out.with(element)`.
- [ ] `transformClass` returns a new `byte[]` and does not mutate `classfileBuffer`.
- [ ] Baseline without agent has `helper.hits=0`.
- [ ] With agent, `greet` result is unchanged and the helper is called once.
- [ ] `VerifyBytecode` confirms 0 before, 1 after, and the first instruction is the helper.
- [ ] `javap` shows the new `invokestatic` instruction before `aload_0`.
- [ ] `-Xverify:all` reports no `VerifyError`.
- [ ] Do not treat fixed constant-pool indices/offsets as an API contract across compilers.
- [ ] When moving to production, remove synchronous dump/log I/O, and add idempotence, error policy, and multi-loader tests.

## 18. Self-Check Questions

1. Why does `java.lang.classfile` in this lesson require JDK 24 and cannot be compiled verbatim with Java 17?
2. What model type does `ClassFile.of().parse(bytes)` return, and what data type does `ClassFile.transformClass` return?
3. Why does `CodeBuilder.invokestatic` need both `ClassDesc` and `MethodTypeDesc`?
4. Why is `"demo/app/Greeter"` used in the matcher while `ClassDesc.of("demo.agent.Probe")` uses dots?
5. What happens if `out.with(element)` is omitted from `CodeTransform`?
6. Why is `CodeTransform.ofStateful` useful even when the demo instruments only one method?
7. What does `-Xverify:all` prove, and what does it not yet prove?
8. Why can `Main` import `Probe` to read the counter while `Greeter` does not need to import the helper in its source?
9. What instruction do the before/after `javap` outputs show added at offset 0?
10. Why should you not write an assertion that the helper's constant-pool index is always `#37`?
11. Why can a failing callback allow the JVM to keep running with the class uninstrumented as expected?
12. If you wanted to instrument two different `greet` overloads, how would you change the predicate?
13. Why should the demo's insertion point not be mechanically applied to `<init>` constructors?
14. Why is a helper with `System.out.println` fine for a demo but unsuitable for an agent measuring millions of calls/s?
15. Try changing `Greeter.greet` into a method with branches and exceptions: what additional bytecode tests are needed?
16. If a class defined by a plugin loader cannot resolve `demo.agent.Probe`, what error might appear?
17. If you want to instrument an already-loaded class, why must you study `retransformClasses` and duplicate insertion?
18. Why does the independent `VerifyBytecode` program increase confidence compared to only reading `agent.hookCount`?
19. Can a `native` method without `Code` use `transformingMethodBodies` to add JVM instructions directly into the native body?
20. When moving to production, what step ensures application state is not broken if the helper or exporter fails?

**Conclusion:** The experiment successfully created **a real Java agent with the JDK 24 Class-File API**: `ClassFile.parse` reads class-file bytes, `ClassTransform.transformingMethodBodies` selects `greet`, `CodeBuilder.invokestatic` inserts `Probe.hit()` before the original instructions, and `ClassFile.transformClass` returns the new bytes to the JVM. The original version has **0** helper calls; the new version has **1**, and the new call is proven by `javap`, an independent Class-File API checker, and execution under `-Xverify:all`. Keep the distinction clear between **one specific verified demo** and **a general-purpose production agent**: constructors/exception flow/loaders/modules/concurrency/idempotence still require dedicated design and testing.

### Official Documentation

- [JDK 24 — java.lang.classfile package: parse/build/transform models](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/package-summary.html)
- [JDK 24 — ClassFile: parse and transformClass](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html)
- [JDK 24 — ClassTransform: transformingMethodBodies](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassTransform.html)
- [JDK 24 — CodeTransform: ofStateful](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/CodeTransform.html)
- [JDK 24 — CodeBuilder: invokestatic](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/CodeBuilder.html)
- [JDK 24 — InvokeInstruction and Opcode](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/instruction/InvokeInstruction.html)
- [JDK 24 — ClassFileTransformer contract](https://docs.oracle.com/en/java/javase/24/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [JEP 484 — Class-File API standardized in JDK 24](https://openjdk.org/jeps/484)
