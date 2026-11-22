# Boundary Between the Transformation Registration API and Tools That Actually Read and Modify Bytecode

In Java instrumentation, **registering a transformer** and **transforming bytecode** are two distinct tasks. `java.lang.instrument` provides the hook into the JVM to receive a class's bytes at the appropriate time; libraries such as ASM, Byte Buddy, or Javassist provide the mechanisms to parse and generate new bytecode. A transformer can be invoked successfully yet the program will still run identically if it does not return a modified class file.

This lesson belongs to the **Instrumentation Overview** topic and focuses on clarifying who registers, who reads/modifies, who applies the result, and how to verify that a transformation actually took place.

## 1. Distinguishing the Four Roles

| Component | Responsible for | What does it not do automatically? |
|---|---|---|
| Java agent (`premain` or `agentmain`) | Serves as the entry point for instrumentation code; receives the `Instrumentation` object from the JVM | Does not automatically know which classes/methods need to be modified |
| `Instrumentation` | Registers/removes `ClassFileTransformer`, requests retransform/redefine when supported, checks certain JVM capabilities | Does not provide a parser/editor for bytecode structure like ASM |
| `ClassFileTransformer` | Receives the class name, class loader, and class file byte array; decides whether to keep it unchanged or return new bytes | Merely implementing the callback does not mean bytecode has been changed |
| ASM / Byte Buddy / Javassist | Reads, models, and/or generates class files, modifying instructions/methods according to developer-defined rules | Does not automatically make the JVM replace a running class just because a byte array was produced |
| JVM | Invokes transformers according to supported mechanisms, uses the transformed bytes, and verifies validity before defining/updating the class | Does not automatically infer the intent of the bytecode tool |

Note: the table describes **roles**, not a rule that separate libraries must be used. Byte Buddy can wrap both the transformer configuration/registration step and the bytecode generation step; ASM can be used directly inside a `ClassFileTransformer`, or used offline in a build tool.

**Visualizing the flow when a class is about to be defined:**

```text
java -javaagent:agent.jar
       |
       v
JVM calls premain(..., Instrumentation)
       |
       v
agent calls instrumentation.addTransformer(...)
       |
       v
JVM prepares to define demo.Greeter
       |
       v
ClassFileTransformer.transform(..., classfileBuffer)
       |
       +-- no modification / not applicable? --> return null
       |
       +-- want to modify? --> ASM reads byte[] --> ASM generates new byte[] --> return new byte[]
       |
       v
JVM continues the transformer chain, verifies, and defines the class
       |
       v
Application executes the accepted bytecode version
```

`classfileBuffer` is class file data in byte form, **not `.java` source** and not a `Class<?>` whose method body can be directly edited. Java Reflection inspects metadata and invokes existing members; it does not provide an API to replace instructions inside a method body.

## 2. What Exactly Does `addTransformer` Do?

```java
instrumentation.addTransformer(transformer);
```

This call **registers** the `transformer` object with the JVM, equivalent to `addTransformer(transformer, false)`. After registration, future matching class definitions can trigger the callback. By itself, `addTransformer` does not:

1. Read and parse the entire classpath.
2. Modify any method.
3. Automatically invoke the callback for all classes already loaded beforehand.
4. Guarantee that every class can be modified.

The traditional callback, still usable on Java 17+, has the form:

```java
byte[] transform(
    ClassLoader loader,
    String className,
    Class<?> classBeingRedefined,
    ProtectionDomain protectionDomain,
    byte[] classfileBuffer
)
```

Meaning of the parameters you usually need to care about:

- `className`: internal name, for example `demo/Greeter` (`/` separator, not `demo.Greeter`); in some cases the value is `null`.
- `loader`: the class loader defining the class, which can be `null` for the bootstrap loader. The same class name with different class loaders can be different runtime classes.
- `classBeingRedefined`: usually `null` during initial loading; may point to the existing class during redefine/retransform.
- `protectionDomain`: security domain information associated with the class, useful when filtering is needed.
- `classfileBuffer`: input bytes for this step in the transformer chain.

