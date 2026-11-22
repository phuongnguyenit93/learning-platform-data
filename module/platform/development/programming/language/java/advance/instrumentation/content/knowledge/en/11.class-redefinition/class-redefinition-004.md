# Checking Redefinition Capability and Per-Class Modifiability

**Redefinition** is the mechanism for replacing the class-file bytes of a class **already loaded by the JVM** by calling `Instrumentation.redefineClasses(ClassDefinition...)`. A Java agent must not assume it can invoke this operation simply because the class exists or because the JVM supports instrumentation. First, **two distinct conditions** must be checked:

- `Instrumentation.isRedefineClassesSupported()`: whether the JVM **in the current agent's configuration** grants the redefine capability. This requires the agent JAR to declare `Can-Redefine-Classes: true` **and** the JVM to actually support it.
- `Instrumentation.isModifiableClass(targetClass)`: whether the **specific class** is allowed to have its definition modified. This result **does not depend** on whether the agent has been granted the redefine capability.

Only when both return `true` should the agent prepare the new bytes and call `redefineClasses(...)`. Even then, the replacement class-file bytes must still have the correct class name, a supported classfile version, and comply with structural change limits. The two booleans are **necessary conditions, not a guarantee of success**.

This lesson covers the Java SE 17 contract, manifests, selecting the right `Class<?>`, bytecode change limits, error handling, and a Java 17+ program compiled and run with **two agent JARs that have the same code but different manifests**.

## 1. Do Not Conflate the Two Checks

| What you want to know | Call | What it actually answers |
| --- | --- | --- |
| Can this agent redefine already-loaded classes? | `inst.isRedefineClassesSupported()` | `true` if the agent manifest requests redefine and the current VM supports it. |
| Is class X in the group of classes the JVM can modify? | `inst.isModifiableClass(X.class)` | `true` if class X is modifiable in principle; does **not** indicate that the agent has the capability. |
| Can transformers be re-run for already-loaded classes? | `inst.isRetransformClassesSupported()` | **Retransformation** capability, independent of redefinition. |
| Can a module's reads/exports/opens be modified? | `inst.isModifiableModule(module)` | Module modification condition; **does not replace** class checks. |

Consider the four states:

| Redefine supported | Class modifiable | How to handle |
| --- | --- | --- |
| `false` | `false` | Do not call redefine; check both the manifest/VM and the class. |
| `false` | `true` | **Do not call redefine**: the class is modifiable in principle, but the agent lacks the capability. |
| `true` | `false` | **Do not call redefine**: the general capability is present, but the class is rejected. |
| `true` | `true` | Can prepare a **valid** `ClassDefinition` and attempt redefinition; still must handle errors. |

Decision model:

```text
JVM starts up / loads agent
        |
        v
Agent receives Instrumentation
        |
        v
isRedefineClassesSupported() ?
        |
        +-- false --> Do not redefine; check manifest and JVM
        |
        +-- true
              |
              v
        Identify the exact loaded Class<?>
              |
              v
        isModifiableClass(clazz) ?
              |
              +-- false --> Skip this specific class
              |
              +-- true
                    |
                    v
            Validate replacement class-file bytes
                    |
                    v
            redefineClasses(new ClassDefinition(clazz, bytes))
                    |
                    v
            Handle success/exceptions, verify at runtime
```

**Do not infer backward:** `isModifiableClass(clazz) == true` does not imply `isRedefineClassesSupported() == true`. The Java SE 17 API explicitly states that the result of `isModifiableClass` is not affected by the `isRedefineClassesSupported` and `isRetransformClassesSupported` capabilities. This is precisely the scenario demonstrated by the runnable example later in this lesson.

## 2. The `Can-Redefine-Classes` Manifest Attribute: Agent-Level Condition

When using a startup agent with `-javaagent`, the manifest **inside the JAR** needs:

```text
Manifest-Version: 1.0
Premain-Class: demo.redefine.ProbeAgent
Can-Redefine-Classes: true

```

`Premain-Class` specifies the class containing `public static void premain(String, Instrumentation)` (or the single-argument overload) for the JVM to invoke **before application `main`**. `Can-Redefine-Classes: true` requests the redefine capability. The JVM can only report it as supported when **both the manifest and the VM support it**; it does not rely solely on the Java version.

