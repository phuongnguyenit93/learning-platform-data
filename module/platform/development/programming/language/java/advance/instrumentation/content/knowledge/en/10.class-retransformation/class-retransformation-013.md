# Designing Configuration-Driven Probe Toggling and Controlled Retransformation

In a running Java application, you may want to enable a probe to observe a method during an incident, then disable the probe to reduce operational overhead without restarting the JVM. With Java Instrumentation, configuration defines the desired state; `ClassFileTransformer` decides what bytecode to generate; `Instrumentation.retransformClasses(...)` applies the change to already-loaded classes. These three parts must be coordinated in a controlled manner.

## 1. Objectives and Terminology

After this lesson, you will be able to:
- Distinguish **changing configuration** from **changing the currently active bytecode**.
- Choose between toggling logic inside a hook and toggling via retransformation.
- Design a workflow to select the right classes, check modifiability, bound scope, and verify results.
- Run a sample Java agent that can enable/disable a probe via a configuration file while the application is still running.
- Handle risks around system load, interactions among multiple transformers, bytecode verification errors, and in-flight invocations.

A **probe** is additional code inserted to record events, timing, invocation counts, or diagnostic information at a specific point. **Retransformation** is the mechanism of asking the JVM to re-run the transformer chain on an already-loaded class and install a new valid bytecode version of that class. It differs from creating a new instance or recompiling source code on disk.

Example: we need to count invocations of `OrderService.work()` only during an investigation window. The requirement is to enable it with `probe.enabled=true`, verify that events appear, then set `false` and verify that new calls no longer produce events.

## 2. Two Probe Toggling Styles

| Style | When Toggling | Advantages | Costs and Limitations |
| --- | --- | --- | --- |
| **Soft toggle**: bytecode always calls `ProbeHooks.maybeRecord()`; inside the hook, it checks a `volatile` flag/config | Change the flag, no retransformation needed per switch | Fast changes, suitable for frequent toggling | The call path still pays the hook call and conditional branch cost; disabled-path logic must be optimized |
| **Hard toggle**: when enabled, the transformer inserts the hook call; when disabled, the transformer does not insert it and retransforms the class | Change configuration **and** request JVM retransformation | When disabled, can completely remove the call inserted by this agent | Retransformation has overhead, must obey JVM limits, and requires error handling |

**Choosing a design:** if very frequent changes are needed, a soft toggle is usually more economical. If measurement is costly even when inactive or you need to minimize impact when disabled, a hard toggle makes more sense, with bounded retransformation frequency and class count. You can combine both: use retransformation once to install the hook, then use a soft toggle for ongoing changes.

Changing a configuration variable **does not automatically modify already-loaded methods**. For a hard toggle, you must actively invoke `retransformClasses` (or another tool with the same purpose) on the target `Class<?>` objects.

## 3. How Does the JVM Perform Retransformation?

With an agent declaring `Can-Retransform-Classes: true`, the JVM supporting this capability, and a transformer registered with `addTransformer(transformer, true)`, the basic flow is:

1. Obtain the class's base bytecode (which may differ from the original bytes in constant pool or certain attributes).
2. Reuse the previous results of transformers that do **not** support retransformation, without calling them again.
3. Re-invoke transformers that **do** support retransformation in chain order.
4. Validate that the changes are legal and install the transformed class.

For a retransformation-capable transformer, returning `null` means **that transformer does not modify the bytes passed to the current invocation**. In a single-transformer model that inserts probes onto the base bytecode itself, when disabled and retransformed, the probe inserted by that transformer disappears from new calls. However, `null` **is not a command to revert all changes across the entire JVM**: other transformers, especially non-retransformation-capable transformers, may still leave changes behind.

Preconditions to check before making changes:
- The agent manifest has `Premain-Class` (or `Agent-Class` for attach as appropriate) and `Can-Retransform-Classes: true`.
- `instrumentation.isRetransformClassesSupported()` returns `true`; `addTransformer(transformer, true)` has succeeded.
- `instrumentation.isModifiableClass(target)` returns `true`; not every class is modifiable.
- Target identity consists of **class name and class loader** (multiple class loaders can hold classes with the same name).
- Changes are restricted to bytecode/attributes permitted by the JVM; do not add/remove fields or methods, change signatures, inheritance hierarchy, or make forbidden schema changes.
- Hooks and helper classes are accessible from the target class's class loader/module.

**Runtime impact:** stack frames that already entered a method before retransformation may continue executing the old bytecode. Subsequent new invocations use the new definition. Existing objects and static variables remain intact; retransformation does not re-run class initializers.

## 4. Safe Configuration Change Workflow

A `reconcile(desiredConfig)` cycle should operate in order:

1. **Load and validate configuration:** check `enabled`, allowed class/method list, configuration version, expiration time; reject invalid values. You can write a new file and atomically rename it to avoid reading a partially written file.
2. **Compare with currently applied configuration:** if the state has not changed, do not trigger unnecessary retransformation. Enforce rate limits and batch multiple changes into one pass.
3. **Identify the exact target set:** scan `getAllLoadedClasses()` by allowlist + class loader + method signature; verify with `isModifiableClass`. Classes not yet loaded will be handled later when loaded by the still-registered transformer.
4. **Assess impact:** count classes, bytecode size, system health; bound by batches and avoid mass changes during high-load periods.
5. **Apply state to the transformer**, then call `retransformClasses` on the exact vetted class set. Synchronize configuration updates so two modification tasks do not overlap.
6. **Verify in practice:** record expected/attempted/succeeded class counts, transformer errors, configuration version; check hook invocation counts on a test case or real telemetry signals.
7. **Rollback on failure:** retain the last successfully applied state, restore flags, and retransform again if needed. Do not declare success merely because the new configuration was read.

In systems with multiple class loaders or thousands of classes, do not let an arbitrary configuration trigger JVM-wide retransformation. Select specific classes/methods and funnel post-validation enable/disable decisions through a single coordination point.

## 5. Runnable Example: Java 17+, Maven, ASM, and Startup Agent

The example uses a **hard toggle**. When `probe.enabled=true`, the agent adds a call to `ProbeHooks.hit()` at the beginning of `demo.OrderService.work()`; when `false`, it returns `null` on the next retransformation. The already-started application does not need a restart. We use ASM to generate valid bytecode; the Java Instrumentation API does not itself provide JVM instruction insertion operations.

Directory structure:

```text
dynamic-probe/
├── pom.xml
├── probe.properties
└── src/main/java/
    ├── agent/
    │   ├── ProbeAgent.java
    │   └── ProbeTransformer.java
    └── demo/
        ├── OrderService.java
        ├── ProbeHooks.java
        └── Main.java
```

**`pom.xml`** — packages the agent and ASM into a single executable agent JAR:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>dynamic-probe</artifactId>
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
                        <goals><goal>shade</goal></goals>
                        <configuration>
                            <createDependencyReducedPom>false</createDependencyReducedPom>
                            <transformers>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                                    <manifestEntries>
                                        <Premain-Class>agent.ProbeAgent</Premain-Class>
                                        <Can-Retransform-Classes>true</Can-Retransform-Classes>
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

**`probe.properties`** — initial configuration:

```properties
probe.enabled=false
```

**`src/main/java/agent/ProbeAgent.java`** — reads configuration, holds the registered transformer, and controls retransformation:

```java
package agent;

import java.io.IOException;
import java.io.Reader;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Properties;

public final class ProbeAgent {
    private static volatile boolean enabled;
    private static Instrumentation instrumentation;

    private ProbeAgent() {}

    public static void premain(String args, Instrumentation inst) throws IOException {
        if (!inst.isRetransformClassesSupported()) {
            throw new IllegalStateException("Retransformation unavailable");
        }
        instrumentation = inst;
        enabled = readEnabled();
        inst.addTransformer(new ProbeTransformer(), true);
        System.out.println("[agent] enabled=" + enabled);
    }

    static boolean enabled() {
        return enabled;
    }

    public static synchronized void reload()
            throws IOException, UnmodifiableClassException {
        boolean next = readEnabled();
        if (next == enabled) {
            return;
        }

        // Demo: only find the OrderService class loaded by the application class loader.
        Class<?> target = Arrays.stream(instrumentation.getAllLoadedClasses())
                .filter(c -> c.getName().equals("demo.OrderService"))
                .filter(c -> c.getClassLoader() == ClassLoader.getSystemClassLoader())
                .findFirst()
                .orElse(null);

        if (target != null && !instrumentation.isModifiableClass(target)) {
            throw new IllegalStateException("Target class is not modifiable");
        }

        boolean previous = enabled;
        enabled = next;
        try {
            // If the class is not yet loaded, the transformer will apply the new state when loaded.
            if (target != null) {
                instrumentation.retransformClasses(target);
            }
        } catch (UnmodifiableClassException | RuntimeException | Error e) {
            enabled = previous;
            throw e;
        }
        System.out.println("[agent] enabled=" + enabled);
    }

    private static boolean readEnabled() throws IOException {
        Properties values = new Properties();
        try (Reader reader = Files.newBufferedReader(
                Path.of("probe.properties"), StandardCharsets.UTF_8)) {
            values.load(reader);
        }
        String raw = values.getProperty("probe.enabled");
        if (raw == null || (!raw.equalsIgnoreCase("true")
                && !raw.equalsIgnoreCase("false"))) {
            throw new IllegalArgumentException(
                    "probe.enabled must be true or false");
        }
        return Boolean.parseBoolean(raw);
    }
}
```