Since Java 9, the interface also has an overload taking `Module` as the first parameter. The new overload forwards by default to the five-argument version, so the examples below use the five-argument signature for readability.

**Return contract:**

```java
return null;             // No transformation: the JVM continues using the bytes from before this step
return transformedBytes; // Propose that the JVM use the new bytes for the rest of the pipeline
```

A callback that only calls `println` and `return null` is an **observing agent**, not yet a bytecode-rewriting agent. Returning an exact semantic copy of the input also produces no behavioral change. Do not mutate the `classfileBuffer` array directly; if transformation is needed, create a separate output array.

## 3. Which Part Does the Bytecode Tool Handle?

With ASM, three common roles are:

- `ClassReader`: decodes the input class file structure.
- `ClassVisitor` / `MethodVisitor`: traverses and adjusts classes, methods, and instructions.
- `ClassWriter`: generates a new class file byte array for the callback to return to the JVM.

Conceptual example:

```java
ClassReader reader = new ClassReader(classfileBuffer);
ClassWriter writer = new ClassWriter(reader, 0);
reader.accept(myClassVisitor, 0);
byte[] rewrittenClassFile = writer.toByteArray();
return rewrittenClassFile;
```

The snippet above **cannot run standalone** because `myClassVisitor` must be declared and explicitly describe the transformation. The next section provides a complete program that does this.

Byte Buddy typically offers a higher-level API for expressing intent, such as intercepting method calls or adding advice; ASM gives closer control over instructions and JVM descriptors. Javassist is often convenient for class/method-level edits. Regardless of the library chosen, you must preserve a valid class file structure, operand stack types, and stack-map frames when altering control flow.

## 4. Java 17+ Example: Registering a Callback and Actually Changing an Instruction

We will build **the same agent** with two modes:

- `observe`: receives the callback, prints a log, `return null` — the application stays unchanged.
- `rewrite`: uses ASM to replace a string constant in the `greet()` method, returns new bytes — the application's output changes.

Maven project structure:

```text
agent-boundary-demo/
├── pom.xml
└── src/main/java/demo/
    ├── BoundaryAgent.java
    ├── Greeter.java
    └── Main.java
```

### 4.1. Target Application

**`src/main/java/demo/Greeter.java`**

```java
package demo;

public final class Greeter {
    public String greet() {
        return "Hello";
    }
}
```

**`src/main/java/demo/Main.java`**

```java
package demo;

public final class Main {
    public static void main(String[] args) {
        System.out.println(new Greeter().greet());
    }
}
```

Without an agent, the application's stdout is:

```text
Hello
```

### 4.2. Agent Registering a Transformer and Invoking ASM Only in `rewrite` Mode

**`src/main/java/demo/BoundaryAgent.java`**

```java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

public final class BoundaryAgent {
    private BoundaryAgent() {
    }

    public static void premain(String agentArgs, Instrumentation instrumentation) {
        boolean rewrite = "rewrite".equals(agentArgs);

        // Step 1: register the callback with the JVM.
        instrumentation.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    ClassLoader loader,
                    String className,
                    Class<?> classBeingRedefined,
                    ProtectionDomain protectionDomain,
                    byte[] classfileBuffer) {

                // Only touch the lesson's class; avoid instrumenting every JVM class.
                if (!"demo/Greeter".equals(className)) {
                    return null;
                }

                System.out.println("[agent] callback: " + className);

                // Step 2a: callback runs without modifying any bytecode.
                if (!rewrite) {
                    return null;
                }

                // Step 2b: ASM reads and rewrites the class file.
                ClassReader reader = new ClassReader(classfileBuffer);
                ClassWriter writer = new ClassWriter(reader, 0);
                boolean[] changed = {false};

                ClassVisitor visitor = new ClassVisitor(Opcodes.ASM9, writer) {
                    @Override
                    public MethodVisitor visitMethod(
                            int access,
                            String name,
                            String descriptor,
                            String signature,
                            String[] exceptions) {

                        MethodVisitor delegate = super.visitMethod(
                                access, name, descriptor, signature, exceptions);

                        // Only replace the instruction in String greet().
                        if (!"greet".equals(name)
                                || !"()Ljava/lang/String;".equals(descriptor)) {
                            return delegate;
                        }

                        return new MethodVisitor(Opcodes.ASM9, delegate) {
                            @Override
                            public void visitLdcInsn(Object constant) {
                                if ("Hello".equals(constant)) {
                                    changed[0] = true;
                                    super.visitLdcInsn("Hello instrumented");
                                } else {
                                    super.visitLdcInsn(constant);
                                }
                            }
                        };
                    }
                };

                reader.accept(visitor, 0);
                if (!changed[0]) {
                    return null;
                }

                System.out.println("[agent] ASM changed LDC in greet()");
                return writer.toByteArray();
            }
        });
    }
}
```

