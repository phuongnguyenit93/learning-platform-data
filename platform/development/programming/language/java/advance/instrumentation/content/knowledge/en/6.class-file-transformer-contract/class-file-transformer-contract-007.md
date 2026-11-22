# Do Not Mutate `classfileBuffer` Provided by the JVM Directly

**Topic:** Java Advance → Instrumentation → **Transformer Contract**.

A `ClassFileTransformer` receives a `classfileBuffer` byte array representing the **input class file for the current callback**. This array is provided by the JVM or a preceding transformer; it **cannot be modified in place** by the current transformer. The Java contract explicitly specifies:

- **Do not modify any element** of `classfileBuffer`.
- If **no transformation is needed**, return **`null`**.
- If **transformation is needed**, create **a new `byte[]` array** containing a **valid class file** with the desired modifications, and return that new array.

This rule is documented in the Javadoc of `java.lang.instrument.ClassFileTransformer` and applies to **load**, **redefine**, and **retransform** callbacks alike. Violating it can corrupt the input data of subsequent transformers, produce hard-to-reproduce results, and cause class loading to fail; the fact that it sometimes "works" does not make the operation valid.

## 1. What Is `classfileBuffer` and Who Owns It?

When a Java agent is registered via `Instrumentation.addTransformer(...)`, the JVM invokes the `transform` method before applying the class definition. On Java 9+, the interface has two overloads: the traditional five-parameter version and the six-parameter version with `Module` added. Both use `byte[] classfileBuffer`.

The six-parameter form for Java 17+:

```java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer)
        throws IllegalClassFormatException {
    // Read classfileBuffer only; return null or a new output array.
    return null;
}
```

**This is only a method fragment**, not a standalone compilable program. `ClassFileTransformer`, `ProtectionDomain`, and `IllegalClassFormatException` require the corresponding imports in the implementing class.

Meaning of each parameter:

| Parameter | Meaning |
| --- | --- |
| `module` | The module containing the class being processed; with JPMS, helps identify the module context |
| `loader` | Defining `ClassLoader`; **may be `null`** for the bootstrap loader |
| `className` | Internal name such as `com/example/Service` (using `/`); check for `null` in defensive code |
| `classBeingRedefined` | `null` on a new definition; may be the `Class<?>` object during redefine/retransform |
| `protectionDomain` | Protection context of the class; not evidence that the input array is allowed to be modified |
| `classfileBuffer` | Input class file bytes, **read-only**, provided by the pipeline |

Although `byte[]` is a **mutable** type in Java, the API **does not** grant permission to mutate it. "Being able to write `array[0] = ...`" is a technical capability of Java, whereas "being allowed to call it" is governed by the **API contract**. This is an example of an *ownership convention* in an API: having an observable reference does not mean the caller owns that data region.

### 1.1. Where Does the JVM Supply the Data From?

According to the Javadoc, the data passed to the first transformer depends on the operation:

1. **New class definition:** the bytes passed to `ClassLoader.defineClass` (or the corresponding native path).
2. **Redefinition:** the bytes supplied in the `ClassDefinition` of `Instrumentation.redefineClasses`.
3. **Retransformation:** based on the original bytes or the most recent redefinition, while transformations from non-retransform-capable transformers are reapplied according to VM rules.

This does **not** guarantee that `classfileBuffer` always matches the bytes on disk or matches the bytes seen in a previous callback. When there are multiple transformers, the input of a later transformer may be the **new output** from an earlier transformer.

## 2. How Are Transformers Chained?

Suppose a class passes through three transformers A, B, and C:

```text
B0: JVM input bytes
  │
  ▼
A.transform(B0) ──► returns B1 (new array)
                      │
                      ▼
                 B.transform(B1) ──► returns null
                                      │
                                      ▼
                                 C.transform(B1) ──► returns B2 (new array)
                                                       │
                                                       ▼
                                                  JVM uses B2
```

- **A** modifies the class and returns a new `B1`. B receives `B1`, not necessarily `B0`.
- **B** changes nothing and returns `null`. The pipeline keeps the input bytes `B1` for the next step.
- **C** reads `B1` and produces `B2`; the JVM processes `B2` according to verification/class loading rules.

**If B secretly mutates `B1` in place and then returns `null`**, the result no longer accurately reflects "B made no transformation", which can break stage independence and comparability. In particular, the input array may be an array already emitted by a preceding transformer; the contract does not allow B to take ownership of that array.