Other cases:

| Manifest content | Meaning |
| --- | --- |
| `Can-Redefine-Classes: true` | Requests the redefine capability. |
| `Can-Redefine-Classes: TRUE` | Boolean value is case-insensitive; equivalent to `true`. |
| `Can-Redefine-Classes: false` | Does not request the capability. |
| **Missing** `Can-Redefine-Classes` | Defaults to `false`. |
| `Can-Redefine-Classes: yes` | Not `true`, so interpreted as `false`. |

Simply having an `agent.mf` file on disk with `true` is **not enough**. At runtime, the JVM inspects `META-INF/MANIFEST.MF` of the **exact agent JAR passed to `-javaagent`**. Shading, repackaging, or CI/CD pipelines can alter the manifest. If runtime returns `false`, inspect the actual artifact rather than just reading the source manifest file.

### 2.1. When Attaching an Agent to a Running JVM

For an agent dynamically loaded via the Attach API (when permitted by the JVM and environment), the entry point is `Agent-Class` and `agentmain(...)`:

```text
Manifest-Version: 1.0
Agent-Class: demo.redefine.DynamicAgent
Can-Redefine-Classes: true

```

This is a **manifest illustrating the mechanism**, not the file used in the runnable example below; the hands-on example uses `ProbeAgent` with `Premain-Class`. Process attach permissions and dynamic loading policies are separate concerns: **a successful attach does not prove redefine capability**. Whether loaded via `premain` or `agentmain`, the agent must check the capability from the `Instrumentation` object it receives.

### 2.2. Redefine Differs from Retransform

The two manifest capabilities are not equivalent:

| Mechanism | Manifest | Capability query API | Execution API |
| --- | --- | --- | --- |
| Redefinition | `Can-Redefine-Classes: true` | `isRedefineClassesSupported()` | `redefineClasses(new ClassDefinition(clazz, bytes))` |
| Retransformation | `Can-Retransform-Classes: true` | `isRetransformClassesSupported()` | `retransformClasses(clazz)` |

**Redefine uses new bytes supplied by the caller**, typically for hot-patching or fix-and-continue. **Retransform re-runs the transformation process** based on the base bytes according to instrumentation rules; a transformer that wants to be invoked during retransformation must register with `canRetransform=true`. An agent must declare and check the exact feature it needs, rather than substituting the other feature's flag.

## 3. Checking `isRedefineClassesSupported()` at Runtime

In `premain`/`agentmain`, the agent receives an `Instrumentation` instance:

```java
// Illustrative code inside the agent; inst has been passed in by the JVM.
boolean canRedefine = inst.isRedefineClassesSupported();
if (!canRedefine) {
    System.out.println("Redefinition unavailable");
    // Choose degraded mode or report a feature error by design.
}
```

According to the Java SE 17 documentation, `isRedefineClassesSupported()` returns the same result within **a single JVM invocation**. There is no reason to expect it to flip from `false` to `true` simply because the application loads more classes or someone edits a manifest file outside the process.

When it is `false`, attempting to call `redefineClasses(...)` may cause the JVM to throw `UnsupportedOperationException`. An agent can handle this gracefully by still recording metrics/tracing for **future class loads** using a normal transformer, while **never falsely reporting that it has hot-redefined a running class**.

Do not treat `java -version` as the answer for capability support. The version indicates that the API exists in the JDK, whereas the capability is an **optional** property of the VM and the specific agent configuration.

## 4. Checking `isModifiableClass(clazz)` for Each Class

API:

```java
// Illustrative code; clazz is a properly resolved Class<?>.
boolean modifiable = inst.isModifiableClass(clazz);
```

It checks whether the JVM can modify the definition of that **specific class**, without testing a patch and without checking the redefine manifest capability. Java SE 17 specifies:

- **Primitive classes** such as `int.class`, `boolean.class`, and `void.class` are **not** modifiable.
- **Array classes** such as `String[].class` and `int[][].class` are **not** modifiable.
- Other classes depend on the JVM. Do not assume all classes in `java.*` are unmodifiable or that all application classes are modifiable.

