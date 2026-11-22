# `redefineClasses`: Replacing a Class Definition with Bytecode Provided via `ClassDefinition`

## 1. Goal and Context

Java Instrumentation does not only intercept classes when the JVM loads them for the first time. With a supporting JVM and an agent that has requested the appropriate capability, an agent can **replace the definition of an already loaded class** with new class file bytes provided by the agent itself:

```java
instrumentation.redefineClasses(
        new ClassDefinition(Target.class, replacementClassFileBytes));
```

The two most important takeaways of this lesson:

1. **`ClassDefinition` is a pair of the target `Class<?>` and a `byte[]` containing the *entire* new class file**, not a file/JAR name pair, Java source, a method body snippet, or an arbitrary "patch".
2. **`Instrumentation.redefineClasses(...)` is a request for the JVM to install a new definition for an *already existing* class**. It uses the supplied bytes, performing validation and structural constraint checks; it does not automatically re-read `.java` files or search for the latest `.class` file on the classpath.

This differs from loading a class with a new name. If `Target` has already been defined by a class loader, `redefineClasses` preserves the **same class identity**, existing live objects, and appropriate runtime state; only the parts of the definition that the JVM permits are updated.

Some use cases: debugger "fix and continue", replacing method bodies in a running application, observability tools needing to update pre-compiled bytecode, or an agent pipeline that proactively generates bytes and passes them into the JVM.

**Version:** Examples use **Java 17+** and the standard `java.lang.instrument` API. Redefinition is an **optional capability** of the JVM; you should not infer from the JDK version number that every runtime grants it. Always check before operating.

## 2. Exact API: `ClassDefinition` and `Instrumentation.redefineClasses`

### 2.1. What Does `ClassDefinition` Contain?

`ClassDefinition` belongs to the `java.lang.instrument` package:

```java
public final class ClassDefinition {
    public ClassDefinition(Class<?> theClass, byte[] theClassFile);
    public Class<?> getDefinitionClass();
    public byte[] getDefinitionClassFile();
}
```

This is a condensed signature summary, **not standalone class source code**. Meaning:

- `theClass`: **the exact `Class<?>` object of the already loaded class** that you want to redefine. The same binary name in two different class loaders can be two distinct class identities.
- `theClassFile`: a `byte[]` array containing a **complete class file** with the JVM class file structure (starting with magic `CAFEBABE`, constant pool, methods, attributes...), not the standalone bytecode of a single method.
- The constructor **does not copy the byte array**, it only holds a reference. If another program modifies the array after creating `ClassDefinition`, the definition content may no longer match expectations. Treat the bytes as **immutable for the duration of the call**.
- Neither the class object nor the array may be `null`; the constructor throws `NullPointerException` when either is missing.
- `getDefinitionClass()` and `getDefinitionClassFile()` return the two paired components.

Why not pass just the class name? **Class identity in the JVM is determined by the name and the defining class loader**. `Class<?>` eliminates ambiguity when the same name exists across multiple plugins, application loaders, custom loaders, or module layers.

### 2.2. What Does `redefineClasses` Do?

Java SE 17 API:

```java
void redefineClasses(ClassDefinition... definitions)
        throws ClassNotFoundException, UnmodifiableClassException;
```

The method accepts **varargs**: one or more `ClassDefinition` instances. The JVM replaces the definitions for the exact specified classes with their corresponding bytes, after applying transformers and verifying the necessary conditions.

`ClassNotFoundException` remains in the signature **for API compatibility**; the Java 17 Javadoc states that this method **does not actually throw** that exception. In simple examples you can use `throws Exception` to avoid obscuring example errors; production code should distinguish actual errors such as `UnmodifiableClassException`, `UnsupportedOperationException`, and `LinkageError` subclasses.

Calling **`redefineClasses()` with an empty array** changes nothing. When passing multiple `ClassDefinition` instances in a single call, the API allows changing interrelated classes together as a set; **if the call throws an exception, no class in the set is redefined**.

### 2.3. What the Agent Must Provide Itself

`redefineClasses` does **not** automatically:

- Find or compile a recently modified `.java` file;
- Read `.class` files from the latest build directory;
- Scan the classpath and pick a class with the same name;
- Automatically generate new bytes from the current body;
- Enable the capability when the manifest is missing it;
- Allow changing arbitrary modifiers, fields, methods, or inheritance relationships.