When there are multiple transformers, the ordering is specified by group: non-retransform-capable Java transformers, non-retransform-capable native transformers, retransform-capable Java transformers, and then retransform-capable native transformers; within each group, registration order is preserved. During a **retransformation**, the non-retransform-capable group **is not called again** in the normal way: their previous results are reused as specified. Therefore, you must not assume that a callback always processes the original bytes from a load.

## 3. Common Incorrect Code Patterns

### 3.1. Assigning an Alias and Thinking It Was Copied

```java
byte[] output = classfileBuffer;
output[10] = 42;         // WRONG: mutating the input itself
return output;           // Also returns the same input reference
```

**Error-illustration fragment**—never use this as a real transformer. In Java, assigning a `byte[]` reference **does not copy elements**. `output == classfileBuffer` is `true`.

### 3.2. Mutating Directly and Returning `null`

```java
classfileBuffer[10] = 42;  // WRONG: violates read-only input
return null;               // Returning null does NOT legitimize the mutation
```

If you corrupt a byte of a class file, it can also cause `ClassFormatError`/`VerifyError`. Even if you happen to change a byte in a way where the program still runs, the approach still violates the contract.

### 3.3. Other Views or APIs Can Also Mutate the Same Array

```java
ByteBuffer view = ByteBuffer.wrap(classfileBuffer);
view.put(10, (byte) 42);  // WRONG: backing array is still classfileBuffer
```

This is also an **error-illustration fragment** and requires `import java.nio.ByteBuffer;` if compiled. `ByteBuffer.wrap` only creates a view over the existing array; it does not create a copy. Similarly, a helper function receiving the same array can mutate its elements even if the caller does not directly write `classfileBuffer[index]`.

### 3.4. "Do Not Mutate in Place" Does Not Mean "You Can Return Arbitrary Bytes"

```java
byte[] output = classfileBuffer.clone();
output[10] = 42;  // May produce an INVALID class file!
return output;
```

This is an **ownership-separation illustration**, not a safe class-file transformation algorithm. `clone()` keeps the input unmodified, but writing to an arbitrary offset can corrupt the constant pool, instruction operands, metadata checksums, or class structure. Generating valid output also requires a parser/writer and dedicated verification.

## 4. Minimal Java 17+ Example: Difference Between an Alias and a Copy

Save this standalone program as **`ArrayOwnershipDemo.java`**:

```java
import java.util.Arrays;

public final class ArrayOwnershipDemo {
    private ArrayOwnershipDemo() {}

    public static void main(String[] args) {
        byte[] input = {1, 2, 3};

        byte[] alias = input;
        System.out.println("alias-same=" + (alias == input));

        byte[] output = Arrays.copyOf(input, input.length);
        output[1] = 9;

        System.out.println("new-array=" + (output != input));
        System.out.println("input=" + Arrays.toString(input));
        System.out.println("output=" + Arrays.toString(output));
    }
}
```

Run with JDK 17 or later:

```bash
javac ArrayOwnershipDemo.java
java ArrayOwnershipDemo
```

**Exact** stdout:

```text
alias-same=true
new-array=true
input=[1, 2, 3]
output=[1, 9, 3]
```

The example uses an **arbitrary data array, not a class file**. It demonstrates **distinct object identity** and **not affecting the input**, but **does not prove** that modifying an arbitrary byte in a class file is valid. For a transformer, the copying principle must go hand in hand with a standards-compliant **parse → transform → emit** class-file pipeline.

## 5. Correct Pattern for `ClassFileTransformer`

At a logical level, a transformer typically has the structure:

```text
transform(metadata, classfileBuffer)
    if not a class to transform:
        return null
    read classfileBuffer with a parser, DO NOT write to input
    create a new output with a bytecode writer
    if output is valid and has modifications:
        return output
    if there are no changes:
        return null
```

This is **pseudocode** to understand the decision flow. `null` is the clearest signal when a class does not need changes; there is no need to make a pointless `clone` for every class the JVM loads. The filter should check the **exact class name, loader/module, method descriptor, and load/retransform stage**, avoiding accidentally applying to every class.

A safe approach is to use **ASM `ClassReader`** to read the input bytes and **ASM `ClassWriter`** to emit a new array via `toByteArray()`. The parser and writer ensure you work with the **class file structure** rather than overwriting bytes at guessed offsets. Even so, you must still ensure valid stack effects, frames, constant pool entries, exception handlers, and redefinition limits.