Example:

```java
System.out.println(inst.isModifiableClass(int.class));      // false
System.out.println(inst.isModifiableClass(String[].class)); // false
```

Even when `isRedefineClassesSupported()==true`, the two classes above still return `false`. Conversely, an ordinary Java class may return `modifiable=true` even when the agent does **not** have the redefine capability. Both checks must be used **together**.

### 4.1. Selecting the Right `Class<?>` and Class Loader

In the JVM, class identity is not just a name string: it also includes the **defining class loader**. Two different class loaders can define two classes with the same name `com.example.Service` from different bytes.

Illustrative snippet:

```java
// Code snippet inside a tool, not a standalone Java program.
// applicationLoader is the properly identified class loader.
Class<?> target = Class.forName(
        "com.example.Service", false, applicationLoader);
if (inst.isRedefineClassesSupported()
        && inst.isModifiableClass(target)) {
    // Next, validate the new bytes before redefining.
}
```

Use `Class.forName(name, false, loader)` to avoid forcing class initialization just for a lookup (when possible). `getAllLoadedClasses()` can also provide loaded `Class<?>` instances, but you must filter by name, loader, module, and product scope. Do not grab the first class matching the name and blindly feed it bytes from a different JAR.

**Note:** `isModifiableModule(module)` is for modifying a module's opens/exports/reads; it does not substitute for `isModifiableClass(clazz)` and does not prove that new class-file bytes will be accepted.

### 4.2. Multiple Loaded Classes

With a large list of classes, filter by your business target before attempting to change definitions. Conceptual pattern:

```java
// Illustrative code inside the agent; inst is already available.
// Only build the candidate list; do NOT redefine any class yet.
java.util.List<Class<?>> candidates = new java.util.ArrayList<>();
if (inst.isRedefineClassesSupported()) {
    for (Class<?> c : inst.getAllLoadedClasses()) {
        if (c.getName().startsWith("com.example.")
                && inst.isModifiableClass(c)) {
            candidates.add(c);
        }
    }
}
```

This snippet is **not enough to call `redefineClasses`**: you need a separate `Class<?>` + replacement `byte[]` pair for **each** class and must verify they are compatible. Scanning the entire JVM and indiscriminately redefining every modifiable class is dangerous, can waste resources, and can collide with other agents.

## 5. Preparing `ClassDefinition`: Right Class and Valid Bytes

A `ClassDefinition` object binds an already-loaded `Class<?>` with new bytes:

```java
// Illustrative code inside a method that already has targetClass, path, and inst.
byte[] bytes = java.nio.file.Files.readAllBytes(path);
java.lang.instrument.ClassDefinition definition =
        new java.lang.instrument.ClassDefinition(targetClass, bytes);
inst.redefineClasses(definition);
```

Here, `bytes` are **JVM class-file bytes**, not Java source text or a URL. The `ClassDefinition(Class<?>, byte[])` constructor **does not clone the input array**; it only stores a reference. Prepare and validate the array completely before the call, and do not mutate the array after creating `ClassDefinition` — especially when multiple threads are involved.

Requirements for the replacement bytes:

1. **Exact binary name of the class** represented by `Class<?>`. If the file contains a different name, `NoClassDefFoundError` may be thrown.
2. **Version supported** by the running JVM; a version newer than the VM can cause `UnsupportedClassVersionError`.
3. **No prohibited schema changes**, such as adding/removing/renaming fields or methods, or changing descriptors, modifiers, or hierarchy in violation of current redefinition rules.
4. **Valid classfile**, where the constant pool, stack map frames, branch offsets, exception handlers, and required attributes remain consistent.
5. **Compatibility with other transformers**: registered `ClassFileTransformer` instances may receive the redefine event and further alter the bytes; do not assume the final class bytes are identical to the patch you passed in.

`isModifiableClass(clazz)==true` does **not** check these five conditions. A patch that adds a new field can still be rejected by the JVM even after passing the two-boolean preflight.

### 5.1. Redefine Does Not Automatically Look Up Files on Disk