The agent must obtain/generate **full replacement class-file bytes** (for example via `Files.readAllBytes`, ASM, Byte Buddy, or the Class-File API on a suitable JDK), verify the target identity, and explicitly invoke the API.

## 3. Capability: Two Separate Conditions

### 3.1. The Agent JAR Manifest

For an agent passed to the JVM via `-javaagent`, the manifest must declare:

```text
Manifest-Version: 1.0
Premain-Class: RedefineAgent
Can-Redefine-Classes: true

```

- `Premain-Class` specifies the entry point of the agent running at JVM startup.
- `Can-Redefine-Classes: true` declares that the agent **needs** the redefine capability.
- This attribute resides in the **main section of `META-INF/MANIFEST.MF` in the actual agent JAR loaded by the JVM**.
- If omitted, set to `false`, or given a value other than `true` (case-insensitive), the requested capability defaults to **`false`**.
- An agent started via dynamic attach uses `Agent-Class`; the `Can-Redefine-Classes` requirement still needs to be considered in the loaded JAR.

**Do not confuse** `Can-Redefine-Classes` with `Can-Retransform-Classes`. The two capabilities are **independent**. Both can be requested, but enabling only retransformation does not substitute for the redefine permission.

### 3.2. Does the JVM Actually Support It?

```java
boolean supported =
        instrumentation.isRedefineClassesSupported();
```

The specification requires the capability to be supported when:

```text
Agent manifest requests Can-Redefine-Classes: true
                         AND
Current JVM provides the corresponding redefine capability
                         |
                         v
        isRedefineClassesSupported() == true
```

The result does not change within the same JVM invocation. If `false`, do not call `redefineClasses` hoping the JVM will enable it automatically; it may throw `UnsupportedOperationException`.

You also need to check the specific class:

```java
boolean modifiable = instrumentation.isModifiableClass(Target.class);
```

`isModifiableClass` is a **separate condition**. Primitive and array types are always unmodifiable; some special classes may be restricted by the runtime. A value of `true` **does not guarantee that every class file change is valid**.

**Gatekeeping checks:**

```java
if (!instrumentation.isRedefineClassesSupported()) {
    // Disable redefine functionality or choose a fallback.
} else if (!instrumentation.isModifiableClass(Target.class)) {
    // Target class cannot be modified in this runtime.
} else {
    // Can attempt redefine with valid bytes and matching class identity.
}
```

This is an **illustrative** snippet; the `instrumentation` and `Target` variables must be provided in an actual agent.

## 4. How Does Redefinition Happen?

```text
Running JVM
  |
  +-- Target class is already loaded, has Class<?> identity
  |
  +-- Agent obtains new .class version (byte[] from file/build/transform)
         |
         v
       new ClassDefinition(Target.class, replacementBytes)
         |
         v
       instrumentation.redefineClasses(...)
         |
         +--> JVM passes bytes through ClassFileTransformers
         |    registered for the redefine path (if any)
         |
         +--> validates name, version, schema, modifiers, frames,
         |    linkage, JVM/JVMTI constraints
         |
         +--> valid: installs new definition for Target
         |       new invocations -> new body
         |
         +--> error: throws exception/error
                 installs none of the changes in the redefine set
```

There are **two processing layers** to distinguish: `ClassDefinition` carries the bytes requested by the agent; if any `ClassFileTransformer` is registered, the JVM may still pass those bytes through the transformer chain **before installing the new definition**. Therefore, "using bytes provided by the agent" does not mean **bypassing all transformers**.

According to the `Instrumentation.addTransformer` Javadoc, registered transformers are invoked when a class is **loaded and redefined**; the `canRetransform` parameter governs behavior on **retransformation**, not whether it is invoked during redefine.

When `ClassFileTransformer.transform(...)` receives a redefine callback:

- `classBeingRedefined` is the target `Class<?>` object, not `null` as during initial load;
- `className` is the internal name in the form `demo/Service`;
- `loader` is the defining class loader of the target, which may be `null` for the bootstrap loader;
- `classfileBuffer` is the bytes at the current step in the transformer chain, and **the input array must not be modified in place**;
- The transformer may return a valid new byte array or `null` to perform no transformation.

Do not confuse a transformer's `return null` (do not modify bytes) with `ClassDefinition` being allowed to contain a `null` byte array (it is not).

## 5. What Are the Limits of Redefinition?