## 6. Runnable Agent Example on Java 17+: Real Transformation Without Mutating Input

This example uses **Apache Maven** and **ASM 9.7.1** to insert a log statement at the beginning of `Greeter.message()`. The transformer only reads `classfileBuffer`, generates a new output array, and self-checks that the input contents remain unchanged.

Directory structure:

```text
safe-buffer-agent/
├── pom.xml
└── src/main/java/
    ├── lesson/agent/ProbeAgent.java
    ├── lesson/agent/SafeBufferTransformer.java
    └── lesson/app/
        ├── Greeter.java
        └── Main.java
```

### 6.1. `pom.xml`

The POM below uses Java 17, ASM to read/write bytecode, and the Maven Shade Plugin to package the ASM dependency into the agent JAR. `Premain-Class` in the manifest points to the entry point executed when `-javaagent` starts.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>lesson</groupId>
    <artifactId>safe-buffer-agent</artifactId>
    <version>1.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.ow2.asm</groupId>
            <artifactId>asm</artifactId>
            <version>9.7.1</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-shade-plugin</artifactId>
                <version>3.6.0</version>
                <executions>
                    <execution>
                        <phase>package</phase>
                        <goals>
                            <goal>shade</goal>
                        </goals>
                        <configuration>
                            <createDependencyReducedPom>false</createDependencyReducedPom>
                            <transformers>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                                    <manifestEntries>
                                        <Premain-Class>lesson.agent.ProbeAgent</Premain-Class>
                                    </manifestEntries>
                                </transformer>
                            </transformers>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.2. Application Classes

Save **`src/main/java/lesson/app/Greeter.java`**:

```java
package lesson.app;

public final class Greeter {
    public String message() {
        return "hello";
    }
}
```

Save **`src/main/java/lesson/app/Main.java`**:

```java
package lesson.app;

public final class Main {
    private Main() {}

    public static void main(String[] args) {
        System.out.println("message=" + new Greeter().message());
    }
}
```

### 6.3. Agent Entry Point

Save **`src/main/java/lesson/agent/ProbeAgent.java`**:

```java
package lesson.agent;

import java.lang.instrument.Instrumentation;

public final class ProbeAgent {
    private ProbeAgent() {}

    public static void premain(String arguments, Instrumentation instrumentation) {
        instrumentation.addTransformer(new SafeBufferTransformer());
    }
}
```

This is a **startup** agent. `addTransformer` does not pass `canRetransform=true`, because the example only processes the class when it is first defined; there is no need to trigger `retransformClasses` or attach to a running JVM.

### 6.4. Transformer That Reads Input and Emits New Output

Save **`src/main/java/lesson/agent/SafeBufferTransformer.java`**:

```java
package lesson.agent;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;
import java.util.Arrays;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

public final class SafeBufferTransformer implements ClassFileTransformer {
    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {

        if (!"lesson/app/Greeter".equals(className)) {
            return null;
        }

        // Snapshot copy ONLY to prove the JVM input was not modified.
        byte[] before = Arrays.copyOf(classfileBuffer, classfileBuffer.length);

        // Reader only reads input; Writer accumulates the new class definition.
        ClassReader reader = new ClassReader(classfileBuffer);
        ClassWriter writer = new ClassWriter(
                reader, ClassWriter.COMPUTE_MAXS | ClassWriter.COMPUTE_FRAMES);

        ClassVisitor visitor = new ClassVisitor(Opcodes.ASM9, writer) {
            @Override
            public MethodVisitor visitMethod(
                    int access, String name, String descriptor,
                    String signature, String[] exceptions) {

                MethodVisitor downstream = super.visitMethod(
                        access, name, descriptor, signature, exceptions);

                if (downstream == null
                        || !"message".equals(name)
                        || !"()Ljava/lang/String;".equals(descriptor)) {
                    return downstream;
                }

                return new MethodVisitor(Opcodes.ASM9, downstream) {
                    @Override
                    public void visitCode() {
                        super.visitCode();
                        super.visitFieldInsn(
                                Opcodes.GETSTATIC,
                                "java/lang/System",
                                "out",
                                "Ljava/io/PrintStream;");
                        super.visitLdcInsn("agent-enter");
                        super.visitMethodInsn(
                                Opcodes.INVOKEVIRTUAL,
                                "java/io/PrintStream",
                                "println",
                                "(Ljava/lang/String;)V",
                                false);
                    }
                };
            }
        };

        reader.accept(visitor, ClassReader.EXPAND_FRAMES);
        byte[] output = writer.toByteArray();

        // Two separate checks: input content and output identity.
        boolean unchanged = Arrays.equals(before, classfileBuffer);
        boolean distinct = output != classfileBuffer;
        System.out.println("input-unchanged=" + unchanged);
        System.out.println("new-output-array=" + distinct);

        return output;
    }
}
```

