# Choosing Redefine vs. Retransform Based on Byte Source and Change Goal

## 1. The Most Important Question: Do You Have New Bytecode or Do You Want to Transform Existing Bytecode?

Both `Instrumentation.redefineClasses(...)` and `Instrumentation.retransformClasses(...)` can affect **a class already loaded by the JVM**, but they are not two equivalent ways of calling the same action. Choosing the right one starts with **the source of the classfile bytes** and **what you actually want to change**.

- **Redefinition:** you have prepared **a replacement classfile definition** for the running class — for example, a `.class` file recompiled from source after a bug fix, or new bytes from a controlled hot-patch process. You pass those full bytes via `new ClassDefinition(targetClass, replacementBytes)` to `redefineClasses(...)`.
- **Retransformation:** you have one or more `ClassFileTransformer`s and want the JVM to **re-run the transformation pipeline** on an already loaded class; the base input is supplied by the JVM from the initial definition or **the most recent redefinition**. You call `retransformClasses(targetClass)`, and retransformation-capable transformers are invoked to produce transformed bytes.

**There is no rule that “redefine is stronger than retransform”.** Each mechanism handles a different kind of data source and workflow. Both must pass through the JVM's class modification restrictions; you cannot use one API to bypass the limitations of the other.

### Four Opening Scenarios

| Scenario | Approach to Consider | Why |
|---|---|---|
| A developer just recompiled `OrderService.class` after fixing fee calculation logic and wants to replace the method body in the running JVM | **`redefineClasses`** | A complete **replacement** classfile is already available |
| A tracing agent has installed a transformer; it wants to enable/disable instrumentation by re-running transformer logic for selected classes | **`retransformClasses`** | Needs to re-run the **transformation pipeline** on base bytes |
| An agent just attached and registered a transformer; already-loaded classes have not changed yet | **`retransformClasses`** if capability is supported | `addTransformer(...)` does not automatically reprocess already-loaded classes |
| You want to add a new field or change the superclass to fix the runtime model | **Usually neither** | Schema limitations of class redefinition/retransformation; requires another design such as restart, class-loader replacement, or external data architecture |

**Lesson goal:** accurately visualize the byte source in both paths, understand the role of transformers even during redefinition, choose the right operation for real-world scenarios, handle errors, and verify behavior. The lesson includes a Java 17+ demo that builds **two definitions with the same binary name**, performs controlled retransformation and redefinition to show the difference between “original load-time bytes” and “base bytes after redefinition”.

## 2. Separating Three Commonly Confused Concepts

A running class can involve three forms of bytes:

1. **Input bytes of the initial class definition:** the bytes passed by the loader to `ClassLoader.defineClass(...)` (or the equivalent JVM path), before the transformer chain is applied.
2. **Input bytes of the most recent redefinition:** the classfile provided by the tool via `ClassDefinition.getDefinitionClassFile()`; this becomes the new base for subsequent retransformations.
3. **Effective bytes after transformation:** the result produced by the transformer chain after JVM validation; this is the definition currently used for new method invocations.

These forms may be identical or different:

~~~text
INITIAL CLASS LOAD:
loader --[initial bytes]--> transformer chain --> JVM verify --> running class
             ^
             |-- initial base source for retransform

REDEFINE:
tool --[replacement .class bytes]--> transformer chain --> JVM verify --> running class
             ^
             |-- base source for retransforms AFTER redefine

RETRANSFORM:
JVM takes base source from load / most recent redefine
    |
    +-- automatically reapplies results of non-capable transformers
    |
    +-- re-invokes canRetransform=true transformers
    |
    v
JVM verify --> running class with new result
~~~

**Note:** the base bytes during retransform are not necessarily **byte-for-byte identical** to the original bytes on disk. The `Instrumentation` documentation allows the JVM to change constant pool layout/size/order, drop some non-essential attributes, or reorder elements whose order is not significant. A proper transformer must read the current input according to the classfile format, rather than matching hashes against the original file and assuming all offsets are fixed.

## 3. Comparing the APIs by Byte Source and Behavior

| Aspect | `redefineClasses(ClassDefinition...)` | `retransformClasses(Class<?>...)` |
|---|---|---|
| Required input from caller | Pair of **`Class<?>` + `byte[]`** containing a **full replacement classfile** | **`Class<?>`** to reprocess; does not pass classfile bytes directly |
| Base byte source | `ClassDefinition.getDefinitionClassFile()` supplied by caller | Base bytes from class load or **most recent redefine** managed by JVM |
| Primary purpose | Replace class definition from new source, suited for fix-and-continue/hot patch from a prepared classfile | Ask the JVM to re-run the bytecode processing chain for a loaded class, suited for instrumentation |
| Do transformers participate? | **Yes**: the transform chain runs during redefine processing | **Selectively**: `canRetransform=true` transformers are re-invoked; results of non-capable transformers are reused |
| Specific capability | `Can-Redefine-Classes: true` + `isRedefineClassesSupported()` | `Can-Retransform-Classes: true` + `isRetransformClassesSupported()` |
| Per-class condition | `isModifiableClass(c)` | `isModifiableClass(c)` |
| Suitable for method body changes | Yes, if the new definition is valid | Yes, if the transformer returns valid bytes |
| Freely add/remove fields, methods, or change superclass or interfaces? | **Not allowed by default**; many schema changes are rejected | **Not allowed by default**; same family of JVM TI restrictions |
| Recreate instances or reset static fields? | No | No |
| Active stack frames of a modified method | Running frames may continue using the old bytecode | Same |
| Passing multiple classes in one call | `ClassDefinition...`; error → no class in the batch is redefined | `Class<?>...`; error → no class in the batch is retransformed |