**`src/main/java/agent/ProbeTransformer.java`** — inserts the hook call into only one method; does not change class signature or structure:

```java
package agent;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

final class ProbeTransformer implements ClassFileTransformer {
    @Override
    public byte[] transform(ClassLoader loader, String className,
            Class<?> classBeingRedefined, ProtectionDomain domain,
            byte[] classfileBuffer) {
        if (!"demo/OrderService".equals(className) || !ProbeAgent.enabled()) {
            return null;
        }

        ClassReader reader = new ClassReader(classfileBuffer);
        ClassWriter writer =
                new ClassWriter(reader, ClassWriter.COMPUTE_MAXS);

        ClassVisitor visitor = new ClassVisitor(Opcodes.ASM9, writer) {
            @Override
            public MethodVisitor visitMethod(int access, String name,
                    String descriptor, String signature, String[] exceptions) {
                MethodVisitor method = super.visitMethod(
                        access, name, descriptor, signature, exceptions);
                if (!"work".equals(name) || !"()I".equals(descriptor)) {
                    return method;
                }
                return new MethodVisitor(Opcodes.ASM9, method) {
                    @Override
                    public void visitCode() {
                        super.visitCode();
                        super.visitMethodInsn(Opcodes.INVOKESTATIC,
                                "demo/ProbeHooks", "hit", "()V", false);
                    }
                };
            }
        };

        reader.accept(visitor, 0);
        return writer.toByteArray();
    }
}
```

`ClassReader` reads the current bytecode of the transform pass; `ClassVisitor` selects the exact method `work()I` (no parameters, returns `int`); `visitCode()` adds the static call at the start of the method. `COMPUTE_MAXS` recomputes the required stack/local limits. For complex transformations that alter control flow/frames, appropriate stack map frames must be computed and verified; do not mechanically apply this example to every class file.

**`src/main/java/demo/OrderService.java`**:

```java
package demo;

public class OrderService {
    public int work() {
        return 40 + 2;
    }
}
```

**`src/main/java/demo/ProbeHooks.java`** — observable measurement signal:

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

public final class ProbeHooks {
    private static final AtomicInteger HITS = new AtomicInteger();

    private ProbeHooks() {}

    public static void hit() {
        System.out.println("[probe] hit=" + HITS.incrementAndGet());
    }

    public static int hits() {
        return HITS.get();
    }
}
```

**`src/main/java/demo/Main.java`** — each Enter press reloads configuration, switches state, and invokes the method:

```java
package demo;

import agent.ProbeAgent;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class Main {
    public static void main(String[] args) throws Exception {
        OrderService service = new OrderService();
        System.out.println("work=" + service.work()
                + ", hits=" + ProbeHooks.hits());
        System.out.println("Edit probe.properties, then press Enter to reload.");

        BufferedReader input = new BufferedReader(
                new InputStreamReader(System.in, StandardCharsets.UTF_8));
        while (input.readLine() != null) {
            ProbeAgent.reload();
            System.out.println("work=" + service.work()
                    + ", hits=" + ProbeHooks.hits());
        }
    }
}
```

From the `dynamic-probe` directory, JDK 17+ and Maven are required:

```bash
mvn -q -DskipTests package
java -javaagent:target/dynamic-probe-1.0.jar -cp target/dynamic-probe-1.0.jar demo.Main
```

Without stopping the application: edit `probe.properties` to `probe.enabled=true`, save the file, and press Enter in the application terminal. Then edit it to `false`, save, and press Enter again.

Sample output (prompt lines omitted):

```text
[agent] enabled=false
work=42, hits=0
[agent] enabled=true
[probe] hit=1
work=42, hits=1
[agent] enabled=false
work=42, hits=1
```

When **enabled**, `reload()` sets the desired state and retransforms `OrderService`; ASM adds the `ProbeHooks.hit()` call. When **disabled**, the transformer is invoked again but returns `null`, so in this single-transformer example the `work()` code after retransformation no longer contains the probe call. The counter remains `1` because retransformation does not reset static state. In the example, pressing Enter is the action that actively triggers reload: merely editing the file without reloading does not switch the state.

**Intentional limitations of the example:** the demo application and agent are in the same JAR, use the system class loader, target one class and one method, and allow only one thread to drive reload. In real production systems, probes are usually in a separate agent/helper; you must address helper visibility across modules/class loaders, receive configuration from a controlled source, and track all transformer errors. This code illustrates the principle, not a production orchestration system.

## 6. Design for Real-World Systems

Configuration state and runtime state can be represented separately:

```text
config version N, desired=ON
         |
         v