**Why does this example comply with the contract?**

- Only processes `lesson/app/Greeter`; for other classes, returns `null` immediately without cloning the entire byte array.
- `before` is a **separate snapshot array** for comparison in this lesson; it must not be used as evidence that mutating the input is allowed. This snapshot is not needed in a production transformer if the library behavior is already controlled.
- `ClassReader` reads `classfileBuffer` without writing to it; `ClassWriter.toByteArray()` creates a **new output class file**.
- Every variable is local to the callback, with no shared scratch array across threads. `output != classfileBuffer` proves distinct object identity, while `Arrays.equals` checks that the input contents were not altered during this invocation. These two conditions are **different**.
- Inserts `getstatic System.out`, `ldc "agent-enter"`, and `invokevirtual PrintStream.println(String)` at the start of `message()`; when `println` finishes, the operand stack returns to its state at method entry.
- `COMPUTE_MAXS | COMPUTE_FRAMES` tells ASM to recompute stack limits and stack-map frames. In this simple branchless example, the code is easy to verify. For complex code, frame computation may also require an accurate class hierarchy/class loader.
- Valid-looking output can still be rejected by the verifier if a transformer emits invalid opcodes in other scenarios; `toByteArray()` must not be treated as proof of complete semantic correctness.
- `System.out.println` directly inside the transformer is only for **the lab exercise**. In a production agent, avoid heavy I/O, re-entrant class loading, locks, large allocations, or accidentally transforming core platform classes.

### 6.5. Compile, Run, and Observe Stdout

Open a terminal in the `safe-buffer-agent` directory, ensuring **JDK 17+** and Maven are available:

```bash
java -version
mvn -version
mvn -q -DskipTests package
```

The `package` command produces a JAR containing ASM and `Premain-Class` at **`target/safe-buffer-agent-1.0.jar`** per the Maven configuration above. Run **without the agent**:

```bash
java -cp target/classes lesson.app.Main
```

Exact stdout of this command:

```text
message=hello
```

Run **with the agent**:

```bash
java -javaagent:target/safe-buffer-agent-1.0.jar -cp target/classes lesson.app.Main
```

Expected stdout in a suitable JDK/ASM environment:

```text
input-unchanged=true
new-output-array=true
agent-enter
message=hello
```

The first two lines are printed by the `transform` callback while the `Greeter` class is being defined. The `agent-enter` line is printed by the **injected bytecode** in the `message` method. The last line proves the application still receives the `hello` string as expected. If loading the agent fails, the JDK may print a different error message instead of the lines above; check the manifest, JAR, classpath, and actual JDK.

**Scope of the check:** `input-unchanged=true` only indicates that the code in this callback invocation did not modify the buffer contents between the snapshot and the check. `new-output-array=true` checks object identity. They do not replace class format validation, concurrency testing, or testing across all JVMs/vendors.

### 6.6. Inspecting Bytecode After Instrumentation

```bash
javap -classpath target/classes -c -p lesson.app.Greeter
```

The command above reads the **class on disk (BEFORE)**; it does not automatically see the version transformed by the agent **in JVM memory**. In BEFORE, the `message` method has logic along the lines of `ldc "hello"` followed by `areturn`. In AFTER at runtime, the logging opcodes (`getstatic` → `ldc "agent-enter"` → `invokevirtual println(String)`) appear before the logic that returns `hello`.

If you need to compare the two versions precisely with `javap`, implement a mechanism to **dump the new `output` array to a controlled snapshot** in a test environment, then run `javap` on the AFTER file. Do not overwrite `classfileBuffer` or the BEFORE file; do not rely on `javap -c` pointing at `target/classes` to conclude that the transformer did not run. In production, avoid dumping all classes directly inside the callback without evaluating I/O impact, loader identity, and sensitive data.

## 7. Why Is `return null` the Right Choice When Unchanged?

One might think that `return classfileBuffer;` or `return classfileBuffer.clone();` also means "unchanged". However:

| Behavior | Meaning and Assessment |
| --- | --- |
| `return null;` | **Correct and preferred** when there is no transformation; tells the pipeline to keep the input as-is |
| `return output;` where `output` is a valid new array | **Correct** when a transformed result is actually produced |
| `return classfileBuffer;` | Discouraged: does not supply a new array as guided by the API and blurs ownership/meaning of "transformed" |
| `return classfileBuffer.clone();` when bytes are identical | Unnecessary: causes allocation and extra pipeline work; `null` expresses intent more clearly |
| Mutate `classfileBuffer` then `return null` | **Violates the contract** even without returning output |
| Mutate `classfileBuffer` then return a new array | **Still violates the contract** because the input was written to |
| Return a new array that is not a valid class file | **Wrong** because it violates the valid-output requirement |

`null` is a signal that **no new transformation was produced in this callback**, not a directive forcing the pipeline to discard all transformations from previously executed transformers.

## 8. What Happens When an Error Occurs in `transform`?

According to the Javadoc, if the callback throws an uncaught exception, subsequent transformers **are still called** and the load/redefine/retransform process **is still attempted**; the effect of throwing an exception is equivalent to returning `null` for that turn. If you suspect the input is not a valid class file, the API allows throwing `IllegalClassFormatException` to improve logging/debugging, but the exception **does not automatically abort the entire class loading**.

Therefore, in production you should:

- Narrow down the exact classes to instrument, and validate data types and bytecode library dependencies.
- If a class cannot be transformed due to an anticipated condition and you want to leave it unchanged, return `null` according to agent policy.
- Log errors in a structured way using a pre-initialized logging channel, while avoiding class-loading loops. Do not rely on `throw` inside a transformer as an absolute "fail closed" mechanism.
- Do not retain the `classfileBuffer` array and mutate it on another thread after the callback. The contract only allows **reading the buffer**, not transferring write permission to another thread or future callback.

**A very hard-to-trace bug:** transformer A creates a new output, transformer B mutates its input in place, and then transformer C throws an exception. When reading the logs, you might think C "corrupted the class", whereas B had already violated ownership earlier. When debugging, record traces by **class + loader + phase + transformer + appropriate hash/snapshot**, and never dump application data indiscriminately.

## 9. What Should Be Kept in Mind for Retransformation and Redefinition?

`Instrumentation.addTransformer(transformer, true)` registers a **retransformation-capable transformer** if the JVM supports it; `false` or the single-argument overload does not register it as such.

- When `retransformClasses` is called, **do not assume** the input buffer is the same array the transformer received on an earlier load. The JVM may reconstruct the pipeline according to retransform rules, with results from non-retransform-capable transformers reused.
- Every callback must still keep `classfileBuffer` immutable, create a new output when needed, and return `null` when unchanged.
- Do not use object identity of `byte[]` to detect whether a class has already been instrumented. To avoid inserting logs twice, design an idempotent transformer based on **class file contents, a valid marker, or a controlled pipeline**, while accounting for retransform policy.
- `redefineClasses`/`retransformClasses` have **restrictions on schema/hierarchy changes and valid bytecode** depending on the JVM/capabilities. A separate, well-formed byte array is not guaranteed to be permitted to redefine an already-loaded class.
- Multiple class loaders can define the same `className`. If caching state, keying solely by class name is insufficient; pay attention to module/loader identity, class unloading, and thread safety.

The ownership principle **does not change** whether the agent runs at startup with `premain` or is dynamically loaded via `agentmain`. A dynamic agent has additional attach/policy constraints, but how the callback is allowed to use `classfileBuffer` remains the same.

## 10. Transformer Review Checklist

Before putting instrumentation into a pipeline, review:

1. **Input:** only read operations on `classfileBuffer`; no `classfileBuffer[index]=...`, `System.arraycopy(..., classfileBuffer, ...)`, `ByteBuffer.wrap(classfileBuffer).put(...)`, or aliases/helpers overwriting the input.
2. **Unchanged:** if there are no actual changes, return `null`; if you already wrote content and then decide not to change, simply discard the output copy you own.
3. **Changed:** output is an independent `byte[]` containing a valid class file generated by a parser/writer; never return `classfileBuffer` directly.
4. **Right target:** check class name using `/`, method descriptor, class loader/module if multiple versions share the same name, and load/redefine/retransform phase.
5. **Valid bytecode:** opcodes, operand stack, `max_stack`, `max_locals`, `StackMapTable`, exception handlers, and branch offsets must be correct.
6. **Operational safety:** avoid blocking I/O, recursive instrumentation, static mutable buffers, holding input references too long, or logging sensitive information.
7. **Pipeline:** be aware of preceding/subsequent transformers; do not assume input is the class on disk; do not rely on ordering if the pipeline order is unspecified.
8. **Testing:** run a real application with the agent, observe behavior, compare BEFORE/AFTER class snapshots, run verifier checks, and test retransform if supported.
9. **Errors:** have a proper logging and skip strategy; know that an exception in `transform` may be treated by the JVM as equivalent to `null`.
10. **Vendor/version:** verify API/runtime and bytecode library compatibility against the target Java version (e.g., ASM and class file version) rather than assuming all JVMs behave identically.

