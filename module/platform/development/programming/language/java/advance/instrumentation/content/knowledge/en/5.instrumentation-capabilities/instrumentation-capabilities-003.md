# `Can-Redefine-Classes` and `Instrumentation.isRedefineClassesSupported()`

A Java agent can replace the bytecode of an **already-loaded** class without restarting the JVM, but doing so requires a *capability* granted when the agent is loaded. The two names in the title answer two different questions:

- **`Can-Redefine-Classes`**: has the agent requested the JVM to allow **class redefinition** in `META-INF/MANIFEST.MF`?
- **`Instrumentation.isRedefineClassesSupported()`**: does the current JVM configuration **actually support** redefinition?

Even if the query returns `true`, not every class can be modified arbitrarily. The agent must still check **`Instrumentation.isModifiableClass(clazz)`**, provide valid **class file bytes** via `ClassDefinition`, and let the JVM verify the bytes when calling **`redefineClasses(...)`**.

## 1. What is class redefinition?

*Redefinition* replaces the definition of a class **currently existing in the JVM** with a new definition; typical uses include replacing method bodies during debugging, fixing logic in a development environment, or swapping bytecode for diagnostic tools. Unlike `ClassLoader#defineClass`, it does not define an additional independent class with the same name. The call takes the **actual `Class<?>` object** of the class to be modified, whose identity is tied to its class loader.

For example: class `demo.Message` has been loaded and `value()` returns `"old"`. You compile another version of `demo.Message`, **keeping the same class name and method signature**, but `value()` returns `"new"`. When the JVM allows redefinition and the new bytecode is valid, **new calls** to the method can return `"new"`. Already-created objects are not recreated, and a method that currently has an active stack frame continues running the old bytecode version until that frame finishes.

Redefinition is not a tool for arbitrarily changing any Java structure: adding fields, adding methods, changing signatures, or changing inheritance relationships are restricted by JVM TI. Therefore, distinguishing between “**the operation is supported**” and “**a specific change is valid**” is foundational to this article.

## 2. The `Can-Redefine-Classes` attribute in the agent manifest

The manifest of an agent loaded with `-javaagent` can look like this:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.ProbeAgent
Can-Redefine-Classes: true

~~~

**Meaning of each line:**

| Line | Function |
|---|---|
| `Manifest-Version: 1.0` | Declares the manifest format version |
| `Premain-Class: demo.ProbeAgent` | Class whose `premain` is invoked when using `-javaagent` |
| `Can-Redefine-Classes: true` | Requests the JVM to provide the redefinition capability if the environment supports it |

Rules according to the `java.lang.instrument` specification:

1. `Can-Redefine-Classes` is an **optional** attribute, defaulting to **`false`** if absent.
2. The value is a boolean (`true`/`false`, case-insensitive). Any value other than `true` is treated as `false`.
3. The attribute must be in the **main section** of `META-INF/MANIFEST.MF` inside the **JAR loaded by the JVM as the agent**. Placing it only in the manifest of another JAR, in an application file, or in `-D...` is not sufficient.
4. `true` **requests the capability**; it does not create the capability in a JVM that does not support it.
5. `Premain-Class` selects the **startup agent** entry point. If the agent is loaded via the attach mechanism, the JAR uses `Agent-Class` and the `agentmain` callback; the capability attribute still serves to request redefinition and does not determine the callback.
6. Changing the manifest on disk after the JVM/agent has started **does not retroactively update** the capability of the current JVM.

This attribute is typically present in an agent that wants to call `redefineClasses` on already-loaded classes. An agent that only observes classes *about to be loaded* via a transformer does not necessarily need to request redefinition.

**Two levels to distinguish:** Agent A has manifest `true`, and JVM X supports redefinition → it can be granted the capability. Agent B has a manifest missing the attribute, even though it also runs on JVM X → it is not considered to have requested the capability. Agent A moves to JVM Y which does not support it → manifest `true` does not guarantee success either.

## 3. `isRedefineClassesSupported()`: checking runtime capability

API signature:

~~~java
boolean isRedefineClassesSupported();
~~~

This method is a member of `java.lang.instrument.Instrumentation`. The JVM passes the `Instrumentation` instance to the agent via the `premain(String, Instrumentation)` or `agentmain(String, Instrumentation)` callback. This is not an object you `new` yourself to test an option.