Validate + authorize + allowlist
         |
         v
Find loaded Class<?> + modifiability check
         |
         v
Single-flight coordinator + bounded batches
         |
         v
Transformer reads immutable config snapshot
         |
         v
retransformClasses(targets...)
         |
         v
Verify probe hits/errors + record applied version
         |
    PASS / FAIL
     |      |
     v      v
commit   rollback + alert
```

In an agent serving many classes, use an immutable configuration snapshot (for example, a `record ProbeConfig(long version, boolean enabled, Set<String> targets)`) and swap the entire snapshot atomically. When starting a retransformation cycle, acquire the coordination lock and tag the change pass with a version; avoid mixing decisions from two versions. Using `volatile boolean` in the example is only sufficient to demonstrate a single simple probe.

Operational decisions that must be made explicit:
- **Scope:** exact allowlist of class name, class loader, method descriptor; do not scan and modify all classes merely because of a shared package name.
- **Limits:** limit classes per batch, minimum interval between switches, and timeouts; batch according to application impact.
- **Signals:** `requested_version`, `applied_version`, `candidate_count`, `modified_count`, `transform_error_count`, `probe_hit_count`, retransformation duration, and rollback count.
- **Hook safety:** hooks must not call back into the very method being measured, must not perform heavy synchronous I/O on hot paths, must avoid generating sensitive data, and must avoid holding references to class loaders that cause leaks.
- **Reliability:** validate bytecode output and actual behavior; exceptions thrown inside `ClassFileTransformer.transform` may not stop the JVM from continuing the transformer chain, so catch/record errors to avoid reporting false state.
- **Operational safeguards:** permissions for changing configuration, auditing who performed the change and why, and the ability to quickly disable when probes increase latency.

A safe rollback option is to retain the last successfully applied configuration snapshot, restore that snapshot on error, invoke retransformation for affected targets when needed, and re-verify. With multiple classes, distinguish single-batch success from whole-campaign success; detect partial-transition states.

## 7. Test Cases and Common Pitfalls

| Test | Expected Result |
| --- | --- |
| `false` at startup | `work()` returns `42`, `hits` does not increment |
| Change `false → true` then reload | New invocation produces one `[probe] hit=...` |
| Change `true → false` then reload | New invocation does not increment `hits`; previous count is preserved |
| Reload with same state | No need for `retransformClasses` |
| Config has value `maybe` or missing key | Reject, keep currently applied state |
| Class not yet loaded | No class to retransform; transformer handles it when the class is loaded |
| Class not modifiable / capability missing | Reject with clear error, do not falsely report success |
| Multiple transformers acting together | Inspect transformer order/bytecode overlap and verify which hooks remain |
| Invocation currently on the stack | May finish with old bytecode; measure on new invocations |

Mental mistakes to avoid:

1. **Editing configuration without triggering retransformation:** already-loaded code remains unchanged under a hard toggle.
2. **Forgetting `Can-Retransform-Classes` or registering with default `addTransformer(transformer)`:** retransformation capability is not enabled for that transformer.
3. **Calling `removeTransformer` expecting to remove the probe immediately:** this stops future transforms; it does not actively strip already-inserted bytecode. An appropriate restorative retransformation must be designed.
4. **Confusing `return null` with restoring the entire original bytecode:** other agents can still transform the class, and non-retransformation-capable transformers have their results reused.
5. **Not distinguishing class loaders:** two classes with the same name from two loaders are two distinct definitions; selecting the wrong class can instrument the wrong application.
6. **Changing class structure during retransformation:** adding fields/methods or changing signatures/hierarchy may be rejected by the JVM.
7. **Treating API completion as proof the probe works:** measure real signals and errors inside the transformer; avoid surprises when a callback fails or method names/descriptors do not match.
8. **Toggling repeatedly on hot classes:** consumes resources and may impact latency; consider a soft toggle or rate limiting.

## 8. Self-Check Questions

1. Why does changing `probe.enabled=false` in the file not immediately remove the hook call from already-loaded bytecode?
2. If your transformer returns `null` when disabled, why might changes from another agent still remain?
3. Why are both `isRetransformClassesSupported()` **and** `isModifiableClass(target)` needed?
4. What happens to an invocation currently executing mid-method when the class is retransformed?
5. In a system with multiple class loaders and thousands of classes, how would you define the allowlist, batching, verification, and rollback?

## 9. References

- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): capabilities, registering transformers, `retransformClasses`, `isModifiableClass`.
- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): transformer ordering, return values, and callback errors.
- [Java SE 21 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent JAR and manifest configuration.