`redefineClasses` uses the exact bytes passed via `ClassDefinition`. It does **not** recompile source code, re-read class files by name, or reload deployed JARs. Real-world tooling must know where the bytes come from, ensuring provenance, release alignment, checksums, and trust; never accept unauthenticated patches from external paths controlled by untrusted parties.

## 6. Java 17+ Example: Comparing Agent JARs With and Without Redefine Capability

The experiment has two versions of `Greeting.java` in the same package with the same class members, except the `message()` method returns a different string. The agent will check both conditions and **if permitted** replace the method body **on the already-loaded class** using the patch bytes.

Directory structure:

```text
redefine-demo/
├── src/
│   ├── main/demo/redefine/
│   │   ├── Greeting.java
│   │   ├── ProbeAgent.java
│   │   └── App.java
│   └── patch/demo/redefine/
│       └── Greeting.java
├── agent-on.mf
└── agent-off.mf
```

The two `Greeting.java` files reside in different directories, but share the same package. The base version is compiled into `out/`, and the patch version is compiled into `patch/`. **Only `out/` is on the runtime classpath**; `patch/` is the byte source for redefinition, not another class loader.

### 6.1. `src/main/demo/redefine/Greeting.java` — Original Version

```java
package demo.redefine;

public class Greeting {
    private final int id;
    private static int initializationCount;

    static {
        initializationCount++;
    }

    public Greeting(int id) {
        this.id = id;
    }

    public String message() {
        return "original-" + id;
    }

    public static int initializationCount() {
        return initializationCount;
    }
}
```

The `id` field helps identify an existing object; `initializationCount` checks whether `<clinit>` is re-executed after redefinition.

### 6.2. `src/patch/demo/redefine/Greeting.java` — Patch Version

```java
package demo.redefine;

public class Greeting {
    private final int id;
    private static int initializationCount;

    static {
        initializationCount++;
    }

    public Greeting(int id) {
        this.id = id;
    }

    public String message() {
        return "updated-" + id;
    }

    public static int initializationCount() {
        return initializationCount;
    }
}
```

Both versions keep the **same class name, fields, constructors, method descriptors, and superclass**. They differ only in the **body of `message()`**, without adding any new structure. If you rename a method or add a field, you have changed the schema and may be rejected.

### 6.3. `src/main/demo/redefine/ProbeAgent.java` — Checking Before Redefining

```java
package demo.redefine;

import java.io.IOException;
import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ProbeAgent {
    private static Instrumentation instrumentation;

    private ProbeAgent() {}

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;
        System.out.println("[agent] redefineSupported="
                + inst.isRedefineClassesSupported());
        System.out.println("[agent] primitiveModifiable="
                + inst.isModifiableClass(int.class));
        System.out.println("[agent] arrayModifiable="
                + inst.isModifiableClass(String[].class));
    }

    public static void redefineIfPossible(Class<?> target, Path replacement)
            throws IOException, ClassNotFoundException, UnmodifiableClassException {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Start with -javaagent");
        }
        boolean modifiable = inst.isModifiableClass(target);
        System.out.println("[agent] targetModifiable=" + modifiable);
        if (!inst.isRedefineClassesSupported() || !modifiable) {
            System.out.println("[agent] skip redefine");
            return;
        }

        byte[] classBytes = Files.readAllBytes(replacement);
        inst.redefineClasses(new ClassDefinition(target, classBytes));
        System.out.println("[agent] redefine complete");
    }
}
```

The agent stores the `Instrumentation` received in `premain`. It prints the capability and the modifiability of primitive/array classes, then exposes a small helper for the demo application to call. In a production agent, redefinition should be driven by an agent management interface rather than forcing business application code to call it directly.

`redefineIfPossible` reads the bytes **only after both conditions pass**. The `redefine complete` log line appears **only after `redefineClasses` returns normally**. This exercise runs sequentially on the main thread; in a multi-threaded design, you must safely manage publication of the `Instrumentation` object and the agent's lifecycle.

### 6.4. `src/main/demo/redefine/App.java`