One particularly common misconception: **`redefineClasses` does not “skip transformers”.** `ClassFileTransformer` is called when a class is loaded, **when a class is redefined**, and when a class is retransformed if the transformer was registered with `canRetransform=true`. Therefore, if you supply replacement bytes and another transformer automatically modifies them, the effective class may differ from the exact bytes in the source file. That is not a bug in `redefineClasses`; it is how the pipeline works.

### 3.1. Minimal Call Shapes

**Redefinition** — caller has `byte[]` of **the entire classfile**:

~~~java
Class<?> target = /* Class<?> loaded by the right loader */;
byte[] replacement = /* valid full new .class */;

instrumentation.redefineClasses(
    new ClassDefinition(target, replacement)
);
~~~

**Retransformation** — caller asks the JVM to re-run transformers:

~~~java
Class<?> target = /* Class<?> loaded by the right loader */;
instrumentation.retransformClasses(target);
~~~

These are **API illustration snippets**, not two standalone programs: the variables `instrumentation`, `target`, and `replacement` must be obtained inside a real agent. The complete example below implements all classes, paths, and build commands.

## 4. Byte Source in `retransformClasses`: Load History vs. Redefine History

You need to understand the exact meaning of “initial class file bytes” in the Javadoc. It does not mean “always the first JAR file the application ever read”. After a redefinition, **the base source for subsequent retransformations is established from the new definition**.

Visualize the sequence with a `Message.text()` method:

~~~text
A. JVM loads Message.class initially:
   base bytes contain "BASE"
   -> (no transformer modifies it) -> text() returns "BASE"

B. Capable transformer is enabled; call retransformClasses(Message.class):
   JVM starts from base bytes "BASE"
   -> transformer changes "BASE" to "LIVE"
   -> text() returns "LIVE"

C. Disable transformation and call retransformClasses(Message.class) again:
   JVM still starts from base bytes "BASE"
   -> transformer returns null
   -> text() returns to "BASE" (in an example with only 1 capable transformer)

D. Caller has recompiled classfile containing "EDIT"; call redefineClasses:
   bytes "EDIT" -> transformer does not modify this time -> text() returns "EDIT"
   THIS REDEFINE creates a new base source

E. Enable transformer and call retransformClasses:
   JVM starts from base source "EDIT" of the most recent redefine
   -> transformer changes "EDIT" to "PIPE"
   -> text() returns "PIPE"

F. Disable transformer and call retransformClasses again:
   JVM starts from base source "EDIT"
   -> transformer returns null
   -> text() returns to "EDIT", not "BASE"
~~~

For this reason, **retransform is not a “restore to the JAR version at JVM startup” button**. It re-runs the pipeline on **the current base held by the JVM**. If you want to revert to `"BASE"` after redefining to `"EDIT"`, you generally need to supply the **BASE classfile bytes** again via a new `redefineClasses` call (when constraints allow), or design a transformer that produces the corresponding bytes. Do not infer a rollback mechanism solely from toggling a flag.

### 4.1. Do Non-Retransform-Capable Transformers Disappear?

**No.** According to the Javadoc, during a `retransformClasses` pass:

- For each transformer registered with `canRetransform=false`, the JVM **does not re-invoke its callback**, but **reapplies the transform result from the most recent class load or redefine**.
- For a `canRetransform=true` transformer, the JVM **re-invokes `transform(...)`** to produce the current output.
- The ordering of transform groups is preserved per the contract, including Java/native capable and incapable groups.

Therefore, “disabling a capable transformer and retransforming returns the base bytes” only holds when no other transformations remain in effect. If other agents have instrumented the class or a non-capable transformer previously generated code, the result after disabling one transformer may still contain another agent's instrumentation.

### 4.2. Bytes from `redefineClasses` Still Go Through the Pipeline

The base source of a redefine is `ClassDefinition.getDefinitionClassFile()`; before installing it, the JVM may apply registered transformers. This has two consequences:

1. The `.class` file you supply must have the right class, version, and schema even before transformation. If a transformer modifies it, the **final output** must also be valid.
2. If a tool extracts the current **already-transformed** bytes and feeds them back as replacement bytes, a transformer may apply itself again and cause **double instrumentation**. Do not treat “bytes observed after instrumentation” as a clean classfile source unless the pipeline design handles repeatability.

When multiple agents intervene, you should clearly model the **owner** of the source-of-truth bytes, transformer ordering, idempotency markers, and behavior when a transformer is removed.

## 5. Four Prerequisites Before Modifying a Loaded Class

### 5.1. Capabilities Are Optional, and the Two Flags Are Independent

For a startup agent that needs both features, the manifest main section:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.SwitchAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true

~~~

For an agent loaded dynamically via the Attach API, use `Agent-Class`/`agentmain` and declare the corresponding `Can-*` attributes. An agent may request only `Can-Redefine-Classes` or only `Can-Retransform-Classes` when it does not need the other feature.

Then you **must check at runtime**:

~~~java
boolean canRedefine = instrumentation.isRedefineClassesSupported();
boolean canRetransform = instrumentation.isRetransformClassesSupported();
~~~

These two results do not substitute for each other. Requesting `true` in the manifest is only a **necessary condition**; the current JVM or configuration may still not provide the capability. Do not assume from “JDK 17” or from a developer machine's vendor that every production JVM returns the same values.

### 5.2. Modifiability Is a Per-Class Condition

~~~java
if (!instrumentation.isModifiableClass(targetClass)) {
    throw new IllegalArgumentException("Class is not modifiable");
}
~~~

Even when both JVM-wide capabilities are `true`, a specific `Class<?>` may be unmodifiable. Primitive and array classes cannot be modified; other kinds of classes may also be rejected by the JVM. The result of `isModifiableClass` is **independent** of the two capability flags and does not guarantee that every modification to the class is valid.

### 5.3. Class Identity Includes the Defining Loader

In a plugin architecture:

~~~text
pluginLoaderA -> com.shop.Cart  // class A
pluginLoaderB -> com.shop.Cart  // class B
~~~