## 11. Common Misconceptions and Answers

| Misconception | Correct Understanding |
| --- | --- |
| "`byte[]` is mutable so it can be edited in place" | Java allows it at the language level, but the **`ClassFileTransformer` contract forbids it** |
| "`byte[] copy = classfileBuffer` is a copy" | That is an **alias** to the same object; use `clone`/`Arrays.copyOf` for a real copy |
| "`ByteBuffer.wrap` isolates the data" | It shares the backing array; `put` still mutates the original array |
| "Returning `null` after mutating the input is enough" | `null` does not legitimize mutation; you must **never write to the input** |
| "Just copy and change arbitrary byte offsets" | Not mutating input is a necessary condition; output must also be a valid class file |
| "Returning `classfileBuffer` itself is optimal" | If unchanged, return `null`; if transformed, emit a new array |
| "`javap` on a `.class` file always shows the runtime agent" | The tool reads the specified source bytes; an agent may only transform in memory |
| "An exception from a transformer always halts the JVM" | The Javadoc states the JVM continues trying subsequent transformers/definition; handle errors explicitly |
| "Retransform always starts from the previous output" | The JVM has rules for reapplying/reusing transformers; do not assume buffer identity |
| "One class name corresponds to one set of bytes" | Different class loaders can define the same binary name |

## 12. Self-Check

1. **Does `byte[] local = classfileBuffer; local[0] = 1;` mutate the input?** Yes. Both variables reference the same array.
2. **If you want to skip `java/lang/String` without transforming it, what should you return?** `null`, without wasting memory cloning it.
3. **Can you mutate `classfileBuffer` and then return a different new array?** No. Mutating the input already violates the contract, even if a different object is returned.
4. **Is `Arrays.copyOf` enough to produce valid output bytecode?** No. It only creates an independent array; class file modifications must comply with the class format and verifier.
5. **Transformer B receives A's output as input. Can B mutate that array directly?** No. That is B's `classfileBuffer`, which must still be treated as read-only.
6. **If `transform` throws an error, does the JVM always block class loading?** No; per the Javadoc, the JVM still continues trying subsequent transformers and the definition process.
7. **How can you tell if a transformer mutated the input during a lab run?** Take a snapshot with `Arrays.copyOf` before the callback logic, then compare with `Arrays.equals`; this is a local check and does not replace testing all execution paths.
8. **Why does the example program print `message=hello` both before and after using the agent?** The injected bytecode adds logging while preserving the returned string; the main semantics of the method remain intact.
9. **Why check both `output != classfileBuffer` and `Arrays.equals(before, classfileBuffer)`?** The first checks that the returned array is a different object; the second checks that **the input contents were not mutated**.
10. **After `retransformClasses`, can you use an old reference to `classfileBuffer` to keep writing to it?** No. You do not own write permission in any callback; retaining a reference and writing asynchronously is also wrong.

## 13. Official Documentation

- Oracle JDK 17, **`ClassFileTransformer` API** (no-input-mutation rule, returning `null`/new array, chain/retransform/error semantics): https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- Oracle JDK 25, **`ClassFileTransformer` API** (comparing contract across newer JDKs): https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- Oracle JDK 17, **`Instrumentation` API** (registering transformers, redefine/retransform, capabilities): https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Oracle JDK 17, **`java.lang.instrument` agent package** (`premain`, `agentmain`, manifest): https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- Java Virtual Machine Specification 17, **`ClassFile` format and `Code` attribute**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- ASM JavaDoc, **`ClassReader` / `ClassWriter` / `MethodVisitor`**: https://asm.ow2.io/javadoc/

The core of the contract: **the input belongs to the pipeline/JVM and the transformer may only read it; a modified result must be a separate new class file; when no change is needed, return `null`**. This rule allows transformers to compose and be verified without relying on hidden mutation.