Java Redefinition is not **arbitrary hot swapping of any component**. According to JVM TI `RedefineClasses` and the limits referenced by the Java 17 Javadoc, you can typically change **method bodies**, the constant pool, and valid attributes, but you cannot arbitrarily:

- Add, remove, or rename already defined **fields** or **methods**;
- Change method descriptors/signatures, attributes affecting schema, or modifiers that the VM does not support;
- Change the superclass or the list of interfaces (class hierarchy);
- Change special structural attributes such as `NestHost`, `NestMembers`, `Record`, or `PermittedSubclasses` in disallowed ways;
- Provide a class file carrying a **different binary name** than the target `Class<?>` object;
- Provide a class-file version newer than the JVM supports or invalid bytes.

Limits may depend on the JVM and JVMTI version. **Do not assume the JVM supports every form of hot swap** just because `isRedefineClassesSupported() == true`.

### Changing the Body, Not the Schema

Designed for the demo:

```java
// Before
public static String text() {
    return "before";
}

// After: keep the same name, descriptor, modifiers, fields, hierarchy
public static String text() {
    return "after";
}
```

Schema changes that are unsafe in most common JVMs:

```java
// Replacement adds a new field, even with the same binary name:
private int newlyAddedField;
```

For an already loaded class, the JVM may reject this with `UnsupportedOperationException` or an appropriate error due to unsupported structural changes. Do not use "it compiles" to conclude "it can be redefined".

### Do Not Modify the Static Initializer Expecting It to Re-run

The new definition **does not trigger an automatic re-run of `<clinit>`** and does not reset static fields. You can change the initializer code in the class file, but already initialized classes are **not automatically initialized a second time** by a redefine call.

## 6. Complete Java 17 Example: `before` → `after` Using `ClassDefinition`

We create **two `MessageService.class` files with the same binary name** but different method bodies:

- Version **v1** is loaded by the app at startup.
- Version **v2** is read into a `byte[]` **after the v1 class has already been loaded**.
- The agent creates `ClassDefinition(MessageService.class, v2Bytes)` and calls `redefineClasses`.
- The app calls the same method of the **same class identity** again and receives the new result.
- A static counter shows that state is not reset upon redefine.

The example uses no external libraries and **does not require the JDK 24 Class-File API**; it uses only JDK 17+.

### 6.1. Directory Structure

```text
redefine-demo/
├── src/
│   ├── v1/
│   │   └── MessageService.java
│   ├── v2/
│   │   └── MessageService.java
│   ├── agent/
│   │   └── RedefineAgent.java
│   └── app/
│       └── DemoApp.java
└── agent.mf
```

After building, there will be `build/v1/MessageService.class`, `build/v2/MessageService.class`, `agent.jar`, and `app.jar`. Having two source files with the same class name is **intentional**; they are compiled **separately twice into two different directories**.

### 6.2. `src/v1/MessageService.java`

```java
public final class MessageService {
    private static int calls = 100;

    private MessageService() {
    }

    public static String text() {
        calls++;
        return "before";
    }

    public static int calls() {
        return calls;
    }
}
```

The first version initializes `calls = 100` when the JVM actually initializes the class. Each call to `text()` increments the counter.

### 6.3. `src/v2/MessageService.java`

```java
public final class MessageService {
    private static int calls = 100;

    private MessageService() {
    }

    public static String text() {
        calls++;
        return "after";
    }

    public static int calls() {
        return calls;
    }
}
```

Comparing v1 and v2: **same class name, same fields, same modifiers, same names and descriptors for every method, same superclass**. The only intentional difference is the returned literal in the `text()` method.

Both the `private constructor` and `calls()` are preserved; nothing that the JVM might consider schema is changed.

### 6.4. `src/agent/RedefineAgent.java`

```java
import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class RedefineAgent {
    private static volatile Instrumentation instrumentation;

    private RedefineAgent() {
    }

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
        System.out.println(
                "[agent] supported="
                + inst.isRedefineClassesSupported());
    }

    public static void replace(Path replacementFile)
            throws IOException, UnmodifiableClassException,
                   ClassNotFoundException {

        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Agent not initialized");
        }

        if (!inst.isRedefineClassesSupported()) {
            System.out.println("[agent] skipped: unsupported");
            return;
        }

        if (!inst.isModifiableClass(MessageService.class)) {
            System.out.println("[agent] skipped: not modifiable");
            return;
        }

        // Read new class file byte[]: not Java source.
        byte[] replacementBytes =
                Files.readAllBytes(replacementFile);

        // Exact pair: loaded Class<?> and v2 bytes.
        ClassDefinition replacement = new ClassDefinition(
                MessageService.class, replacementBytes);

        // If successful, new method invocations use the v2 definition.
        inst.redefineClasses(replacement);

        System.out.println("[agent] redefine completed");
    }
}
```