Same name, but two **different** `Class<?>` objects. `redefineClasses` requires the exact class object and full bytes with a **matching binary name**. `retransformClasses` also takes the exact class object; you cannot just pass the string `"com.shop.Cart"`.

If using `getAllLoadedClasses()` to locate a class:

~~~java
for (Class<?> c : instrumentation.getAllLoadedClasses()) {
    if ("com.shop.Cart".equals(c.getName())
            && c.getClassLoader() == expectedLoader) {
        // c is a candidate; still need to check modifiability.
    }
}
~~~

This snippet is illustrative only; `expectedLoader` must be determined according to your real architecture. Do not casually call `Class.forName(...)` to “find” an already-loaded class, because doing so can trigger a new definition in a different loader.

### 5.4. Valid Classfile Within JVM TI Limits

Neither mechanism is class schema migration. Under the restrictions of many JVMs, the following changes are rejected:

- Adding, removing, or renaming fields/methods.
- Changing inheritance/interfaces.
- Modifying method/class attributes that JVM TI does not support changing.
- Providing a classfile version not accepted by the runtime.
- Providing bytes whose binary name does not match `targetClass`.
- Producing invalid `StackMapTable`, constant pool, bytecode, verifier state, or helper visibility.

Changing **method bodies** is the best case to start with. For specialized VMs/JDKs that support extensions, you must verify against the specific implementation; **do not assume** either API is an arbitrary class replacement mechanism.

## 6. Practical Decision Workflow

Use the decision tree before writing code:

~~~text
Do you want to modify an already-loaded class?
|
+-- No, the class is not loaded yet
|     -> Register a ClassFileTransformer to handle initial class definition.
|
+-- Yes
      |
      +-- Do you have trusted, pre-built full replacement .class bytes?
      |      |
      |      +-- Yes: is the goal hot-fix / replacing method body from a new build?
      |              -> Prefer considering redefineClasses(...)
      |                 check Can-Redefine-Classes + isRedefineClassesSupported
      |
      +-- Do you want to re-run existing bytecode transformation logic?
      |      |
      |      +-- Yes: enable/disable/update instrumentation policy
      |              -> Prefer considering retransformClasses(...)
      |                 check Can-Retransform-Classes + isRetransformClassesSupported
      |
      +-- Do you want to change the schema: add fields, change superclass, etc.?
             -> Choose an alternative design; do not pick either API hoping to bypass limits.

After choosing:
   right Class<?>/loader?
   class modifiable?
   current source bytes valid?
   could transformer pipeline affect it?
   new bytecode valid?
   active frames/static state impacted?
   test + rollback plan?
~~~

### Concrete Examples

**A. Hotfix fee calculation logic from a new build.** CI produces a signed/verified `BillingService.class` containing a bug-fix method body, with the same class name and schema as the running class. If the goal is to **make that build the new base definition**, `redefineClasses` expresses the intent better. Even so, you must check state compatibility, constant pool, classfile version, and transformers that may run on those bytes.

**B. Tracing agent already attached, wants to instrument already-loaded classes.** No replacement `.class` is available; the agent has a transformer that inserts timing hooks at method entry/exit. Register `addTransformer(transformer, true)` and call `retransformClasses(selectedClasses)` after checking prerequisites. This is the natural use case for retransform.

**C. Changing an agent's filter or sampling configuration.** If the transformer reads a new immutable configuration or can be safely toggled and you want to update running classes, call `retransformClasses` with the selected class set. If the tool has already computed full replacement bytes outside the pipeline, redefinition can be considered, but keep in mind that transformers are still invoked.

**D. Debugger fix-and-continue.** The IDE has a newly compiled classfile for a method and wants to replace the runtime definition. `redefineClasses` is the exact case explicitly suggested by the `Instrumentation` Javadoc. Updating source outside the JVM does **not** automatically update already-loaded classes; an explicit operation is required.

**E. Reverting to before instrumentation.** If only your capable transformer modified the bytes and the base source did not change, disabling the transformer and retransforming can return to the base. If you have redefined to different bytes, retransform will be based on the new definition; reverting to the old version requires managing real **byte snapshots/versions** and applying a proper rollback procedure.

**F. Creating a class with a new field.** If business logic requires changing object structure, neither mechanism is a general migration tool. An application may need a restart, versioned classes/loaders, migrating state across schemas, or storing supplemental data in an external map with proper cleanup.

## 7. Java 17+ Demo: Observing the Two Byte Sources Change Over Time

The lab below uses a **startup agent** to simplify keeping the same `Instrumentation` and transformer in a single JVM. The same principles apply to `agentmain` with Attach, though Attach adds permission/process requirements and dynamic agent loading policies.

The demo includes:

- An initial `demo.Message` compiled by `javac` with `text() -> "BASE"`.
- A replacement `demo.Message` from another source, with the same binary name, signature, and class schema, but `text() -> "EDIT"`.
- `SwitchAgent` registering **one** capable `ClassFileTransformer`. When enabled, the transformer changes the exact 4-byte ASCII constant-pool UTF8 `"BASE"` to `"LIVE"` or `"EDIT"` to `"PIPE"`. Both are **4 bytes** long, so the demo does not alter classfile layout.
- `App` calling both `retransformClasses` and `redefineClasses`, printing the result after each step.

**Important warning:** hand-writing a constant pool parser and swapping literals is a **minimal illustrative trick**, not a production instrumentation solution. It only works on these two demo classes containing four-byte ASCII literals, does not generate/insert instructions, and does not support arbitrary classfiles. When you need structured method body changes, use libraries like ASM/Byte Buddy on JDK 17, or the standard Class-File API from JDK 24 if targeting a suitable version.

### 7.1. Project Directory