- **`true`**: the redefinition capability **is supported in the current JVM configuration**, with the appropriate capability request from the agent. You can then proceed to check the class and bytes.
- **`false`**: redefinition is not currently available through this API; calling `redefineClasses(...)` will result in an `UnsupportedOperationException` because the capability was not granted.
- **Result is stable for the entire lifetime of a JVM**: the API specifies that multiple calls within the same JVM return the same result. There is no “wait a bit” for `false` to turn into `true` on its own.

You should not use `isRedefineClassesSupported()` to test classes like `java.lang.String`, `demo.Service`, or `int[]` because it **takes no class argument**. For a specific class, use `isModifiableClass`.

### Decision matrix

| Did the agent request the capability? | Does the JVM support/grant the capability? | Check result |
|---|---|---|
| No (`false` or missing attribute) | JVM may implement redefinition | `isRedefineClassesSupported()` is still not guaranteed to be `true`; by contract the agent must request it |
| Yes (`true`) | No | `false` |
| Yes (`true`) | Yes | `true`; **does not guarantee** the target class is modifiable |
| Yes (`true`) | Yes, but new bytes have invalid schema/format | Check may be `true`, but `redefineClasses` still **fails** |

The processing flow should be:

~~~text
Agent JAR: Can-Redefine-Classes: true?
    |
    v
Instrumentation.isRedefineClassesSupported() == true?
    |
    v
Instrumentation.isModifiableClass(Target.class) == true?
    |
    v
New bytecode has matching class, version, schema, and passes verifier?
    |
    v
Instrumentation.redefineClasses(new ClassDefinition(Target.class, bytes))
    |
    +-- success: new method calls use the new definition
    +-- exception: analyze the error, do not assume every change is valid
~~~

## 4. `isModifiableClass` asks about the target class, not the capability

~~~java
boolean isModifiableClass(Class<?> theClass);
~~~

This check returns `true` if the class is of a kind that the JVM can modify via redefinition **or** retransformation, and `false` if it cannot be modified. The specification explicitly states that the result of `isModifiableClass` is **not affected** by the value of `isRedefineClassesSupported()` or `isRetransformClassesSupported()`.

For example, on a typical JVM:

- `isModifiableClass(demo.Message.class)` may be `true`;
- `isModifiableClass(int.class)` is always `false`;
- `isModifiableClass(String[].class)` is always `false`.

Some special JVM-implemented classes may also be unmodifiable. The fact that `isModifiableClass(Message.class)` returns `true` **does not mean** the agent has been granted permission to redefine; the capability condition must be checked separately.

If you want to modify a class:

~~~java
if (inst.isRedefineClassesSupported()
        && inst.isModifiableClass(Target.class)) {
    byte[] bytes = java.nio.file.Files.readAllBytes(
            java.nio.file.Path.of("replacement/Target.class"));
    inst.redefineClasses(
            new java.lang.instrument.ClassDefinition(Target.class, bytes));
}
~~~

This is an **illustrative snippet inside a method**: it assumes `Target`, `Instrumentation inst`, and the corresponding bytes file exist. `ClassDefinition` pairs the **actual `Class<?>`** with the **entire bytes of the new class file**, not Java source code or only a partial method body.

Two classes with the same binary name belonging to two different class loaders have different identities. You must pass the exact `Class<?>` of the object the application is using.

## 5. Java 17+ hands-on: replacing bytecode of an already-loaded method

The following example can be compiled with **JDK 17+**. It creates an agent that receives `Instrumentation` via `premain`, an original version, and a replacement version of the same class `demo.Message`. The application calls `Message.value()` before and after the redefinition operation.

### 5.1. Directory tree

~~~text
redefine-lab/
├── MANIFEST.MF
├── src/
│   └── demo/
│       ├── ProbeAgent.java
│       ├── Message.java
│       └── Demo.java
├── replacement-src/
│   └── demo/
│       └── Message.java
└── out/
    ├── original/
    ├── replacement/
    └── demo.jar
~~~

The two `Message.java` files have the **same class/package name**, but are compiled into **two different directories**. The old version is packaged into the application JAR; the new version is read directly as bytes to send to the JVM. Do not mix the two versions on the same classpath.

### 5.2. `src/demo/ProbeAgent.java`

~~~java
package demo;

import java.lang.instrument.Instrumentation;

public final class ProbeAgent {
    private static volatile Instrumentation instance;

    public static void premain(String options, Instrumentation inst) {
        instance = inst;
    }

    public static Instrumentation instrumentation() {
        if (instance == null) {
            throw new IllegalStateException(
                    "Start with -javaagent:out/demo.jar");
        }
        return instance;
    }
}
~~~