```java
package demo.redefine;

import java.nio.file.Path;

public final class App {
    private App() {}

    public static void main(String[] args) throws Exception {
        Greeting existing = new Greeting(7);
        System.out.println("[app] before=" + existing.message());
        System.out.println("[app] initCountBefore="
                + Greeting.initializationCount());

        ProbeAgent.redefineIfPossible(Greeting.class,
                Path.of("patch", "demo", "redefine", "Greeting.class"));

        System.out.println("[app] after=" + existing.message());
        System.out.println("[app] newObject=" + new Greeting(9).message());
        System.out.println("[app] initCountAfter="
                + Greeting.initializationCount());
    }
}
```

We **keep the same `existing` instance** before and after redefinition. If successful, new method calls on the old instance use the new code, while `id` does not change on its own. The static `initializationCount` variable will show that the JVM does not re-run the static initializer.

### 6.5. Two Manifests

Contents of `agent-on.mf`:

```text
Manifest-Version: 1.0
Premain-Class: demo.redefine.ProbeAgent
Can-Redefine-Classes: true

```

Contents of `agent-off.mf`:

```text
Manifest-Version: 1.0
Premain-Class: demo.redefine.ProbeAgent

```

Both JARs contain the **exact same `ProbeAgent` code**; only the manifest differs. Keep the trailing newline at the end of each manifest file.

### 6.6. Compiling and Building the Agent JARs

In the `redefine-demo/` directory, with Bash:

```bash
mkdir -p out patch

javac --release 17 -d out \
  src/main/demo/redefine/Greeting.java \
  src/main/demo/redefine/ProbeAgent.java \
  src/main/demo/redefine/App.java

javac --release 17 -d patch \
  src/patch/demo/redefine/Greeting.java

jar --create --file agent-on.jar --manifest agent-on.mf \
  -C out demo/redefine/ProbeAgent.class

jar --create --file agent-off.jar --manifest agent-off.mf \
  -C out demo/redefine/ProbeAgent.class
```

With Windows PowerShell (one command per line):

```powershell
New-Item -ItemType Directory -Force -Path out,patch | Out-Null
javac --release 17 -d out src/main/demo/redefine/Greeting.java src/main/demo/redefine/ProbeAgent.java src/main/demo/redefine/App.java
javac --release 17 -d patch src/patch/demo/redefine/Greeting.java
jar --create --file agent-on.jar --manifest agent-on.mf -C out demo/redefine/ProbeAgent.class
jar --create --file agent-off.jar --manifest agent-off.mf -C out demo/redefine/ProbeAgent.class
```

`--release 17` produces source/classfile output targeting Java 17. No external libraries are required. After building:

```text
out/demo/redefine/Greeting.class     original definition
out/demo/redefine/ProbeAgent.class   agent entry point
out/demo/redefine/App.class          main class
patch/demo/redefine/Greeting.class   replacement definition bytes
agent-on.jar                          JAR declaring the capability
agent-off.jar                         JAR not declaring the capability
```

**Do not add `patch/` to `-cp`**. The program reads the patch file using `Files.readAllBytes` from the working directory. If you run `java` from a different directory, the `patch/...` path may not exist.

### 6.7. Running the Agent With Redefine Capability

```bash
java -javaagent:agent-on.jar -cp out demo.redefine.App
```

Stdout **verified on Zulu/OpenJDK 24.0.2**, with code compiled using `--release 17`:

```text
[agent] redefineSupported=true
[agent] primitiveModifiable=false
[agent] arrayModifiable=false
[app] before=original-7
[app] initCountBefore=1
[agent] targetModifiable=true
[agent] redefine complete
[app] after=updated-7
[app] newObject=updated-9
[app] initCountAfter=1
```

Analysis:

1. The agent requested `Can-Redefine-Classes: true`, and the test JVM granted the capability.
2. Primitive `int.class` and array `String[].class` are not modifiable even though the agent has the capability.
3. `Greeting.class` has `modifiable=true` in this JVM.
4. The agent used bytes from `patch/.../Greeting.class` in `ClassDefinition`, and redefinition succeeded.
5. **The same old `existing` object** calls `message()` again and returns `updated-7`. The new object returns `updated-9`.
6. `initializationCount` remains `1`, because redefinition does not re-execute `<clinit>`.

### 6.8. Running the Agent Without Declaring Redefine Capability

```bash
java -javaagent:agent-off.jar -cp out demo.redefine.App
```