~~~text
redefine-vs-retransform/
├── AGENT.MF
├── src/
│   ├── base/demo/Message.java
│   ├── edited/demo/Message.java
│   ├── agent/demo/agent/SwitchAgent.java
│   └── app/demo/App.java
└── out/                         # Created during build step
    ├── base/demo/Message.class
    ├── edited/demo/Message.class
    ├── agent/
    ├── app/
    └── switch-agent.jar
~~~

The two files `src/base/demo/Message.java` and `src/edited/demo/Message.java` have **the same package, class name, and file name** but are compiled into **two different output directories**. Never add **both directories** to the runtime classpath when running the demo; runtime uses `out/base`, while `out/edited` only supplies classfile bytes for `redefineClasses`.

### 7.2. File `src/base/demo/Message.java`

~~~java
package demo;

public final class Message {
    private Message() {}

    public static String text() {
        return "BASE";
    }
}
~~~

### 7.3. File `src/edited/demo/Message.java`

~~~java
package demo;

public final class Message {
    private Message() {}

    public static String text() {
        return "EDIT";
    }
}
~~~

Both have the same `demo.Message`, the same method `text()Ljava/lang/String;`, the same modifiers, and the same class hierarchy. Only the returned literal in the method body changes. On a typical JVM that supports redefinition, this is an appropriate change to test.

### 7.4. File `src/agent/demo/agent/SwitchAgent.java`

~~~java
package demo.agent;

import java.lang.instrument.ClassDefinition;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.ProtectionDomain;

public final class SwitchAgent {
    private static volatile Instrumentation instrumentation;
    private static volatile boolean patchEnabled;

    private SwitchAgent() {}

    public static void premain(String arguments, Instrumentation inst) {
        instrumentation = inst;

        boolean canRetransform = inst.isRetransformClassesSupported();
        boolean canRedefine = inst.isRedefineClassesSupported();

        System.out.println("[agent] capabilities retransform="
                + canRetransform + " redefine=" + canRedefine);

        if (!canRetransform || !canRedefine) {
            throw new IllegalStateException(
                    "Both capabilities required for this demo");
        }

        // Transformer is registered at startup, but does not patch initially.
        inst.addTransformer(new LiteralPatchTransformer(), true);
    }

    public static void retransform(Class<?> target, boolean enablePatch)
            throws UnmodifiableClassException {

        Instrumentation inst = requireInstrumentation();
        if (!inst.isRetransformClassesSupported()
                || !inst.isModifiableClass(target)) {
            throw new IllegalStateException(
                    "Retransformation unavailable for target");
        }

        patchEnabled = enablePatch;
        inst.retransformClasses(target);
    }

    public static void redefine(Class<?> target, Path replacementFile)
            throws Exception {

        Instrumentation inst = requireInstrumentation();
        if (!inst.isRedefineClassesSupported()
                || !inst.isModifiableClass(target)) {
            throw new IllegalStateException(
                    "Redefinition unavailable for target");
        }

        // Disable patching so the EDIT bytes supplied by the caller are used.
        patchEnabled = false;

        byte[] newClassFile = Files.readAllBytes(replacementFile);
        inst.redefineClasses(new ClassDefinition(target, newClassFile));
    }

    private static Instrumentation requireInstrumentation() {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException(
                    "Run this app with -javaagent");
        }
        return inst;
    }

    private static final class LiteralPatchTransformer
            implements ClassFileTransformer {

        @Override
        public byte[] transform(
                Module module,
                ClassLoader loader,
                String className,
                Class<?> classBeingRedefined,
                ProtectionDomain domain,
                byte[] bytes) {

            if (!patchEnabled
                    || !"demo/Message".equals(className)
                    || loader != ClassLoader.getSystemClassLoader()) {
                return null;
            }

            byte[] changed = replaceSingleLiteral(bytes);
            if (changed != null) {
                System.out.println(
                        "[agent] transformer patched demo.Message");
            }
            return changed;
        }

        // MINIMAL constant pool parser for illustration only.
        // Do not use for arbitrary classfiles from untrusted sources.
        private static byte[] replaceSingleLiteral(byte[] original) {
            if (original.length < 10
                    || (original[0] & 255) != 0xCA
                    || (original[1] & 255) != 0xFE
                    || (original[2] & 255) != 0xBA
                    || (original[3] & 255) != 0xBE) {
                return null;
            }

            byte[] copy = original.clone();
            int cpCount = u2(original, 8);
            int offset = 10;
            int replacements = 0;

            for (int index = 1; index < cpCount; index++) {
                if (offset >= original.length) {
                    return null;
                }

                int tag = original[offset++] & 255;
                switch (tag) {
                    case 1: { // CONSTANT_Utf8
                        if (offset + 2 > original.length) {
                            return null;
                        }
                        int length = u2(original, offset);
                        offset += 2;
                        if (offset + length > original.length) {
                            return null;
                        }

                        if (length == 4) {
                            if (isAscii(original, offset, "BASE")) {
                                putAscii(copy, offset, "LIVE");
                                replacements++;
                            } else if (isAscii(original, offset, "EDIT")) {
                                putAscii(copy, offset, "PIPE");
                                replacements++;
                            }
                        }
                        offset += length;
                        break;
                    }
                    case 3: case 4:
                    case 9: case 10: case 11: case 12:
                    case 17: case 18:
                        offset += 4;
                        break;
                    case 5: case 6:
                        offset += 8;
                        index++; // long/double use two CP slots.
                        break;
                    case 7: case 8: case 16:
                    case 19: case 20:
                        offset += 2;
                        break;
                    case 15:
                        offset += 3;
                        break;
                    default:
                        return null;
                }

                if (offset > original.length) {
                    return null;
                }
            }
            return replacements == 1 ? copy : null;
        }

        private static int u2(byte[] bytes, int offset) {
            return ((bytes[offset] & 255) << 8)
                    | (bytes[offset + 1] & 255);
        }

        private static boolean isAscii(
                byte[] bytes, int offset, String literal) {
            for (int i = 0; i < literal.length(); i++) {
                if ((bytes[offset + i] & 255) != literal.charAt(i)) {
                    return false;
                }
            }
            return true;
        }

        private static void putAscii(
                byte[] bytes, int offset, String literal) {
            for (int i = 0; i < literal.length(); i++) {
                bytes[offset + i] = (byte) literal.charAt(i);
            }
        }
    }
}
~~~