Explanation:

- `premain` receives `Instrumentation` when the JVM starts with `-javaagent`. The demo stores the instance in a `volatile` field for later invocation from the application.
- `isRedefineClassesSupported()` and `isModifiableClass(MessageService.class)` are checked first.
- `Files.readAllBytes` provides the **raw contents of `build/v2/MessageService.class`**. It does **not** load/define the v2 class in the JVM.
- `MessageService.class` is the `Class<?>` object already loaded by the runtime, **not** a new v2 class instance.
- `ClassDefinition` pairs the class identity and the bytes; `redefineClasses` is the step that asks the JVM to replace the body.
- No other transformer is registered in the example, so the bytes from the file are the direct input for validation/installation of the definition.
- The demo lets API errors propagate for easy observation. A production agent needs logging, artifact verification, and an appropriate rollback or fail-safe strategy.

### 6.5. `src/app/DemoApp.java`

```java
import java.nio.file.Path;

public final class DemoApp {
    private DemoApp() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: DemoApp <replacement-class-file>");
        }

        // First use v1, ensuring the class is loaded/initialized.
        System.out.println("[main] before="
                + MessageService.text());
        System.out.println("[main] callsBefore="
                + MessageService.calls());

        // Read v2 bytes and redefine immediately in the same JVM.
        RedefineAgent.replace(Path.of(args[0]));

        System.out.println("[main] after="
                + MessageService.text());
        System.out.println("[main] callsAfter="
                + MessageService.calls());
    }
}
```

`MessageService.class` always points to the **same class identity**. No `new ClassLoader()` is used to load a second copy of `MessageService`.

### 6.6. `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: RedefineAgent
Can-Redefine-Classes: true

```

This is the manifest of **agent.jar**, not the v1/v2 class files or `app.jar`. Ensure there is a trailing blank line ending the main section. `Premain-Class` must be the exact binary name of the agent (`RedefineAgent` is in the default package).

### 6.7. Compiling and Running on Linux/macOS/WSL (POSIX shell)

Standing in the `redefine-demo/` directory containing `agent.mf`:

```bash
mkdir -p build/v1 build/v2

# The class version that will actually be loaded by the JVM initially.
javac --release 17 -d build/v1 src/v1/MessageService.java

# The replacement keeps the same binary name but has a new method body.
javac --release 17 -d build/v2 src/v2/MessageService.java

# The compiler for the app and agent only sees the v1 class.
javac --release 17 -cp build/v1 -d build/v1 \
  src/agent/RedefineAgent.java src/app/DemoApp.java

# The agent only carries the RedefineAgent class and the capability manifest.
jar --create --file agent.jar --manifest agent.mf \
  -C build/v1 RedefineAgent.class

# The app JAR only carries v1; do NOT put v2 on the classpath.
jar --create --file app.jar \
  -C build/v1 DemoApp.class -C build/v1 MessageService.class

java -javaagent:agent.jar -cp "agent.jar:app.jar" \
  DemoApp build/v2/MessageService.class
```

**Expected stdout** on HotSpot/JDK 17+ with redefinition support:

```text
[agent] supported=true
[main] before=before
[main] callsBefore=101
[agent] redefine completed
[main] after=after
[main] callsAfter=102
```

Meaning of each line:

1. The agent is started by the JVM, the manifest requests the capability, and the JVM grants redefine capability.
2. Method `MessageService.text()` in v1 returns `"before"`; the first call increments `calls` from 100 to 101.
3. The agent uses bytes from `build/v2/MessageService.class` via `ClassDefinition` to install the new body.
4. Method `text()` on new invocations returns `"after"`.
5. Static field `calls` **continues from 101 to 102**, without resetting to 100; the class initializer does not re-run because of redefine.

If the JVM does not support it, the program takes the `skipped` branch and the final call still returns `"before"`, with the count reaching 102. This is a controlled fallback path, **not** proof that redefine succeeded.

### 6.8. Windows PowerShell

On Windows, use **`;`** instead of `:` in the classpath, and create directories using the PowerShell command:

```powershell
New-Item -ItemType Directory -Force build/v1, build/v2 | Out-Null