Stdout on the same Zulu/OpenJDK 24.0.2:

```text
[agent] redefineSupported=false
[agent] primitiveModifiable=false
[agent] arrayModifiable=false
[app] before=original-7
[app] initCountBefore=1
[agent] targetModifiable=true
[agent] skip redefine
[app] after=original-7
[app] newObject=original-9
[app] initCountAfter=1
```

`targetModifiable=true` **still appears**, even though `redefineSupported=false` due to the missing manifest capability. The agent checked the condition and **did not call `redefineClasses`**, so the original method code remained unchanged.

Both runs were executed on **two separate fresh JVMs**. On another JVM vendor or configuration, `isRedefineClassesSupported` and `isModifiableClass` may differ; only the unmodifiability of primitive and array classes is consistently specified.

### 6.9. Inspecting the JARs and Both Class Files

```bash
jar --list --file agent-on.jar
jar --list --file agent-off.jar
javap -p -s -classpath out demo.redefine.Greeting
javap -p -s -classpath patch demo.redefine.Greeting
```

The two `javap` commands let you compare **field/method descriptors and class names** between the original and the patch. You can also use `javap -v` to inspect the classfile version, constant pool, and attributes. They read artifacts on disk, **not the bytecode already redefined inside the JVM**.

Inspect `META-INF/MANIFEST.MF` **inside each JAR** using a ZIP/JAR viewer: `agent-on.jar` must contain `Can-Redefine-Classes: true`, while `agent-off.jar` must not. Looking at the JAR filename alone does not prove the manifest is right.

## 7. What "Successful Redefinition" Means for a Running JVM

Redefinition does not mean the JVM "reloads the class from scratch" or creates new objects automatically. Several important consequences follow:

- **Existing instances remain**, with their fields keeping their original values. The exercise shows `existing` keeping `id=7` while subsequent invocations of `message()` run the new code.
- **Static state is preserved**; `<clinit>` is not re-run automatically. Thus `initializationCount` stays `1`, even though the patch class file still declares the static initializer.
- **Active stack frames**: if a thread is already executing the old method when redefinition occurs, the running frame may continue using the old bytecode; new invocations use the new definition. Do not assume every thread switches opcodes mid-method immediately.
- **Class identity does not change**: you are replacing the definition of an already-loaded `Class<?>`, not defining another class with the same name via a different loader.
- **Other transformers may participate** during redefinition, so the bytes finally installed in the JVM may differ from the initial bytes supplied by the caller.
- **There is no automatic rollback** simply from detaching an agent or closing a control connection. To revert to the old logic, you must prepare valid bytes of the old definition and apply them again (if the JVM permits), along with checking runtime state.

Therefore, a hot-patch can successfully replace method code yet still break business logic if the new code is incompatible with **existing static values and instance state**.

## 8. Class Schema Restrictions and Errors After Both Checks

Even when both booleans return `true`, the JVM can still reject the new bytes. In standard redefinition, you can replace method bodies and compatible metadata, but **you cannot arbitrarily change the class schema**:

- Adding, removing, or renaming fields or methods.
- Prohibited changes to method descriptors, modifiers, or interface/superclass hierarchy.
- Changing structural attributes such as `NestHost`, `NestMembers`, `Record`, or `PermittedSubclasses` in violation of JVMTI rules.
- Supplying invalid bytes or bytes containing broken opcodes, stack maps, or constant-pool references.
- Using a classfile version newer than the runtime supports.

A patch that only changes a string inside `message()` like the example is the minimal case. For complex method body transformations, use an appropriate bytecode library or Class-File API and run the verifier and tests on the target JVM.