**Important explanation about the transformer:**

- `patchEnabled` starts as `false`, so the initial JVM definition of `demo.Message` is not altered.
- When `retransform(..., true)` is called, the JVM re-invokes `transform` because it was registered with `canRetransform=true`. The transformer does not mutate the input byte array in-place; it calls `clone()` and returns new bytes.
- `replaceSingleLiteral` only replaces one 4-byte `CONSTANT_Utf8` with value `BASE` or `EDIT`. It does not parse/modify method structure; the string literal in `Message.text()` is referenced via `CONSTANT_String` pointing to UTF8. This modification works for the two classes provided by the example and does not prove that arbitrary constant pool modifications are safe.
- When `patchEnabled=false`, the transformer returns `null`. In a demo with only one capable transformer, retransforming again uses the base bytes unpatched by that transformer, letting you observe the difference between **BASE before redefine** and **EDIT after redefine**.
- `redefine(...)` builds a `ClassDefinition` from the **replacement** file's bytes and temporarily disables patching. In principle, however, the pipeline is still invoked on redefine; the lack of modification is because the demo's own transformer returns `null`.
- If the classfile does not contain exactly one target literal, the parser returns `null` (skips) rather than attempting a blind transformation. This is only a lab exercise; production needs a real classfile parser, safe logging, and concurrency management.

**Why is `volatile` needed?** A real Java agent may receive callbacks from different class-loading threads. `volatile` ensures basic visibility for the flag value. The demo invokes operations sequentially; if production supports concurrent requests, a single global flag is still **not enough** to guarantee each operation uses the right configuration, and an appropriate synchronization or immutable-config design is needed.

### 7.5. File `src/app/demo/App.java`

~~~java
package demo;

import demo.agent.SwitchAgent;
import java.nio.file.Path;

public final class App {
    private App() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: demo.App <replacement-class-file>");
        }

        // Start with bytes from out/base/demo/Message.class.
        System.out.println("initial=" + Message.text());

        // retransform takes base bytes BASE; transformer changes it to LIVE.
        SwitchAgent.retransform(Message.class, true);
        System.out.println("after retransform=" + Message.text());

        // Disable transformer; retransform runs again from BASE.
        SwitchAgent.retransform(Message.class, false);
        System.out.println("after retransform off=" + Message.text());

        // Replace base with full replacement .class containing EDIT.
        SwitchAgent.redefine(Message.class, Path.of(args[0]));
        System.out.println("after redefine=" + Message.text());

        // Now retransform starts from EDIT, not from BASE.
        SwitchAgent.retransform(Message.class, true);
        System.out.println(
                "after retransform since redefine=" + Message.text());

        // Disable patch; the new base source remains EDIT.
        SwitchAgent.retransform(Message.class, false);
        System.out.println(
                "after retransform off since redefine=" + Message.text());
    }
}
~~~

Note that `App` calls `Message.text()` for the first time **before** requesting retransform or redefine, so the class is already loaded. There is no need to use the Attach API for this demo: the startup agent provides `Instrumentation` ready to use, and the program explicitly controls the timing of each operation.

### 7.6. File `AGENT.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.SwitchAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true

~~~

Both flags are required because the demo uses **both** APIs. For an agent that only needs redefinition, you should not mechanically request retransform. The manifest file must have a trailing newline; `jar cfm` will place it into `META-INF/MANIFEST.MF`.

### 7.7. Compiling and Packaging with JDK 17+

Create the output directories from the `redefine-vs-retransform` root.

**On Bash:**

~~~bash
mkdir -p out/base out/edited out/agent out/app
~~~

**On PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force out/base, out/edited, out/agent, out/app | Out-Null
~~~

Compile the two same-named classes into **two separate directories**; compile the agent; create the agent JAR:

~~~bash
javac --release 17 -d out/base src/base/demo/Message.java

javac --release 17 -d out/edited src/edited/demo/Message.java

javac --release 17 -d out/agent src/agent/demo/agent/SwitchAgent.java

jar cfm out/switch-agent.jar AGENT.MF -C out/agent .
~~~

To compile `App`, the classpath must include **the BASE build** and the agent JAR because `App`'s source directly calls `SwitchAgent`.

**Bash/Linux/macOS:**

~~~bash
javac --release 17 -cp "out/base:out/switch-agent.jar" -d out/app src/app/demo/App.java
~~~

**Windows PowerShell or CMD:**

~~~powershell
javac --release 17 -cp "out/base;out/switch-agent.jar" -d out/app src/app/demo/App.java
~~~

When running, do **not** put `out/edited` on the classpath. The EDIT file is passed via **the path to the `.class` file**, not loaded initially by the class loader.

### 7.8. Running and Expected Stdout

**Bash/Linux/macOS:**

~~~bash
java -javaagent:out/switch-agent.jar -cp "out/app:out/base:out/switch-agent.jar" demo.App out/edited/demo/Message.class
~~~

**Windows:**

~~~powershell
java -javaagent:out/switch-agent.jar -cp "out/app;out/base;out/switch-agent.jar" demo.App out/edited/demo/Message.class
~~~

On a **typical HotSpot JDK 17+ supporting both capabilities** and running the exact demo source code, expected stdout:

~~~text
[agent] capabilities retransform=true redefine=true
initial=BASE
[agent] transformer patched demo.Message
after retransform=LIVE
after retransform off=BASE
after redefine=EDIT
[agent] transformer patched demo.Message
after retransform since redefine=PIPE
after retransform off since redefine=EDIT
~~~