javac --release 17 -d build/v1 src/v1/MessageService.java
javac --release 17 -d build/v2 src/v2/MessageService.java
javac --release 17 -cp build/v1 -d build/v1 src/agent/RedefineAgent.java src/app/DemoApp.java

jar --create --file agent.jar --manifest agent.mf -C build/v1 RedefineAgent.class
jar --create --file app.jar -C build/v1 DemoApp.class -C build/v1 MessageService.class

java -javaagent:agent.jar -cp "agent.jar;app.jar" DemoApp build/v2/MessageService.class
```

To avoid environment dependencies, keep the working directory location exact: the replacement file argument is passed to the application and `Path.of(args[0])` is resolved **relative to the current directory**.

### 6.9. Verifying That There Are Two Distinct Artifacts

```bash
javap -classpath build/v1 -c MessageService
javap -classpath build/v2 -c MessageService

jar --list --file agent.jar
jar --list --file app.jar
```

The two `javap` runs will show that `text()` of v1 and v2 use different literals; constant pool indices may differ between builds. `agent.jar` contains `RedefineAgent.class` and the manifest; `app.jar` contains `DemoApp.class` and **v1 `MessageService.class`**.

**Do not delete/overwrite `build/v1/MessageService.class` with the v2 version before running**: if the app accidentally loads v2 from the start, the example no longer proves in-process definition replacement.

## 7. What Is Actually Preserved After Redefine?

### 7.1. Class Identity and Existing Objects

Redefinition does not create a new class identity. Instances of the class remain instances of the **same class**; existing fields and their values are preserved.

```text
Before:
  Class<?> identity = MessageService.class
  Existing object -> v1 methods

After redefine:
  Class<?> identity = MessageService.class  // still the same identity
  Existing object -> new method invocations use v2
```

If a method changes behavior while keeping the same signature, old objects can invoke the new body. Do not assume that objects are automatically recreated, constructors are re-invoked, or state is automatically migrated.

### 7.2. Static State and Class Initializer

The Javadoc specifies that redefinition does not trigger class initialization beyond normal semantics and **does not re-run the initializer**. Static variable values remain as they were before the call. In the demo, the counter goes from 101 to 102; a static initializer `calls = 100` in the v2 bytes does **not** re-run.

If new logic requires new state, you must design compatibility-preserving migration, and you cannot add fields to an already loaded class if the JVM does not support schema changes.

### 7.3. Active Stack Frames

If a thread has already entered a v1 method **before** redefine, the active frame continues executing the **old bytecode**. New invocations will execute the v2 body.

```text
Thread A:  enter slowOperation() in v1
              |
Thread B:     redefineClasses(v2) succeeds
              |
Thread A:  old frame continues executing v1 code
Thread C:  new invocation runs v2 body
```

Therefore, **"redefine returning successfully" does not mean every running frame switches bytecode instantaneously**. Do not use redefine as a synchronization primitive or to guarantee that all threads cross a single cutover point simultaneously.

### 7.4. Synchronization and Side Effects

If v2 code changes lock ordering, event emission, metric configuration, or dependencies, new invocations exhibit the new behavior while old invocations may still be completing with the old code. Both the agent and the application need to consider compatibility between the two versions, especially across modules/class loaders and long-running transactions.

## 8. `redefineClasses` vs. `retransformClasses`

| Criterion | `redefineClasses(ClassDefinition...)` | `retransformClasses(Class<?>...)` |
| --- | --- | --- |
| Goal | Replace the definition of an already loaded class | Re-run the transformation pipeline for an already loaded class |
| Byte source | The agent **provides the full new bytes itself** in `ClassDefinition` | The JVM starts from the base bytes of the most recent load/redefine and applies transformers |
| Class selection | `Class<?>` object inside each `ClassDefinition` | List of `Class<?>` |
| Capability | `Can-Redefine-Classes` + VM support | `Can-Retransform-Classes` + VM support |
| Check API | `isRedefineClassesSupported()` | `isRetransformClassesSupported()` |
| Registered transformer required beforehand? | **Not required**; can use pre-built bytes | Not required to call, but transformers determine bytecode changes |
| Are transformers invoked? | Transformers registered for class redefinition will be invoked | Transformers with `canRetransform=true` are invoked; results from `false` transformers are reused |
| Arbitrary structural changes? | **No**; subject to JVMTI constraints | **No**; subject to JVMTI constraints |
| Typical use | Fix-and-continue, replacing method bodies with a new class file | Tracing/coverage re-running transformations |

Both allow an already loaded class to receive new bytecode without restarting the JVM, but they have **two different bytecode sources and two different capabilities**.

One easy point of confusion: `redefineClasses` **can invoke registered transformers even when they were added with `canRetransform=false`**, because that flag classifies **retransformation** handling. Do not equate "transformer does not support retransform" with "transformer does not run during redefine".

## 9. Redefining Multiple Classes in One Call

A single call can carry multiple pairs:

```java
ClassDefinition first = new ClassDefinition(
        FirstService.class, firstBytes);