| Error / Situation | Cause and How to Handle |
| --- | --- |
| `isRedefineClassesSupported()==false` | Check `Can-Redefine-Classes` in the actual manifest, or the JVM does not grant the capability. |
| `isModifiableClass(clazz)==false` | This class cannot be modified; primitives/arrays are always false, other classes depend on the VM. |
| `modifiable=true` but `supported=false` | Do not call redefine: agent-level capability is insufficient. |
| `UnsupportedOperationException` | The VM does not allow redefinition **or** the class structural change exceeds limits. |
| `UnmodifiableClassException` | One of the classes requested for redefinition is not modifiable. |
| `ClassFormatError` / `VerifyError` | Class file bytes are malformed or bytecode verification failed. |
| `NoClassDefFoundError` | The class name in the replacement bytes does not match the target class. |
| `UnsupportedClassVersionError` | The JVM does not understand the classfile version of the new bytes. |
| `ClassCircularityError` / `LinkageError` | Dependency structure or linkage errors after transformation. |
| `NullPointerException` | Passing null into `ClassDefinition` or the `ClassDefinition...` array. |
| `IOException` reading patch | Wrong path, missing permissions, or nonexistent file — occurs before the redefine step. |

The `redefineClasses(ClassDefinition...)` API declares `throws ClassNotFoundException, UnmodifiableClassException`. The Java SE 17 documentation notes that `ClassNotFoundException` is present **only for compatibility** and is never actually thrown by this method. The sample program still declares it because the compiler requires it per the method signature.

**Atomicity across a set of classes:** If `redefineClasses(...)` throws an exception for an array of `ClassDefinition`, by contract **none of the classes in the set are redefined**. This is helpful when multiple classes depend on each other, but it does not mean external byte selection or build artifacts are rolled back automatically; you must prepare all data before calling.

## 9. Ordered Diagnostic Workflow

If a tool reports "redefine is not working", follow this checklist rather than guessing from the JVM name:

1. **Right agent JAR?** Trace `-javaagent:path.jar` or the actual Attach path; inspect `META-INF/MANIFEST.MF` inside that file.
2. **Right entry point?** Startup requires `Premain-Class` and `premain`; attach requires `Agent-Class` and `agentmain` (if supported).
3. **Capability flag present?** `Can-Redefine-Classes: true` in the right agent manifest; `Can-Retransform-Classes` does not substitute.
4. **What does runtime report?** Print `isRedefineClassesSupported()` right after receiving `Instrumentation`; if false, do not attempt redefinition.
5. **Which target class?** Confirm the binary name, defining loader, module, and selected `Class<?>`. Do not use a `Foo.class` resource from another loader as patch bytes without checking.
6. **Is the class modifiable?** Query `isModifiableClass(target)` for **each** class; do not infer from the general capability.
7. **Is the patch valid?** Compare both versions with `javap -p -s`, check classfile version, and inspect bytecode output; ensure method/field schemas remain compatible.
8. **Any other transformers?** If so, check transformation order and the bytes after each step; errors can arise after your patch bytes are submitted.
9. **Which error is thrown?** Distinguish `UnsupportedOperationException`, `UnmodifiableClassException`, class format/linkage errors, and `IOException` when reading the file.
10. **Runtime post-check:** Re-run the method on old and new instances, and verify state and running threads. Do not conclude the whole application is healthy just because the API call did not throw.

For production, use patches from trusted sources with proper checksums/signatures, audit logging, staging tests, and a recovery plan. Redefinition can alter application behavior with high privilege; never let unauthenticated paths control the patch bytes.

## 10. Common Misconceptions to Avoid

| Misconception | Accurate Understanding |
| --- | --- |
| "A Java agent can redefine any class." | JVM capability is optional, and each class must also be modifiable. |
| "`isModifiableClass==true` means redefine capability is enabled." | False: this check does not depend on the capability. |
| "Declaring true in the manifest guarantees JVM support." | False: the JVM must also allow it. |
| "Having `Can-Retransform-Classes` is enough to call redefine." | False: they are two separate capabilities. |
| "`String[].class` is a normal class so it can be modified." | False: array and primitive classes are always unmodifiable. |
| "Passing both booleans means you can add a new field." | False: schema change restrictions still apply. |
| "`ClassDefinition` reads bytes from disk automatically." | False: the caller must supply the new `byte[]`. |
| "`ClassDefinition` clones the bytes so another thread can mutate the array." | False: it holds a reference to the input array. |
| "Redefine re-runs constructors of existing instances." | False: instances retain their existing field values. |
| "Redefine re-runs `<clinit>` to reset static fields." | False: static state remains intact. |
| "All old stack frames immediately switch to the new method body." | False: active frames may continue executing the old code. |
| "Replacing the JAR on disk automatically updates loaded classes." | False: an explicit redefine call with valid bytes or another mechanism is required. |