Any runtime that does not support both capabilities will **not** produce the stdout above: `premain` intentionally fails fast because the demo needs both. That does not prove the JDK lacks the Instrumentation API; it only proves the current runtime does not provide all features required by the demo.

**Analysis of each state transition:**

| Step | Operation | Byte Source | Transformer Active? | Method Result |
|---|---|---|---|---|
| 1 | Initial class load | BASE from `out/base` | No | `BASE` |
| 2 | `retransformClasses` | BASE from JVM | Yes; `BASE → LIVE` | `LIVE` |
| 3 | `retransformClasses` | Still BASE from JVM | No | `BASE` |
| 4 | `redefineClasses(ClassDefinition(EDIT bytes))` | **EDIT bytes from new file** | No | `EDIT` |
| 5 | `retransformClasses` | **EDIT from most recent redefine** | Yes; `EDIT → PIPE` | `PIPE` |
| 6 | `retransformClasses` | Still EDIT from redefine | No | `EDIT` |

The most important row is step 6: after redefining, disabling the transformer and retransforming **does not revert to `BASE`**, but returns to `EDIT`, because the redefinition changed the base source. This is the exact meaning of “choosing by byte source”.

To verify the effect of preparing the right replacement bytes, ensure both `out/base/demo/Message.class` and `out/edited/demo/Message.class` exist, while only `out/base` is on the runtime classpath. When calling `redefineClasses`, the caller loads **the bytes of the EDIT file**, without asking a class loader to define a second copy of the class.

### 7.9. What the Demo Does Not Prove

- Replacing UTF8 literals in the constant pool is a safe trick **only for this specific demo data**; do not use this parser to edit arbitrary or production classfiles.
- It does not add new fields/methods and does not bypass schema limits.
- It does not demonstrate active frame behavior. The `text()` method finishes very quickly; calls after changing the definition use the new definition.
- The demo has only **one capable Java transformer**; multiple agents/native transformers and incapable groups can produce different outputs.
- The demo intentionally uses a startup agent and does not test dynamic Attach policies; moving to Attach requires `Agent-Class`/`agentmain`, attach permissions, a way to find the right loaded `Class<?>`, and appropriate JVM configuration.

## 8. Distinguishing “Byte Source” from “Change Goal”

Many mistakes occur because tools only ask “do we want to change behavior?” without asking **who owns the source of truth**.

### 8.1. When You Have a Recompiled Classfile

`redefineClasses` fits better if you want to **make an external classfile version the new base**. It is convenient for IDE hot-swap, live patching, and debugging with signed build artifacts.

However, you must clarify:

- The bytes come from the **right build**, right class name, right target Java version, and schema.
- Which loader/module the running class belongs to; you must not accidentally target a class from another plugin.
- Other registered transformers may automatically apply themselves to these bytes during redefinition.
- Does the new bytecode read old state under new assumptions? There is no automatic migration of static fields or object instances.
- Is there a verified snapshot of the old classfile to roll back via another redefine?

When a hotfix is a class version with a fixed method body, verify whether the patch depends on adding a new field or changing a constructor/superclass. Those changes may not be supported even if compiling the new source succeeds cleanly.

### 8.2. When You Have a Transform Algorithm, Without a Replacement File

`retransformClasses` fits if your logic is “for the existing class definition, reapply the agent's bytecode insertion rules”. Typical cases:

- Adding/removing tracing hooks for methods with a specific annotation.
- Changing coverage or security monitoring policies in already-loaded classes.
- Re-enabling a transformer after late attach.
- Updating instrumentation rules when a feature is toggled on/off.

Crucially, the transformer must be **idempotent** with respect to the input source and transformer chain, not duplicating instrumentation across repeated retransformations. If multiple transformers are used, account for how the JVM reapplies results of `canRetransform=false` transformers.

### 8.3. When a Transform Algorithm Uses External Bytes

A `ClassFileTransformer` can technically **return entirely new classfile bytes** read from elsewhere. Thus, “retransform means never using external bytes” is an overly absolute interpretation.

More accurately:

- **The retransform API does not accept full classfile bytes from the caller**; the JVM chooses the input source and invokes the pipeline.
- **A transformer** may decide to use another data source to produce its output, as long as the classfile is valid and meets constraints.
- If the primary data source is a **pre-built replacement `.class`**, `redefineClasses` usually expresses the intent more clearly and avoids unnecessary coupling to transformer callbacks.
- In both cases, responsibility for versioning, integrity, and compatibility must be clearly defined.

### 8.4. When You Only Want New Classes Instrumented

If the class is **not loaded yet**, there is no `Class<?>` on which to call `retransformClasses`/`redefineClasses` in the sense of replacing an existing class. Registering a `ClassFileTransformer` before the initial class definition and transforming at load-time is the right workflow.

Do not call `Class.forName` just to obtain a class object and then “retransform” if the goal is to intercept **the first load**: looking up the class can trigger loading too early, missing the easiest instrumentation point.

## 9. Shared Runtime Limits: Not a Restart or Schema Migration

### 9.1. Active Stack Frames

Per the Javadoc of both APIs, if a method has **active frames** when the class is replaced:

- Existing frames may continue executing **the bytecode of the old version**.
- New invocations after the replacement succeeds will use the new definition.

Design tests with a long-running method synchronized before the swap and verify both groups of calls. Do not treat a stack frame still printing the old value as proof that redefine/retransform failed.

### 9.2. Static State and Instances

Neither API automatically re-runs `<clinit>` or resets existing static fields. Existing objects are not reconstructed either. Practical consequences:

- The new method body uses current static values, not the static initializer from the newly compiled source.
- If the new source “expects” an additional field, the class schema may be rejected, or the design needs external state.
- If the new logic assumes a different invariant for old instances, you must have a state compatibility plan; the API will not fix that invariant automatically.

### 9.3. Retransform/Redefine Commands on a Group of Classes