ClassDefinition second = new ClassDefinition(
        SecondService.class, secondBytes);

instrumentation.redefineClasses(first, second);
```

This is an **illustrative snippet**, not a standalone program; the agent must prepare `instrumentation`, both classes, and both byte arrays.

Reason for using one call for a set: two classes may be interrelated and need to be updated together, for example A's method body starts calling B's new behavior. By contract, **if the operation throws an exception, no class in the set is redefined**. This is **all-or-nothing when the call fails**, not a business data transaction, and it does not guarantee that every active thread will observe the same method version at the exact same instant.

Useful practices:

- Verify the name, schema, class file version, and class loader of **each** pair before calling.
- Do not repeat the same `Class<?>` twice in one batch because the request is ambiguous, hard to debug, and provides no benefit.
- Use a tested byte variant, checking compatibility with other classes in the JVM.
- Save the artifact version and a rollback plan **before** making changes; only use old bytes as a rollback if they still satisfy the current schema/loader and runtime capabilities.

If one replacement in the set is invalid, the entire attempt can fail. Therefore, batches should be small enough and have a cohesive purpose.

## 10. Common Errors and How to Diagnose Them

| Symptom | Common Cause | How to Handle |
| --- | --- | --- |
| `isRedefineClassesSupported() == false` | Manifest missing `Can-Redefine-Classes: true` or VM does not support it | Check the **actual loaded agent JAR**, current JVM, and capability |
| `UnsupportedOperationException` on call | Capability not granted or replacement requests disallowed changes | Check manifest, class schema, and JVMTI constraints |
| `UnmodifiableClassException` | A target class is not modifiable | Check `isModifiableClass` per class; skip special classes |
| `ClassFormatError` | Bytes are not a valid class file | Read the proper `.class`, avoid mixing in source/ZIP/empty bytes; verify |
| `NoClassDefFoundError` | Class name in bytes does not match target `Class<?>` | Cross-check internal/binary name, correct class file and loader |
| `UnsupportedClassVersionError` | Class file version is higher than target JVM supports | Build with `javac --release 17` or an appropriate target version |
| `LinkageError` or `VerifyError` | Invalid bytecode/hierarchy/linkage state | Check stack maps, method descriptors, references/module/class loader |
| Adding field/method causes error | Schema change not supported by the JVM | Only change method bodies/valid constant pool entries, do not alter structure |
| Redefine succeeds but method still returns old value on a thread | Old stack frame continues executing v1 bytecode | Check new invocations and call timing |
| Static counter does not reset | This is the expected semantics: initializer does not re-run | Do not rely on redefinition to reset state |
| v2 code is on disk but runtime does not change | API not called, reading wrong path, loading wrong version, or capability is false | Log path/bytes, check class identity, API result |
| Only putting v2 JAR on `-cp` expecting v1 class to change automatically | Class loading does not automatically replace an already defined class identity | Requires `ClassDefinition` and `redefineClasses` |
| Redefine in a multi-agent environment behaves unexpectedly | Another `ClassFileTransformer` also runs on the new bytes | Check transformer list and order, transformation ownership |
| Call throws error when a batch has multiple classes | One replacement violates a constraint | Verify each pair, then **intentionally** retry with the fixed batch; do not partially mutate old classes |

**Which errors are checked?** `UnmodifiableClassException` and `ClassNotFoundException` appear in the signature. Many other important errors are unchecked exceptions or `Error`s. Do not write `catch (Exception)` and claim you have caught every class file error. For production, distinguish error types, log appropriately, and avoid accidentally swallowing `LinkageError`.

## 11. Safe Implementation Checklist for Agents

1. **Check capability:** manifest `Can-Redefine-Classes: true` + `isRedefineClassesSupported()`.
2. **Check target class:** use the exact `Class<?>` of the defining loader to modify and `isModifiableClass`.
3. **Prepare proper bytes:** full new class file, not source, ZIP/JAR bytes, or method-only instructions.
4. **Keep class identity and schema compatible:** do not change class name, field/method signatures, hierarchy, or unsupported modifiers.
5. **Choose a controllable byte source:** built artifact, verified bytecode emitter, or trusted snapshot.
6. **Do not mutate bytes after attaching to `ClassDefinition`:** the constructor does not copy the array.
7. **Account for other transformers:** redefine passes through the registered `ClassFileTransformer` chain.
8. **Preserve object/state lifecycle:** initializer does not re-run; old active frames may continue executing the old body.
9. **Verify output and rollback:** integration test on the real JVM/version; keep old artifacts and a controlled recovery plan.
10. **Monitor operations:** log target loader, artifact version, byte identifier/checksum, capability status, success/failure, and `ClassFormatError`/`LinkageError` errors.
11. **Batch intentionally:** multiple related classes can be replaced in one call, but do not treat the API as a business transaction or a barrier across threads.
12. **Do not over-request permissions:** the manifest should only request capabilities the agent genuinely needs; do not automatically use attach or alter module permissions when unrelated.

## 12. Self-Check Questions

**Question 1.** Does `ClassDefinition(Target.class, bytes)` create a new `Class<?>` or pair bytes with an existing class?

**Answer:** It only creates a parameter block pairing the **existing `Class<?>`** and the full bytes. It is `Instrumentation.redefineClasses` that asks the JVM to install the new definition.

**Question 2.** Does simply editing `Target.java` and re-running `javac` change the class in a running JVM?

**Answer:** No. The agent must obtain the new `Target.class` as a `byte[]`, check the target class/capability, and then call `redefineClasses`.

**Question 3.** Does `Can-Retransform-Classes: true` substitute for `Can-Redefine-Classes: true`?

**Answer:** No. These are two independent optional capabilities.

**Question 4.** Is redefining a v2 version with the same name/methods but one newly added field guaranteed to succeed?

**Answer:** No. Schema changes may be rejected by JVMTI/JVM. The demo keeps the field/method schema unchanged.

**Question 5.** Why is the counter in the demo 101 before and 102 after, instead of resetting to 100?

**Answer:** `redefineClasses` does not automatically re-run the class initializer and preserves static field values. Only the new method body is applied to subsequent invocations.

**Question 6.** Is a `canRetransform=false` transformer invoked when `redefineClasses` occurs?

**Answer:** It can be, and by contract registered transformers are invoked during class redefinition; the `canRetransform` parameter governs only the retransformation path.

**Question 7.** A batch redefining A and B throws an exception on replacement B: has A been half-changed?

**Answer:** By contract, if the call throws an exception, **no class is redefined**. However, that does not mean thread execution has transaction-like synchronized cutover.

## 13. Official Documentation

- [Oracle Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `redefineClasses`, `isRedefineClassesSupported`, `isModifiableClass`, static state/active frame semantics, and errors.
- [Oracle Java SE 17 — `ClassDefinition`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): `Class<?>` + `byte[]`; constructor does not copy the buffer.
- [Oracle Java SE 17 — package `java.lang.instrument`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): manifest attributes `Premain-Class`, `Agent-Class`, `Can-Redefine-Classes`, and `Can-Retransform-Classes`.
- [Oracle Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callbacks during load/redefine/retransform and transformation application order.
- [Oracle JVM TI — `RedefineClasses`](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html): class-file change limits, JVM interaction, and runtime semantics.
- [Java Virtual Machine Specification SE 17 — Chapter 4](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): class file format and versions.

**Remember:** `redefineClasses` **does not search for new code for you**; it replaces the definition of an already loaded class with **full class-file bytes** that you place in `ClassDefinition(Class<?>, byte[])`, subject to the appropriate JVM capabilities and constraints. Method bodies of new invocations can change, but class identity, instances, and static state are not automatically recreated or reset.