## 11. Self-Check Exercises

**Question 1.** An agent sees `isModifiableClass(Greeting.class)==true`, but `isRedefineClassesSupported()==false`. Should it call `redefineClasses`?

**Answer:** No. The class is modifiable in principle, but the agent lacks the capability. Check the manifest/JVM and do not call the API.

**Question 2.** What if `Can-Redefine-Classes: true` is set, but `isModifiableClass(int.class)==false`?

**Answer:** Skip the primitive class. Having the general capability does not make primitives or arrays modifiable.

**Question 3.** Why do the two JARs in the example contain the exact same `ProbeAgent.class` yet produce different capability outputs?

**Answer:** `agent-on.jar` declares `Can-Redefine-Classes: true`, whereas `agent-off.jar` omits the flag (defaulting to false). The JVM in the example supports it when the agent requests it.

**Question 4.** Why does `existing.message()` return `updated-7` after redefinition while `initializationCount` remains `1`?

**Answer:** **New** method invocations use the new code, whereas instance and static state are not re-initialized. The JVM does not automatically invoke `<clinit>` upon redefinition.

**Question 5.** A patch adds an `extra` field, even though the class is modifiable and the VM is supported. Is it guaranteed to succeed?

**Answer:** No. The two checks do not validate the schema of the new bytes; the JVM may throw `UnsupportedOperationException` for a prohibited structural change.

**Question 6.** Is `ClassDefinition(clazz, bytes)` safe if another thread modifies the `bytes` array afterward?

**Answer:** No. The constructor does not copy the buffer; finalize and validate the bytes and do not mutate them while in use.

**Question 7.** Can you identify the right class using only `clazz.getName()`?

**Answer:** Not enough in a multi-loader environment: the same name can refer to different runtime classes. You must care about the defining loader and the `Class<?>` object itself.

**Question 8.** If you call redefine for multiple classes and one class has a format error, should you assume the remaining classes were updated?

**Answer:** No. By contract, if `redefineClasses` throws an exception, **none of the classes in that set are redefined**.

**Question 9.** Is `isModifiableModule(module)==true` enough to prove `isModifiableClass(clazz)==true`?

**Answer:** No. Modifying a module and modifying a class have different APIs and contracts.

## 12. Summary and Authoritative References

**Pre-redefine rule:**

```text
Agent manifest requests Can-Redefine-Classes: true
          +
JVM grants the capability
          |
          v
isRedefineClassesSupported() == true
          +
Identify exact Class<?> and isModifiableClass(clazz) == true
          +
New class-file bytes are valid and do not violate schema
          |
          v
redefineClasses(new ClassDefinition(clazz, bytes))
          |
          v
Handle exceptions, verify method invocation/state
```

Key takeaways:

1. `isRedefineClassesSupported` checks **agent/JVM capability**, while `isModifiableClass` checks **each specific class**; both are required.
2. Primitive and array classes are always unmodifiable. An ordinary class can be `modifiable=true` even when the agent does not yet have redefine capability.
3. Both booleans being true does **not** guarantee a valid `ClassDefinition`; you must verify the name, schema, classfile version, and bytecode.
4. Redefinition can change the method body for new invocations on **existing instances**, but it does not re-run static/instance initialization and does not clear field values.
5. In production, verify the JAR manifest of the actual artifact, ensure patch bytes are trusted, and check runtime behavior after the change.

**Authoritative sources:**

- [Java SE 17 — `Instrumentation`: isRedefineClassesSupported, isModifiableClass, redefineClasses](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [Java SE 17 — `java.lang.instrument`: Premain-Class, Agent-Class, Can-Redefine-Classes](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [Java SE 17 — `ClassDefinition`: binding class + bytes, no array copy](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html)
- [Java SE 17 — `ClassFileTransformer`: callback with redefinition](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [JVMTI — `RedefineClasses`: schema change scope, stack frames, and runtime state](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html#RedefineClasses)
- [Java SE 17 — `java` launcher: `-javaagent`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)