Both APIs accept **multiple classes** in a single call; the JVM validates and installs them as a group operation per the contract: if an error occurs, **no class in that batch is replaced**. That does not mean multiple separate calls form a transaction: if you run 3 independent calls and the 3rd fails, the earlier completed calls are not automatically rolled back.

Therefore, for changes spanning multiple classes, consider a single call over an appropriate group of classes. However, larger batches increase cost and the risk of hitting an unmodifiable target. Group selection must be based on real dependencies.

### 9.4. Permissions, Modules, and Helper Visibility

A transformer generating bytes that call agent helpers needs to check:

- Can the target's defining loader see the helper?
- Does the target module have the necessary readability/exports/opens?
- Was the helper added to the bootstrap or system search path at the right time?
- Are method signatures and class versions compatible with the runtime?

`Instrumentation.redefineModule(...)` can expand certain module relationships when needed and permitted; that is a **different problem** from choosing redefine vs. retransform. Do not “open all packages” to fix every linking error.

## 10. Exceptions and Failure Modes

Operations can throw different errors, such as:

| Problem Category | Example | Appropriate Response |
|---|---|---|
| JVM does not grant capability | `UnsupportedOperationException` when requesting an unsupported feature | Check `is...Supported()`, choose fallback or fail-fast clearly |
| Target is not modifiable | `UnmodifiableClassException` | Skip target and report reason; do not retry infinitely |
| Redefine bytes have wrong name | `NoClassDefFoundError` | Match classfile name with `targetClass` and the right loader |
| Malformed classfile | `ClassFormatError` | Check parser/writer, verifier, and byte source |
| Incompatible classfile version | `UnsupportedClassVersionError` | Compile for the right target Java version |
| Unsupported schema change | `UnsupportedOperationException` | Design patch to modify method bodies only, or use another architecture |
| Linking/verifier failure | `LinkageError`, `VerifyError`, and related errors | Check stack map, constant pool, hierarchy, and helper visibility |
| Reading replacement file fails | `IOException` on the tool side | Do not call redefine with empty/incomplete data |
| Risk from agent interference | No crash, but wrong behavior | Runtime tests, metrics, rollback based on saved source bytes |

**An exception from `retransformClasses`/`redefineClasses` means that request failed**; do not assume the target class was partially modified. However, if external preparation steps (writing files, loading another agent, changing config) already happened, the API does not automatically roll back those external side effects.

For transformers, a callback throwing an exception may be handled by the JVM under the contract allowing the pipeline to continue; **do not abuse exceptions as a tool to block every class definition**. The tool should check results and log the right error class.

### 10.1. Fail-Fast or Degrade?

- If the tool only collects metrics and can afford to miss some targets, missing a capability can degrade to load-time-only or skip targets with a notice.
- If a patch to fix a business bug **must** be installed, a missing capability or unmodifiable class should be a deployment-blocking error, never printing “Patch applied”.
- If a patch needs consistency across multiple classes, a batch request and dependency testing are better than uncontrolled sequential patching.

Do not print `"class changed"` as soon as `addTransformer` returns; that method only registers a callback. Only after the operation succeeds and **behavior has been verified** should the fix be considered complete.

## 11. Common Design Mistakes

### Mistake 1 — “Redefine is just retransform with new bytes”

Inaccurate. `redefineClasses` takes **full bytes from the caller**, while `retransformClasses` takes **class objects** and runs the pipeline with base bytes managed by the JVM. After a redefine, the base for subsequent retransformations can change.

### Mistake 2 — “Redefine skips all transformers”

False. Transformers are invoked on **class redefinition** passes per the contract. Another agent can still modify the bytes you just supplied. You must inspect the entire pipeline when diagnosing output that does not match the replacement file.

### Mistake 3 — “Retransform after redefine reverts to the original JAR”

False. The base definition for subsequent retransforms comes from **the most recent redefine** (in the demo, EDIT). If you need to return to BASE, you must restore the appropriate source bytes, not just disable the transformer.

### Mistake 4 — “`canRetransform=false` will be called again on retransform”

False. The JVM reuses the previous effect of `canRetransform=false` transformers; only the capable group is called back again. A callback not being re-invoked does not mean its previous effect has disappeared.

### Mistake 5 — “Any schema change will work with either API”

False. Changes like adding/removing fields, changing method signatures, or altering inheritance are restricted; many JVMs reject them. Migrating state or object layout usually requires a different architectural approach.

### Mistake 6 — “Retransform capability implies redefine capability”

False. `Can-Retransform-Classes` and `Can-Redefine-Classes` are two distinct optional attributes; you must check the corresponding query before calling each API.

### Mistake 7 — “You can redefine a class by string name”

False. Both APIs require **`Class<?>` of the exact JVM runtime type**. Two different loaders can define the same binary name, yet those are two classes with different identities.

### Mistake 8 — “If a class has modifiable=true, the new bytes are always valid”

False. `isModifiableClass` does not evaluate the output classfile. Verifier errors, method signatures, class versions, superclasses, and stack frames can still cause the operation to fail.

### Mistake 9 — “Rolling back by flipping a boolean off is enough”

False when multiple transformers are involved or after a redefine. Reliable rollback requires storing **a baseline/snapshot with provenance**, knowing which transformers it has passed through, and checking runtime conditions before reapplying old bytes.

### Mistake 10 — “Updating the code is enough; no need to test against old state”

False. Redefinition/retransformation does not reset static fields or recreate instances. The new method body runs on existing state; logical compatibility must be tested.

### Mistake 11 — “Once a method is replaced, active frames switch immediately”

No. Currently running frames may still use the old bytecode; new calls use the new definition. You must distinguish the behavior of old frames from new invocations.

### Mistake 12 — “Finding classfile bytes in a resource means you have the right replacement”

No. A resource with the same name may belong to a different version, a different class loader, a shaded/nested JAR, or a different build. Check provenance, binary name, schema, verifier, and target compatibility.