`premain` is invoked by the JVM before `main` when `-javaagent` is present. In this example, the agent and the application reside in the same JAR so that the application can retrieve the stored `Instrumentation`. In an environment with multiple class loaders, you must ensure the class storing the instance and the class accessing the instance are the exact same definition.

### 5.3. `src/demo/Message.java` — original class

~~~java
package demo;

public final class Message {
    public static String value() {
        return "old";
    }
}
~~~

### 5.4. `replacement-src/demo/Message.java` — replacement class

~~~java
package demo;

public final class Message {
    public static String value() {
        return "new";
    }
}
~~~

Only change the string-returning logic: do not add fields, change signatures, or change modifiers. This is the kind of change suited for redefinition. If you want to try adding a field, see the common errors section; **do not modify the replacement version used for the successful run**.

### 5.5. `src/demo/Demo.java`

~~~java
package demo;

import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class Demo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: demo.Demo <replacement-class-file>");
        }

        System.out.println("before=" + Message.value());

        Instrumentation inst = ProbeAgent.instrumentation();
        boolean supported = inst.isRedefineClassesSupported();
        boolean modifiable = inst.isModifiableClass(Message.class);

        System.out.println("supported=" + supported);
        System.out.println("modifiable=" + modifiable);

        if (!supported || !modifiable) {
            System.out.println("skipped");
            return;
        }

        byte[] bytes = Files.readAllBytes(Path.of(args[0]));
        ClassDefinition replacement =
                new ClassDefinition(Message.class, bytes);

        inst.redefineClasses(replacement);
        System.out.println("after=" + Message.value());
    }
}
~~~

Explanation:

1. `Message.value()` is called before the operation to observe `"old"` and ensure the target class has been loaded.
2. The two queries check **JVM capability** and **target class modifiability**.
3. `Files.readAllBytes` reads the exact bytes of the new `.class` file; it does not require the new class to be loaded alongside in the JVM.
4. `ClassDefinition(Message.class, bytes)` specifies the class to replace in the JVM.
5. If `redefineClasses` succeeds, the subsequent `Message.value()` call uses the new method body.

The `main` method declares `throws Exception` to keep the example short; a production agent needs to categorize and handle errors according to its own workflow.

### 5.6. `MANIFEST.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: demo.ProbeAgent
Can-Redefine-Classes: true

~~~

Ensure the manifest file has a **trailing blank line**. In this example run with `-cp ... demo.Demo`, `Main-Class` is not needed because the application class name is specified on the command line.

### 5.7. Compile and run commands

Open a terminal in `redefine-lab`. Create the directories using Bash/Git Bash:

~~~bash
mkdir -p out/original out/replacement
~~~

Or using Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/original, out/replacement | Out-Null
~~~

Continue running the following JDK commands in that same directory:

~~~bash
javac --release 17 -d out/original src/demo/ProbeAgent.java src/demo/Message.java src/demo/Demo.java
javac --release 17 -d out/replacement replacement-src/demo/Message.java
jar --create --file out/demo.jar --manifest MANIFEST.MF -C out/original .
java -javaagent:out/demo.jar -cp out/demo.jar demo.Demo out/replacement/demo/Message.class
~~~

The `/` in the paths above is supported by Java on Windows. `--release 17` ensures the class files target Java 17. Do not add `out/replacement` to `-cp`: the original class needs to be loaded first, while the new version is passed as bytes.

On a **HotSpot JDK that supports redefinition** and has granted the capability, expected stdout is:

~~~text
before=old
supported=true
modifiable=true
after=new
~~~

Both boolean values must be observed on the **JVM you are using**; other JVM distributions/configurations may report `false`. If the conditions are not met, the demo code prints `skipped`. If the conditions are met but the new bytes are invalid, `redefineClasses` may throw an exception; `supported=true` **does not guarantee** that `after=new` will always be printed.

If `-javaagent` is omitted, the JVM does not invoke `premain`, the `instance` field remains unassigned, and the demo reports that it must be run with `-javaagent`.

## 6. Control experiment: manifest disables the redefinition capability

Create `MANIFEST-disabled.MF`:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.ProbeAgent
Can-Redefine-Classes: false

~~~

Create another JAR from the exact same compiled original classes and run it in a **new JVM**:

~~~bash
jar --create --file out/demo-disabled.jar --manifest MANIFEST-disabled.MF -C out/original .
java -javaagent:out/demo-disabled.jar -cp out/demo-disabled.jar demo.Demo out/replacement/demo/Message.class
~~~