**Explanation of the boundary points:**

1. `premain` is invoked by the JVM via the `Premain-Class` manifest entry; it receives `Instrumentation`.
2. `addTransformer(...)` only **registers**; at this point the code has not read the contents of `Greeter`.
3. When `Greeter` is defined, the JVM calls `transform` with the class's bytes.
4. In `observe`, printing the log proves the callback ran, while `return null` proves **no replacement bytes were provided**.
5. In `rewrite`, `ClassReader` locates the `greet()` method with descriptor `()Ljava/lang/String;`; `MethodVisitor` replaces the `LDC` value from `"Hello"` to `"Hello instrumented"`.
6. `ClassWriter` generates the new class file; `return writer.toByteArray()` feeds it back into the JVM's pipeline.

The example intentionally changes only **a single string constant**, without adding methods, altering control flow, or changing operand stack sizes or stack-map frames. Therefore, using `ClassWriter(reader, 0)` is appropriate for this small transformation. When adding branches, changing the stack, or adding exception handlers, you must recompute stack/maxs/frames properly (for example, using ASM's computation flags when appropriate), and then verify the generated bytecode.

### 4.3. Packaging the JAR with Manifest and ASM Library

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>agent-boundary-demo</artifactId>
    <version>1.0.0</version>

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
                        <goals><goal>shade</goal></goals>
                        <configuration>
                            <transformers>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                                    <manifestEntries>
                                        <Premain-Class>demo.BoundaryAgent</Premain-Class>
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

We package ASM together with the agent using the Shade Plugin: if the JAR only contains `BoundaryAgent.class` without ASM on the agent's class loading path, the JVM may throw `NoClassDefFoundError` when the agent needs ASM. `Premain-Class` tells the JVM the agent startup method; it does **not** mean the JVM knows how to rewrite methods on its own.

### 4.4. Running and Comparing Results

From the `agent-boundary-demo` directory, using JDK 17+ and Maven:

```bash
mvn -q -DskipTests package

java -cp target/agent-boundary-demo-1.0.0.jar demo.Main

java -javaagent:target/agent-boundary-demo-1.0.0.jar=observe \
     -cp target/agent-boundary-demo-1.0.0.jar demo.Main

java -javaagent:target/agent-boundary-demo-1.0.0.jar=rewrite \
     -cp target/agent-boundary-demo-1.0.0.jar demo.Main
```

The trailing `\` is line continuation in Bash; in PowerShell/cmd, write each `java` command on a single line.

**Expected stdout for each `java` command (excluding Maven build output):**

Without agent:

```text
Hello
```

`observe` mode:

```text
[agent] callback: demo/Greeter
Hello
```

`rewrite` mode:

```text
[agent] callback: demo/Greeter
[agent] ASM changed LDC in greet()
Hello instrumented
```

The key takeaway: **both `observe` and `rewrite` receive the callback; only `rewrite` changes the output of `greet()`**. This directly verifies the boundary between *registered/invoked* and *modified bytes used by the JVM*.

You can inspect the original bytecode with:

```bash
javap -c -p -cp target/agent-boundary-demo-1.0.0.jar demo.Greeter
```

This command reads the class on **disk**, so you will still see the original `"Hello"` constant. The agent in the example only transforms the definition **inside the running JVM**; it does not overwrite `.class` files in the JAR. This helps distinguish *runtime transformation* from *offline bytecode rewriting*.

## 5. Transformation Timings That Are Easily Confused

### 5.1. Initial Loading: Load-Time Transformation

An agent started with `-javaagent` registers its transformer in `premain`, and classes defined **after registration** pass through the appropriate callback. This is the mechanism used in the example.

If a class was already defined before registration, merely calling `addTransformer` will not retroactively run the callback for that class.

### 5.2. Retransform: Re-running the Pipeline for an Already-Loaded Class

If the JVM supports it, the agent JAR declares the appropriate capability (`Can-Retransform-Classes: true`), the transformer is registered with `addTransformer(transformer, true)`, and the specific class is modifiable, then `instrumentation.retransformClasses(Target.class)` asks the JVM to re-run the transformation process.

Before using it, check:

```java
if (instrumentation.isRetransformClassesSupported()
        && instrumentation.isModifiableClass(Target.class)) {
    instrumentation.retransformClasses(Target.class);
}
```

`Target` in this snippet is just a placeholder for an existing class, **not runnable standalone code**. The method can also throw exceptions such as `UnmodifiableClassException`, so real code must handle them.

Subtle detail: a transformer registered with `canRetransform=false` is **not invoked again** during retransform, but its previous transformation result is reapplied by the JVM per the API contract. Only transformers with `canRetransform=true` receive the callback during a retransform. You cannot infer solely from registration that a callback will definitely run again.

### 5.3. Redefine: Supplying a New Definition

`instrumentation.redefineClasses(new ClassDefinition(Target.class, bytes))` takes **already-prepared class file bytes**. These may have been produced by ASM/Byte Buddy or another tool. This is another path to ask the JVM to update an existing class; it requires `isRedefineClassesSupported()` and a modifiable class, and must obey JVM restrictions on class structural changes.

Do not conflate these three operations:

| Operation | Nature |
|---|---|
| `addTransformer(...)` | Registers a callback for matching events |
| `retransformClasses(...)` | Asks the JVM to re-run the transform pipeline on an already-loaded class |
| `redefineClasses(...)` | Asks the JVM to use a newly supplied class definition |

Retransform and redefine are not mechanisms to freely add/remove fields, change method signatures, or alter the hierarchy of a running class. Supported changes depend on JVM capabilities and must be checked against documentation and tested on the target runtime.

### 5.4. Dynamically Loaded Agents and the Module System

Java also has `agentmain` for agents loaded after the JVM has started; dynamic attach/load availability depends on the JDK, configuration, and runtime policies. Do not assume it is always available like `-javaagent` at startup. With the module system (Java 9+), the `java.lang.instrument` API provides the `transform(Module, ...)` overload; module access and class-loader visibility can affect agent code and its dependent libraries. Any changes to module read/open permissions must be decided separately; `addTransformer` does not automatically grant arbitrary access.

## 6. Who Decides Whether a Transformation Succeeds?

A transformer typically receives `byte[]` and returns another `byte[]` or `null`, but **the JVM is the party that accepts and loads the class definition**. Changing bytes does not mean everything can be changed.

A class file may be rejected if:

- the constant pool, opcodes, or class file format is corrupted;
- the bytecode violates type checking, operand stack, or stack-map frame rules;
- it uses a class-file version unsupported by the runtime;
- it modifies an already-loaded class in a way the JVM does not support;
- it conflicts with another transformer in the pipeline.

Multiple transformers can run sequentially, so a transformer may receive bytes already processed by a previous transformer. Do not assume the input is always byte-for-byte identical to the `.class` file on disk. When writing your own transformer, design it to be safe for repeated runs, filter class names, avoid transforming the agent's own libraries, and minimize side effects inside the callback.

**Diagnosing by layer of responsibility:**

1. No callback observed: check the manifest, `-javaagent`, registration timing, internal name, and class loader.
2. Callback observed but behavior unchanged: check whether it actually entered the modification branch, produced different bytes, and returned the new array.
3. New bytes produced but load/verify error occurs: check class-file structure, instructions, stack/frames, and retransform/redefine restrictions.
4. Change occurs but on the wrong class/method: check `className`, descriptor (e.g., `()Ljava/lang/String;`), overloads, and class loader.
5. Works on initial run but fails on retransform: check JVM/manifest capabilities, `canRetransform`, and idempotency when re-run.

Use `java -Xverify:all ...` when you need to proactively tighten bytecode verification in a test environment. For complex transformations, add ASM checks such as `CheckClassAdapter` (requires the appropriate dependency) and tests verifying both behavioral output and class loading. A `"transform called"` log **is not sufficient** proof that a method was modified.

## 7. Misconceptions to Eliminate

- **"Calling `addTransformer` means the application is already instrumented."** False: it is only registered; the callback may not have run yet or may always return `null`.
- **"`ClassFileTransformer` modifies bytecode by itself."** False: it is a callback interface/contract; the modification logic must be executed by your code or a bytecode library.
- **"ASM is part of `Instrumentation`."** False: ASM is a separate library; the example had to include it as a dependency and on the agent's classpath/JAR.
- **"Having ASM means you can automatically modify running code."** False: ASM generates bytes; you need the appropriate load/redefine/retransform step for the JVM to use those bytes.
- **"`return null` is an error."** False: it is the valid, standard way to say "do not modify this class".
- **"Every already-loaded class will be modified when a transformer is added."** False: you must explicitly consider retransform/redefine if supported.
- **"Opening the JAR after running will show the modified method."** False for runtime examples: the file on disk is not overwritten.
- **"Just replace raw byte sequences in `.class`."** Dangerous: the constant pool, lengths, instructions, and JVM verification have strict rules; use a class-file-aware tool like ASM.

## 8. Choosing Tools Based on Needs

| Need | Appropriate approach |
|---|---|
| Only observe which classes are loaded | Java agent + `ClassFileTransformer` filtering and `return null` |
| Modify a specific instruction/descriptor | Agent + ASM for fine-grained bytecode control |
| Add advice/interceptors to methods with a high-level API | Byte Buddy with the appropriate agent/transformer mechanism |
| Create/modify `.class` before packaging a JAR, without a running JVM | ASM/Byte Buddy/Javassist at build time; a Java agent is not necessarily needed |
| Change an already-loaded class | Check JVM capabilities; choose retransform or redefine within supported limits |
| Verify that transformation actually happened | Observe behavior/output bytes, run the verifier, and cross-check with callback logs |

## 9. Self-Check Knowledge

1. A transformer prints `demo/Greeter` and returns `null`. What work has the agent done and what has it not done?  
   **Answer:** it has registered for/observed the class definition event; it has not provided replacement bytecode.

2. ASM generates valid bytes, but the code only calls `reader.accept(...)` and then `return null`. Will the JVM use the new class?  
   **Answer:** no; the result generated by ASM was not fed back into the pipeline via `return writer.toByteArray()`.

3. Why does `javap` reading the JAR still show `"Hello"` after the `rewrite` run printed `"Hello instrumented"`?  
   **Answer:** the transformation happens inside the JVM at class definition time; the original file on disk is not modified.

4. To affect an already-loaded class, is calling `addTransformer` alone enough?  
   **Answer:** no; you need the appropriate class-update path, to check support and modifiability, and then ask the JVM to perform it.

5. Do Byte Buddy and `Instrumentation` completely replace each other?  
   **Answer:** no. One provides the tool/abstraction to define transformations; the other is the JVM API for registering and managing the instrumentation process. A solution can combine both.

**Key takeaway:** `Instrumentation` and `ClassFileTransformer` form the **pathway and contract for receiving/returning class bytes**; ASM/Byte Buddy/Javassist (or equivalent bytecode code) produce the **modified content**; the JVM decides to **apply valid bytes**. Only when all three parts work together properly does the program exhibit instrumented behavior.

## References

- Java 17 — [`Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- Java 17 — [`ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- Java 17 — [Package `java.lang.instrument`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- ASM — [Project page](https://asm.ow2.io/) and [Maven Central artifact](https://central.sonatype.com/artifact/org.ow2.asm/asm/9.7.1)