## 12. Operational and Testing Checklist

### Before Choosing the API

- [ ] Is the target class **already loaded** or not? If not, consider transforming at initial load.
- [ ] Is the primary byte source a **fully built** new `.class` file, or a transformer algorithm operating on JVM-supplied input?
- [ ] If full replacement bytes are available, are they from the right build, with integrity and class schema verified?
- [ ] If using a transformer, is the code idempotent and able to handle bytes after a redefine?
- [ ] Have you identified the exact `Class<?>` by binary name + defining loader/module?
- [ ] Does the JVM have the required capability, and is the target modifiable?
- [ ] Do you plan to change fields/methods/inheritance beyond limits, or only method bodies?
- [ ] If rollback is needed, which source bytes are saved: initial BASE or the EDIT from redefine?

### During Execution

- [ ] If redefining: read complete classfile bytes, verify source, create `ClassDefinition(target, bytes)`, request a compatible batch.
- [ ] If retransforming: register an appropriate `ClassFileTransformer` with `canRetransform=true`, select the target class set, then explicitly call `retransformClasses`.
- [ ] Log distinctly: `registered`, `redefine requested`, `retransform requested`, `transform invoked`, and `verified`.
- [ ] Have clear exception handling and a fail-fast/degrade policy; do not swallow errors and report success.
- [ ] Do not mutate `classfileBuffer` in-place; if the transformer produces bytes, return a valid new array.
- [ ] Check the impact of other transformers in the pipeline.

### After Execution

- [ ] Test new invocations and the case where the method is running in an active frame.
- [ ] Test against pre-existing static state and instances.
- [ ] Compare class behavior against the goal, rather than relying only on the API not throwing an exception.
- [ ] Test across multiple class loaders, module boundaries, and target Java runtime versions.
- [ ] Confirm the rollback plan uses the right source-of-truth version and does not touch out-of-scope classes.
- [ ] If multiple dependent classes exist, verify consistency when replacing them in the same batch.

### Suggested Test Matrix

| Case | Condition | Expected Result |
|---|---|---|
| 1 | BASE, patch on, retransform | LIVE |
| 2 | BASE, patch off, retransform | BASE |
| 3 | Redefine to EDIT file, patch off | EDIT |
| 4 | After redefine, patch on, retransform | PIPE |
| 5 | After redefine, patch off, retransform | EDIT, **not BASE** |
| 6 | JVM lacks `Can-Redefine-Classes`/capability | Do not call redefine; report error clearly |
| 7 | JVM lacks `Can-Retransform-Classes`/capability | Do not call retransform; report error clearly |
| 8 | Target `isModifiableClass==false` | Intentionally skip/fail |
| 9 | Replacement classfile has wrong binary name | Redefine batch fails |
| 10 | Replacement makes forbidden field schema change | JVM rejects per limits |
| 11 | Multiple transformers, including `canRetransform=false` | On retransform, prior result of incapable transformer is still reapplied |
| 12 | Batch of 2 classes, one has invalid bytes | Neither class in the batch is installed |

## 13. Self-Check Questions

**1.** You have a new `InvoiceService.class` after fixing a method body and want to apply the compiled version directly to the loaded class. Which do you choose?

> Typically consider `redefineClasses(new ClassDefinition(target, bytes))` because the caller has the full new classfile and wants to use it as the base definition.

**2.** A profiler already has a transformer and wants to add instrumentation to methods of a running class, without a new class file. Which do you choose?

> `retransformClasses(target)` with a transformer registered with `canRetransform=true`, after checking capabilities and modifiability.

**3.** Is it true that `redefineClasses` does not invoke `ClassFileTransformer`?

> No. Redefinition also goes through the transformer pipeline; replacement bytes can be transformed before the JVM verifies and installs them.

**4.** Why does a retransform after a redefine not necessarily use bytes from the original JAR?

> Because the base source for retransform is managed per **the most recent class load or redefine**. When redefining with EDIT bytes, EDIT becomes the new base.

**5.** Does disabling a capable transformer and retransforming always return the original code?

> No. It may only remove that transformer's effect, while non-capable transformations or other transformers remain active. After a redefine, the base has also changed.

**6.** Can a modifiable class with `isRedefineClassesSupported()==true` freely add new fields?

> No. Schema changes must obey JVM TI restrictions; many JVMs only support changing method bodies and certain attributes.

**7.** Are all existing instances recreated after a redefine?

> No. Instances and static state are not automatically recreated or reset. Active frames may continue running old bytecode.

**8.** If you only just registered a transformer with `addTransformer(t,true)`, are already-loaded classes transformed yet?

> Not yet. To process old classes you must call `retransformClasses(target)`; registration does not automatically replay all loaded classes.

**9.** When redefining a class in a plugin loader, is knowing just the name `com.example.Service` enough?

> No. You need the `Class<?>` for the right defining loader and bytes with the matching binary name. A string name alone does not uniquely identify a runtime class.

**10.** In the demo, why is the final string EDIT instead of BASE?

> `redefineClasses` replaced the base source with the EDIT classfile. The retransform pass with patching disabled re-runs from the EDIT base and returns `null`, so the method continues returning EDIT.

## 14. Official Specification Sources

- Java SE 17, `Instrumentation`: `redefineClasses`, `retransformClasses`, byte sources, transformer replay, capabilities, active frames, static fields, and errors: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Java SE 17, `ClassFileTransformer`: transformer ordering, inputs on load/redefine/retransform, `return null`, and `canRetransform`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- Java SE 17, `ClassDefinition`: target class + classfile byte definition used for redefine: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html
- Java SE 17, `java.lang.instrument`: manifest `Can-Redefine-Classes` and `Can-Retransform-Classes`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- JVM TI `RedefineClasses` and `RetransformClasses`: class schema/runtime behavior restrictions: https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html