A typical result on HotSpot:

~~~text
before=old
supported=false
modifiable=true
skipped
~~~

Important explanation: `supported=false` means the redefinition capability was not granted. `modifiable=true` **can still be true**, because whether a class can be modified is queried **independently of the capability**. The string `skipped` is printed by **Demo**'s own logic, not a default JVM message.

If some JVM returns `modifiable=false`, it does not change the principle: **both conditions** must be checked before proceeding. Changing `false` to `true` in the manifest also cannot force a JVM that does not support redefinition to support it.

## 7. Limitations of `redefineClasses` and post-redefinition behavior

In Java 21 JVMTI, redefinition can change method bodies, the constant pool, and certain allowed class-file attributes, but has many structural restrictions. Changes such as **adding/removing/renaming fields or methods; changing method signatures, modifiers, or inheritance relationships; or changing `NestHost`, `NestMembers`, `Record`, or `PermittedSubclasses`** are prohibited by the corresponding contract.

| Scenario | Result/Meaning |
|---|---|
| Only change `value()` body from returning `"old"` to `"new"` | Structurally valid; still requires valid bytes and verifier acceptance |
| Add `private int counter` to an already-loaded class | Schema change; not part of normal redefinition changes |
| Change `String value()` to `int value()` | Signature change; not allowed |
| Change superclass, add/remove methods, or change modifiers | Structural change; not allowed |
| Use a `.class` with a different name from the target `Class<?>` | Invalid; may throw `NoClassDefFoundError` |
| Use a `.class` compiled for a newer Java version than the target JVM | May throw `UnsupportedClassVersionError` |
| Bytes with malformed structure, stack map, or verification errors | May throw `ClassFormatError` or linkage/verification errors |
| Target a primitive/array class | Such classes cannot be modified |

Several **runtime consequences** cannot be ignored:

- **Existing objects remain** and keep their instance fields. Redefinition does not re-run constructors or migrate data.
- **Static initializers do not automatically re-run** and static field values are not automatically reset. Changing the source code of a static field declaration does not necessarily change the current state.
- **Currently executing stack frames continue with the old method version**; **new calls** to the method use the new version. Do not use a thread currently in the middle of a method to conclude that redefinition failed.
- **Compile-time constants may be inlined** in calling classes. Changing a `static final` constant in a redefined class does not automatically update bytes already compiled into other classes.
- **Multiple classes in a single call** can be redefined together; if the call throws an exception, the API guarantees that **none of the classes in the group are updated**.
- **A successful redefinition does not automatically revert**. To restore old logic, you must save the old bytes and actively perform the corresponding operation if the environment allows it.
- JVM TI may clear **breakpoints** on the redefined class; you need to re-sync the debugging tool if relying on them.

The JVM TI specification is the authoritative source for limitations in each JDK version. Changes specific to newer class file features may have additional constraints; do not treat a boolean check result as a guarantee that any bytecode will be accepted.

## 8. Common exceptions

Java signature:

~~~java
void redefineClasses(ClassDefinition... definitions)
        throws ClassNotFoundException, UnmodifiableClassException;
~~~

| Symptom/Error | Explanation | How to handle |
|---|---|---|
| `isRedefineClassesSupported()` is `false` | Manifest did not request it, or JVM does not support/grant the capability | Check the **manifest inside the actual agent JAR**, configuration/JVM |
| `UnsupportedOperationException` when capability is false | Redefinition is not allowed in the current configuration | Query `isRedefineClassesSupported()` first |
| `UnmodifiableClassException` | A target class cannot be modified | Use `isModifiableClass`, exclude special class types |
| `UnsupportedOperationException` even when capability is true | The new bytes require an unsupported change (e.g., schema change) | Compare field/method lists, modifiers, hierarchy, and attributes |
| `ClassFormatError`/verification error | Bytes are not a valid class file or bytecode is invalid | Use `javap -v -c`/verifier, inspect the tool generating the bytes |
| `NoClassDefFoundError` when class name differs | Bytes declare a class whose name does not match the target | Ensure matching package and binary name |
| `UnsupportedClassVersionError` | Class file version is not supported by the target JVM | Compile with a compatible `--release` |
| New logic does not appear mid-method | Old frame is still active | Verify on **new calls**, not in the middle of an existing frame |

Note that `ClassFormatError`, `UnsupportedClassVersionError`, and `LinkageError` belong to `Error`, not all are `Exception`. Therefore, `throws Exception` in the demo is to simplify the example, **not a strategy for handling all runtime errors**.

`ClassNotFoundException` remains in the declaration for API compatibility reasons; the `Instrumentation` documentation notes that this exception is not actually thrown by `redefineClasses` under the current contract. Do not infer from this checked exception declaration that the JVM will search the classpath for a new class.

## 9. Redefinition and retransformation are related but not identical

| Aspect | Redefinition | Retransformation |
|---|---|---|
| Manifest capability | `Can-Redefine-Classes` | `Can-Retransform-Classes` |
| Check method | `isRedefineClassesSupported()` | `isRetransformClassesSupported()` |
| Execution method | `redefineClasses(ClassDefinition...)` | `retransformClasses(Class<?>...)` |
| Input data | **Replacement class file bytes** passed by the agent | Process of reapplying transformers starting from the relevant **initial class file bytes** |
| Used when | Replacing a compiled class version / hot code replace | Applying or recomputing transformations on already-loaded classes |
| Per-class guard | `isModifiableClass(clazz)` | Also uses `isModifiableClass(clazz)` |

`Can-Redefine-Classes: true` **is not equivalent to** `Can-Retransform-Classes: true`. Do not call `addTransformer(transformer, true)` and assume the redefinition capability is automatically available; each mechanism has its own conditions.

When calling `redefineClasses`, registered `ClassFileTransformer`s may also participate in the byte-processing pipeline before the JVM verifies and installs the final definition. Therefore, consider interactions with other agents in the same process.

## 10. Safe and accurate usage workflow

1. **Launch the right agent JAR** via the appropriate `Premain-Class`/`Agent-Class`, and receive `Instrumentation` from the JVM.
2. **Request the right capability** with `Can-Redefine-Classes: true` in the main manifest of the agent JAR.
3. **Query the runtime** via `isRedefineClassesSupported()`. If `false`, report the environment limitation and do not call redefine.
4. **Identify the target class** using the exact `Class<?>` the application uses, including its class loader; call `isModifiableClass`.
5. **Prepare the complete new class file bytes**, keeping structure and signatures valid. Inspect the class file with `javap` or bytecode verification tools when needed.
6. **Execute `redefineClasses`**; categorize errors if any occur, and do not assume preflight booleans guarantee the operation will succeed.
7. **Verify new calls**, monitor state/breakpoints, and have a recovery plan using original bytes if needed.

## 11. Self-check

1. **The manifest has no `Can-Redefine-Classes`; the JVM technically supports redefinition. Can the agent definitely redefine?** No. The agent must request the capability, and the JVM must grant it.
2. **Does `Can-Redefine-Classes: true` force `isRedefineClassesSupported()` to return `true`?** No; it still depends on the JVM/configuration.
3. **`isModifiableClass(Message.class)` returns `true`, `isRedefineClassesSupported()` returns `false`; can `redefineClasses` be called?** No; the per-class query is independent of the capability.
4. **Can calling `isRedefineClassesSupported()` again after a few seconds change `false` to `true` in the same JVM?** No; the result is stable within a JVM session.
5. **Can `ClassDefinition(Target.class, bytes)` containing a differently named class be used to rename a class?** No; the class file must match the target.
6. **After redefinition, does the static initializer re-run?** No. Existing instances and static field state do not automatically reset.
7. **Does a currently running method immediately jump to the new bytecode mid-method?** No; the active frame continues with the old version, and new calls use the new version.
8. **Does enabling `Can-Redefine-Classes` automatically enable `Can-Retransform-Classes`?** No; they are two separate capabilities.
9. **When redefining a group of two classes at once fails, could one class have already been updated?** By API contract, no class in the group is redefined if the call throws an exception.

### Authoritative references

- [Java SE 21 — `java.lang.instrument` package specification](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): manifest capabilities and agent callbacks.
- [Java SE 21 — `Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): exact queries, operations, and exceptions.
- [Java SE 21 — `ClassDefinition`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): pairing a class and class file bytes.
- [JVM Tool Interface 21 — RedefineClasses](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html): schema restrictions, active frames, state, and error groups.
- [Java SE 21 — JAR File Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html): manifest structure.

**Key takeaway:** `Can-Redefine-Classes` is the **agent's request**; `isRedefineClassesSupported()` is the **capability granted by the JVM**; `isModifiableClass(clazz)` checks the **target class**; and `redefineClasses(...)` is what validates and installs the **replacement bytes**.