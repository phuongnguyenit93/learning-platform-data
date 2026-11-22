# Retransformation Limits: Modifying Method Bodies Is Allowed, Adding Fields/Methods or Changing Inheritance Is Not

In Java instrumentation, `Instrumentation.retransformClasses(...)` helps update **the definition of a class already loaded by the JVM**, for example to add logging statements, collect execution time, or change logic inside a method. However, this is **not a mechanism to replace a class with one of an arbitrary structure**.

On a JVM under the Java 17/JVMTI contract, retransformation can change **method bodies**, the constant pool, and **non-prohibited** attributes. Conversely, it must not change the *schema* of the class: no adding, removing, or renaming fields/methods; no changing method signatures, modifiers, or inheritance relationships; certain special class attributes must also remain stable.

This lesson belongs to the **Retransformation** section and focuses on the question: "Why can changing `return "old"` to `return "new"` succeed, while adding `private int x`, adding a method `foo()`, or changing `extends` fails?"

After this lesson, you will:

- Distinguish between **method body changes** and **class schema changes**.
- Clearly know which changes are **allowed, prohibited, or require further verification**.
- Understand the conditions for `Can-Retransform-Classes`, `isRetransformClassesSupported()`, and `isModifiableClass()`.
- Run a Java 17+ example proving that a method body version is applied, while a version with a **new field** is rejected.
- Understand the fate of objects, static state, and active stack frames after retransformation.
- Know alternative design approaches if you need to "add state" or "add behavior" to a running class.

## 1. What Is Retransformation? It Operates on an *Already Loaded* Class

When the JVM loads a class for the first time, the general flow is:

```text
initial .class bytes
       |
       v
ClassFileTransformer.transform(...)
       |
       v
class file bytes after transformers
       |
       v
JVM verifies/defines class -> java.lang.Class<?> exists
```

After the class is already in the JVM, an agent granted the capability can call:

```java
instrumentation.retransformClasses(com.example.Target.class);
```

This is **an illustrative call**; it assumes the `instrumentation` variable was received via `premain`/`agentmain` and the class `com.example.Target` exists. Retransformation asks the JVM to re-run the bytecode transformation pipeline for the specified class, but **does not define a second class with the same name**, and **does not create a class with a completely different structure**.

On the `java.lang.instrument` API:

```java
void retransformClasses(Class<?>... classes)
        throws UnmodifiableClassException
```

A single call can request multiple classes at once. If an error occurs while verifying/installing the result, the JVM does not install the new version for any of the classes requested in that call. This helps avoid certain partial update states at the class-set level, but does **not** replace business logic and compatibility testing.

**Important starting point:** the original class **has already been defined**. The JVM must preserve the identity and structural information currently used by existing objects, call sites, and linkage mechanisms. Therefore, some changes can be performed during **load-time instrumentation** but are no longer valid when **retransforming** that class later.

## 2. How Does a Method Body Differ from a Class Schema?

Consider the source class:

```java
package demo;

public class Service {
    private int count = 0;

    public String message() {
        return "before";
    }

    public int count() {
        return count;
    }
}
```

### 2.1. Changing a method body: usually valid

```java
public String message() {
    return "after";
}
```

The signature remains:

```text
message()Ljava/lang/String;
```

Everything belonging to the class "skeleton" remains the same as before: class name, superclass, interfaces, fields, method name, descriptor, and modifiers. Only the instructions/constants used inside `message()` are changed. This is **the typical use case** of instrumentation: adding `println`, measurement branches, tracer calls, or modifying part of internal processing.

That does not mean any arbitrary byte array will be accepted. The new class file must be valid, the bytecode must pass the verifier, the instructions/stack map/constant pool must be consistent, and all relevant constraints still apply.

### 2.2. Adding a field: changes the class schema, prohibited

```java
private int count = 0;
private String newState; // Field does not exist in the loaded class.
```

A new field changes the **set of field members** and can affect object layout, reflection metadata, and access behavior. `retransformClasses` does **not** extend the structure of existing objects in that way. On the standard JVM in the example, this attempt is rejected with `UnsupportedOperationException`.

There is no special exception just because the field is `private`, `static`, `transient`, a small reference, or "never read".

### 2.3. Adding a method: also changes the schema, prohibited

```java
public String message() {
    return "after";
}

public void newMethod() {  // New method.
    System.out.println("hello");
}
```

Adding a method changes the set of methods the JVM knows for that class. Retransformation is not used to extend the method table/vtable or create a new API for an already loaded class.

**Important tip when using frameworks:** if an instrumentation tool automatically generates a *synthetic method*, bridge method, accessor, or helper method **inside the target class itself**, the transformation might be valid at initial load time but invalid during retransformation. You must inspect the final bytes returned by the transformer, not just look at the original Java source code.

### 2.4. Changing inheritance relationships: changes the type identity graph, prohibited

```java
// Loaded definition:
public class Child extends BaseA implements Runnable { ... }

// New definition to apply:
public class Child extends BaseB implements AutoCloseable { ... }
```

Changing the direct superclass or the set of direct interfaces alters subtype relationships, method resolution, and dispatch. JVMTI does not allow such inheritance changes during retransformation.

**Changing a call inside the body** from `super.foo()` to another valid call (with the class structure remaining stable) is not equivalent to changing `extends`; the actual bytecode and access rules must be evaluated.

## 3. Matrix: Which Changes Can Be Applied to a Loaded Class?

| Desired Change | Java 17/JVMTI Retransform | Explanation |
|---|---|---|
| Add logging/metrics to an existing method body | **Possible** | Only changes instructions in the `Code` attribute |
| Change branches or constants used in an existing method | **Possible** | Preserves schema, valid bytes |
| Replace `return 1` with `return 2` in method `int value()` | **Possible** | Method name/descriptor unchanged |
| Change exception handling inside a method | **Possible**, must verify | Bytecode and exception table must be valid |
| Modify constant pool to serve the body | **Possible**, within class file limits | Constant pool may change; not a license to change schema |
| Change certain non-prohibited attributes | **Depends on attribute** | JVMTI allows some attributes, but has a prohibited list |
| Add an instance or static field | **No** | Class field set is changed |
| Remove or rename a field | **No** | Field schema is changed |
| Change field descriptor/type | **No** | Field set/schema is not preserved |
| Add a method (including private/synthetic) | **No** | Method set is changed |
| Remove or rename an existing method | **No** | Method set is changed |
| Change return type or parameter types | **No** | Method descriptor/signature is changed |
| Add a new `foo(int)` overload | **No** | Effectively adds a method |
| Change method/class modifiers | **No** | JVMTI prohibits modifier changes |
| Change `extends BaseA` to `extends BaseB` | **No** | Direct superclass changes |
| Add/remove `implements InterfaceX` | **No** | Direct interface set changes |
| Change `NestHost`/`NestMembers` | **No** | Prohibited class attribute change |
| Change `Record` or `PermittedSubclasses` | **No** | Prohibited class attribute change |
| Change the binary name of the class | **No** | Class identity does not match |

Here, **"Possible" does not mean "always succeeds"**: it still depends on whether the JVM has the capability, the class is modifiable, the new bytecode is valid, other transformers modify the bytes, and verifier/linkage/access control requirements.

Similarly, "must not change signature" is not just a Java compiler rule at the source level. The JVM identifies a method by **name + descriptor** in the class file. `void f(int)` and `void f(long)` have two different descriptors; changing a parameter type is equivalent to removing one method and adding another as far as schema matching is concerned.

**Regarding attributes:** the Java 17 JVMTI specification specifically prohibits changing `NestHost`, `NestMembers`, `Record`, and `PermittedSubclasses`; do not infer from "attributes may change" that **every** attribute can be changed. Annotation/signature metadata should also be tested case by case, not automatically placed on an "always allowed" list.

## 4. Why Does the JVM Enforce Keeping the Class Structure Stable?

An existing class is used by the JVM and the program in many places:

- **Object layout:** each instance has field storage already allocated according to the existing class definition.
- **Runtime type checks:** `instanceof`, casts, and method dispatch depend on the inheritance/interface graph.
- **Linkage:** bytecode of other classes may have already resolved field/method references by name + descriptor.
- **Reflection and MethodHandle:** metadata exists and may have already been accessed and cached.
- **Active stack frames:** currently running methods have frames and locals/operand stacks corresponding to the bytecode version that started executing.
- **JIT/native code:** the runtime may have already optimized call paths based on class information.

To allow modifying method bodies **while preserving identity and schema**, the JVM can install **a new executable version of the method** for subsequent invocations; it does not need to invalidate all instances or establish a different type hierarchy immediately.

This is completely different from loading a **new** class using a separate `ClassLoader`: that creates a class with a different identity (the same binary name can still be two runtime types if the loaders differ). Creating a new class with another loader is **not** retransforming the old class.

## 5. Conditions for Calling `retransformClasses` Successfully

### 5.1. Capability is optional

You need **both** a JVM that supports the retransform capability **and** an agent with an appropriate manifest:

```text
Manifest-Version: 1.0
Premain-Class: agent.SchemaAgent
Can-Retransform-Classes: true

```

`Can-Retransform-Classes: true` is a **capability request**, not a guarantee on every JVM. On a supporting JVM, `Instrumentation.isRetransformClassesSupported()` returns `true`. If `false`, calling `retransformClasses(...)` is not a way to force the JVM to enable the capability.

An agent can start with:

```java
if (!inst.isRetransformClassesSupported()) {
    System.out.println("Retransformation not supported");
    return;
}
if (!inst.isModifiableClass(targetClass)) {
    System.out.println("Target class is not modifiable");
    return;
}
```

This is an **illustrative method snippet** (the variables `inst` and `targetClass` must exist), not a standalone program. The two APIs answer **two different questions**:

- `isRetransformClassesSupported()`: does this agent/JVM configuration have this capability?
- `isModifiableClass(targetClass)`: can this specific class be redefined/retransformed based on its class kind?

A class may be considered "modifiable" while the agent's retransform capability is still not enabled. Primitive classes and array classes are not modifiable according to the `Instrumentation` documentation.

### 5.2. Registering a retransform-capable transformer

```java
inst.addTransformer(transformer, true);
```

The `true` parameter requests that the transformer's callback be invoked when `retransformClasses(...)` runs. If the JVM/agent does not support it, registration can throw `UnsupportedOperationException`.

In contrast:

```java
inst.addTransformer(transformer, false);
```

or:

```java
inst.addTransformer(transformer);
```

is a transformer **not capable of being called back** during retransformation. Previous transformation results from this group are **reapplied** according to the contract, rather than calling `transform(...)` again just because retransformation occurred.

Whether the callback is invoked again or not, the **final bytes** after the entire chain of transformers must still preserve the schema allowed by the JVM. Another transformer adding a field can cause retransformation to fail even if your transformer only modifies a single instruction.

### 5.3. When to call?

An agent can register a transformer during `premain(String, Instrumentation)` or `agentmain(String, Instrumentation)`, and then request retransformation after the target class already exists.

- `-javaagent` + `premain`: the agent is started before the application `main`, but can still actively load a class and then retransform it.
- Attach + `agentmain`: the agent is loaded into a running JVM, suitable for enabling instrumentation after startup (if the runtime allows dynamic agent loading).
- Using `-javaagent` does not "automatically retransform by default"; there must be code calling `retransformClasses` or another mechanism requesting the operation.

## 6. Complete Java 17+ Example: Method Body Edit Succeeds, Adding a Field Is Rejected

This example produces **three class files with the same binary name** `demo.Target`, but only **one version** is loaded by the JVM as the real class:

1. **`base`**: the original loaded class, `status()` returns `"before"`.
2. **`body`**: same schema, `status()` returns `"after"`.
3. **`field`**: same as the original schema **except with an added field**, `status()` returns `"forbidden"`.

An agent `SchemaAgent` pre-reads the two replacement class files, registers a `ClassFileTransformer`, and then calls `retransformClasses` twice. The first call using the `body` version must succeed on a capable environment; the second call using the `field` version must be rejected due to the schema restriction.

**Requirements:** JDK 17+ with `javac`, `jar`, `java`, and `Instrumentation` supporting retransformation; no ASM, Byte Buddy, Maven, or Gradle needed. The example was verified using OpenJDK 21 with `javac --release 17`.

### 6.1. File layout

```text
schema-retransform-demo/
├── src/
│   ├── base/demo/Target.java
│   ├── body/demo/Target.java
│   ├── field/demo/Target.java
│   ├── app/demo/App.java
│   └── agent/agent/SchemaAgent.java
├── agent.mf
└── out/                  (generated during compilation)
    ├── base/
    ├── body/
    ├── field/
    └── agent/
```

**You must create the exact `src/...` directories and corresponding files.** The three `Target.java` files with the same package/class name are compiled **separately** into three different output directories; do not pass all three into a single `javac -d out/base` command as that will cause a duplicate class error.

### 6.2. `src/base/demo/Target.java`: original version

```java
package demo;

public final class Target {
    private static int counter = 10;

    public static void increment() {
        counter++;
    }

    public static int count() {
        return counter;
    }

    public static String status() {
        return "before";
    }
}
```

This is the real class loaded by the application class loader. The static state `counter` starts at `10`; to verify that runtime data is not reset, the agent will call `increment()` once before retransforming.

### 6.3. `src/body/demo/Target.java`: method body change only

```java
package demo;

public final class Target {
    private static int counter = 10;

    public static void increment() {
        counter++;
    }

    public static int count() {
        return counter;
    }

    public static String status() {
        return "after";
    }
}
```

Compared to the `base` version, this class has the **same**:

- Name `demo.Target` and modifier `public final`.
- Field `private static int counter`.
- Methods `increment()V`, `count()I`, and `status()Ljava/lang/String;`.
- Default constructor and superclass `java.lang.Object`.

The difference is the instruction/constant used in the **body of `status()`**. The classfile version may have a different constant pool, but the retransformation contract allows this appropriate change.

### 6.4. `src/field/demo/Target.java`: intentionally breaks the schema

```java
package demo;

public final class Target {
    private static int counter = 10;
    private static String addedField = "new";

    public static void increment() {
        counter++;
    }

    public static int count() {
        return counter;
    }

    public static String status() {
        return "forbidden";
    }
}
```

The intentional error-causing difference is:

```java
private static String addedField = "new";
```

Adding a field is a **class schema** change, not just a method body edit. This class file can still **compile validly and load initially** if standalone, but it **cannot be used to replace the schema of the already loaded `demo.Target`** via `retransformClasses`.

This is an important control case: "`javac` compiles without errors" is **not** sufficient proof that the class bytes are a valid update for an existing runtime class.

### 6.5. `src/app/demo/App.java`: application using the version currently in the JVM

```java
package demo;

public final class App {
    public static void main(String[] args) {
        System.out.println("[app] status=" + Target.status()
                + ",count=" + Target.count());
    }
}
```

When run without the agent, the app will print `status=before,count=10`. When the agent updates the body of `status()`, the app will use the new body even though the bytecode on disk in `out/base` is never overwritten.

### 6.6. `src/agent/agent/SchemaAgent.java`: entry point and transformer

```java
package agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.ProtectionDomain;

public final class SchemaAgent {
    static volatile String phase = "none";

    public static void premain(String args, Instrumentation inst)
            throws Exception {

        if (!inst.isRetransformClassesSupported()) {
            System.out.println("[agent] retransformation unsupported");
            return;
        }

        // Intentionally load the real class before registering the transformer:
        // we are TESTING retransformation, not load-time transform.
        Class<?> type = Class.forName(
                "demo.Target",
                true,
                ClassLoader.getSystemClassLoader());

        if (!inst.isModifiableClass(type)) {
            throw new IllegalStateException("Target cannot be modified");
        }

        Method status = type.getMethod("status");
        Method count = type.getMethod("count");
        Method increment = type.getMethod("increment");

        System.out.println("[agent] before=" + status.invoke(null)
                + ",count=" + count.invoke(null));
        increment.invoke(null);

        // Read both files into byte[] before calling retransform.
        // Relative paths are resolved from the JVM's working directory.
        byte[] allowed = Files.readAllBytes(Path.of(
                "out", "body", "demo", "Target.class"));
        byte[] forbidden = Files.readAllBytes(Path.of(
                "out", "field", "demo", "Target.class"));

        inst.addTransformer(
                new PatchTransformer(allowed, forbidden), true);

        phase = "body";
        inst.retransformClasses(type);
        System.out.println("[agent] after-body=" + status.invoke(null)
                + ",count=" + count.invoke(null));

        phase = "field";
        try {
            inst.retransformClasses(type);
            throw new AssertionError(
                    "Adding a field was unexpectedly accepted");
        } catch (UnsupportedOperationException expected) {
            System.out.println("[agent] add-field=REJECTED");
        } finally {
            phase = "none";
        }

        System.out.println("[agent] final=" + status.invoke(null)
                + ",count=" + count.invoke(null));
    }
}

// Non-public top-level class, in the same SchemaAgent.java file.
final class PatchTransformer implements ClassFileTransformer {
    private final byte[] allowed;
    private final byte[] forbidden;

    PatchTransformer(byte[] allowed, byte[] forbidden) {
        this.allowed = allowed;
        this.forbidden = forbidden;
    }

    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {

        if (!"demo/Target".equals(className)
                || classBeingRedefined == null) {
            return null;
        }

        return switch (SchemaAgent.phase) {
            case "body" -> allowed.clone();
            case "field" -> forbidden.clone();
            default -> null;
        };
    }
}
```

**Explanation of each part of the agent:**

1. `isRetransformClassesSupported()` checks the capability before using it.
2. `Class.forName(...)` loads and initializes `demo.Target` **before** the transformer is registered. This clearly distinguishes the experiment from load-time transformation.
3. `status`, `count`, and `increment` are `Method` objects reflecting methods of **the same runtime class**. No new `ClassLoader` is created and no new class name is defined.
4. `increment.invoke(null)` brings `counter` to `11` before updating the method body.
5. `Files.readAllBytes` reads the two pre-compiled classfiles without needing a bytecode manipulation library. Relative paths assume the program is run from the `schema-retransform-demo` directory.
6. `addTransformer(..., true)` registers a transformer capable of participating in retransformation. The manifest in the next section must allow the capability.
7. `phase = "body"` causes the transformer to return bytes of the **same schema, different body** version, and `retransformClasses(type)` asks the JVM to apply it.
8. `phase = "field"` causes the transformer to return bytes of the version **with a new field**. The JVM checks the class schema and rejects it. `UnsupportedOperationException` is printed as a stable label, rather than depending on a specific HotSpot error message.
9. `finally { phase = "none"; }` returns the transformer to a mode that applies no further transformations.
10. If retransformation fails, the `field` version is **not installed**; the method updated in the previous successful call remains in effect.
11. `return null` in the transformer means **do not change bytes** for callbacks not belonging to `demo.Target` or not part of the retransformation phase being tested. `return allowed.clone()` / `forbidden.clone()` returns a new array without directly modifying `classfileBuffer`.

A common question: why does `SchemaAgent` keep the `phase` variable as `volatile`? Because the JVM callback may execute in the context of another thread, and the variable is used to select the byte version. `volatile` ensures basic visibility; for an agent with **multiple concurrent class retransformations**, a more complex state and correlation design is needed instead of using a global flag like in the demo.

This code uses a `switch` expression supported by Java 17 without needing Java preview features. The `transform(Module, ...)` form is the `Module` overload of `ClassFileTransformer` on Java 9+.

### 6.7. Manifest `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: agent.SchemaAgent
Can-Retransform-Classes: true

```

`Premain-Class` selects the startup agent entry point. `Can-Retransform-Classes: true` requests the retransform capability. You must keep a trailing blank line ending the main section when creating the manifest file.

`Can-Redefine-Classes: true` is not needed for this example because it **does not call `redefineClasses`**. The two capabilities are independent and you must check the exact API being used.

### 6.8. Compile and JAR packaging commands (JDK 17+)

Open a terminal in the root directory `schema-retransform-demo`, where `src` and `agent.mf` are located. Create the output directories:

```bash
mkdir out
mkdir out/base
mkdir out/body
mkdir out/field
mkdir out/agent
```

If a directory already exists, skip the corresponding creation command. Then compile each version of the same class name into **separate directories**:

```bash
javac --release 17 -d out/base src/base/demo/Target.java
javac --release 17 -d out/body src/body/demo/Target.java
javac --release 17 -d out/field src/field/demo/Target.java

javac --release 17 -cp out/base -d out/base src/app/demo/App.java
javac --release 17 -d out/agent src/agent/agent/SchemaAgent.java
```

The fourth `javac` command places `App.class` on the same classpath as the original `Target` version. The agent is compiled separately and has **no compile-time dependency** on `demo.Target`; it uses reflection to access the runtime class.

Package **only the two agent classes** into the JAR:

```bash
jar --create --file schema-agent.jar --manifest agent.mf -C out/agent agent/SchemaAgent.class -C out/agent agent/PatchTransformer.class
```

`SchemaAgent.java` contains two top-level classes (`public` `SchemaAgent` and package-private `PatchTransformer`), so `javac` generates **two `.class` files**. Both must be included in the JAR to avoid `NoClassDefFoundError` when the agent instantiates the transformer.

Inspect the archive:

```bash
jar --list --file schema-agent.jar
```

The important entries must be present:

```text
META-INF/MANIFEST.MF
agent/SchemaAgent.class
agent/PatchTransformer.class
```

`demo.Target` is not in the agent JAR; the JVM loads it from `-cp out/base`. The two replacement versions `out/body/demo/Target.class` and `out/field/demo/Target.class` sit on the filesystem for the agent to read at runtime.

### 6.9. Running and explaining stdout

Without the agent:

```bash
java -cp out/base demo.App
```

Stdout:

```text
[app] status=before,count=10
```

With the agent:

```bash
java -javaagent:schema-agent.jar -cp out/base demo.App
```

**Stdout actually verified on OpenJDK 21 with all classes compiled with `--release 17`:**

```text
[agent] before=before,count=10
[agent] after-body=after,count=11
[agent] add-field=REJECTED
[agent] final=after,count=11
[app] status=after,count=11
```

Line-by-line explanation:

- **Before:** the `out/base/demo/Target.class` version is loaded; `status()` returns `"before"`, and the newly initialized `counter` is `10`.
- **After-body:** the first retransformation **is accepted**, new invocations of `status()` return `"after"`; `counter=11` because `increment()` was called earlier.
- **Add-field REJECTED:** the second version has the field `addedField`, changing the schema, and the JVM rejects it.
- **Final:** the class still uses the updated body version and does not turn into the version containing the new field; the static counter remains `11`.
- **App:** after `premain` finishes, `App.main()` calls the same existing class, seeing the updated method body and the old state.

This is an example of **the same class object being retransformed**, with no operation replacing the class file in `out/base` and no second class loader. The `REJECTED` line is printed by **the agent code itself** when catching `UnsupportedOperationException`; detailed JVM error messages vary between versions and should not be used as test assertions.

**If the JVM does not support retransformation:** `SchemaAgent` will print `[agent] retransformation unsupported` and return, and the application runs the original version. On the successfully tested environment (OpenJDK 21), that branch did not execute.

### 6.10. Inspecting classfiles with `javap`

```bash
javap -p -classpath out/base demo.Target
javap -p -classpath out/body demo.Target
javap -p -classpath out/field demo.Target
```

Check:

- `base` and `body`: same fields and same method declarations; different `status()` body (see `javap -c`).
- `field`: has an additional field `private static java.lang.String addedField;`.

To view instructions:

```bash
javap -c -p -classpath out/base demo.Target
javap -c -p -classpath out/body demo.Target
```

In the `status()` method, the two versions have `ldc` pointing to different string constants followed by `areturn`. Constant pool indices may differ between compiled versions; **do not depend on exact offsets/indices**—instead inspect behavior and structure.

## 7. Are Objects, Static Fields, and `<clinit>` Recreated on Retransformation?

**No.** Retransformation does not make the JVM re-initialize the class at the agent's request. Existing objects are not recreated or reallocated for field storage; their field values remain their runtime values prior to the update (unless application/agent code actively modifies them afterward).

In the example, before retransformation:

```text
demo.Target.counter = 11
```

The `body` version has the source declaration `private static int counter = 10`, but updating does not mean the JVM re-runs `<clinit>` and resets it to `10`. The output proves that after retransformation **it is still 11**.

Distinguish three cases:

1. **Initial class initialization:** the JVM executes class initialization according to normal Java semantics.
2. **Retransformation of an already initialized class:** does not re-run `<clinit>` to reset static fields.
3. **New method logic itself modifies state when called:** it can modify fields normally via the new code, but that is method execution behavior, **not** a reset effect caused by retransformation.

If an agent needs a new state structure attached to each object without being able to add a field, it must design a state store **external to the target class** or change the design before load time, rather than assuming the JVM will allocate extra object slots.

## 8. Active Stack Frames: Why Might Running Code Still See Old Bytecode?

Another important point of the contract is **method version**.

When a class is updated via retransformation:

- **New method calls** after the update will use the new method version.
- **Stack frames already executing that method** at the time of the update may continue running **the old version's bytecode** until the frame completes.

Model:

```text
Thread A                            Thread B / Agent
--------                            ----------------
enter Service.work() [old bytes]
   |
   |---- work is running -------------------|
   |                                        |
   |                              retransform Service
   |                                 old -> new
   |                                        |
   |---- running frame still on old --------|
   |
return old outcome

next work() call ------------------> new method version
```

Therefore, a successful retransformation **does not mean all currently running calls immediately switch to the new code mid-method**. If you inject tracing advice into a very busy method, invocations that started before the update may not emit new events from those old active frames.

Do not write measurements relying on the assumption that "immediately after `retransformClasses` returns, every stack frame is already instrumented." This is an important practical difference when enabling an agent in a production system actively handling requests.

**Additional note:** old frames continue using old bytecode, but heap/object/field state is still shared at runtime. "Old bytecodes" does not mean creating a copy of the heap, static state, or a parallel class hierarchy.

## 9. How Does Retransformation Differ from Redefinition and Load-Time Instrumentation?

| Mechanism | Timing | Main Input | Can Add Fields/Methods to a Loaded Class? |
|---|---|---|---|
| Load-time `ClassFileTransformer` | **Before the JVM defines** the class for the first time | Initial class bytes at load time | Can create a different valid class schema at load time, subject to bytecode/runtime limits |
| `Instrumentation.retransformClasses` | **After the class has loaded** | JVM starts from initial class bytes and re-runs the transformer chain per contract | **No** under Java 17 JVMTI |
| `Instrumentation.redefineClasses` | **After the class has loaded** | Agent supplies new class bytes via `ClassDefinition` | **No** under Java 17 JVMTI |

**Do not use `redefineClasses` as a trick to bypass the schema limits** of `retransformClasses`. The two mechanisms differ in how bytes are supplied, but `RedefineClasses` also prohibits the schema, modifier, and inheritance changes discussed here.

### Retransformation pipeline with multiple transformers

According to `Instrumentation.retransformClasses`:

1. The JVM starts from the appropriate initial class file bytes, which may not be bit-for-bit identical to the bytes on disk.
2. Transformations from **non-capable** transformers (`addTransformer(t, false)`) from a previous load/redefine are **reapplied** without invoking their callbacks again.
3. **Capable** transformers (`addTransformer(t, true)`) are invoked again in group order.
4. The JVM verifies the **final bytes**; only then does it install the new class definition if valid.

Therefore, if another transformer in the chain added a member when the class was **initially** loaded, reapplying that transformation can make the bytecode layout look different from the original `.class` file while still remaining consistent with the existing definition. You need to inspect **the schema already defined by the JVM**, not just `javap` on the original source file, to analyze accurately.

## 10. "Adding Fields/Methods for Measurement" Scenarios: Alternative Designs

Some instrumentation libraries want to inject:

- `private long $timerStart;` into each instance.
- `private static Counter $counter;` into the class.
- `private void $helper$method()` to be called from the modified body.
- A new interface to add a marker or hook behavior.

All of these are **class structure** changes if performed on the already loaded class itself. Retransformation is not the appropriate tool.

### 10.1. Using state outside the target class

Instead of adding a field to an already loaded `Service`:

```java
// Design idea, NOT a standalone agent.
private static final Map<Object, State> states =
        Collections.synchronizedMap(new WeakHashMap<>());
```

This is an **illustrative field snippet** in a separate state-managing class, not code injected into the target. `WeakHashMap` is only useful when you clearly understand object lifecycles, equality/hashCode, and key/value liveness; if `State` accidentally holds a strong reference back to the key, data can still be retained. In high-concurrency systems, you need to design appropriate thread-safety, identity semantics, and GC behavior.

If the instrumentation point only needs **per-invocation** state (timestamp, trace context), it is usually kept in local variables/stack inside the instrumented method body, or in an appropriate tracer service, without necessarily adding an instance field.

### 10.2. Putting helper methods in **another class**

If complex supporting logic is needed:

```java
// Illustrative method body snippet of the target class after transformation:
public int work(int x) {
    AgentHelper.onEnter();
    try {
        return x * 2;
    } finally {
        AgentHelper.onExit();
    }
}
```

This **does not add a method to the target class**; it only modifies the body of `work` to call a method on `AgentHelper` belonging to a **separate helper class** that is validly loaded/packaged. You must ensure the helper is actually visible to the target's class loader/module, has access permissions, and does not cause recursion when instrumenting.

Do not confuse "a new method body calling a new method on a helper class" with "adding a new method to the target class." The former is a potentially valid body edit; the latter changes the schema.

### 10.3. If you truly need to add fields/methods, do it before the class is defined

If you control load-time instrumentation, you can transform class bytes **before the JVM defines the class for the first time** to produce the desired schema. However, you must sufficiently prepare for compatibility, class loading, verification, class initialization, and calling code.

If the class has already loaded, another option is to **deploy a new software version and restart** or use an explicitly managed class-loader versioning architecture. Changing loaders can create a different type identity and requires resolving references/serialization; it is not a simple "bypass retransform".

### 10.4. Not every state-tracking requirement needs a schema change

For example, "adding a counter" can be solved by:

- An external counter, keyed by method ID/class identity.
- A span start timestamp in a local variable injected into the method.
- A thread-local context with a properly managed lifecycle.
- A weak-key state store with clear eviction/GC and identity policies.
- Having existing code call a helper to observe, rather than adding a field to the object.

Each approach has tradeoffs in memory, overhead, thread-safety, and classloader leaks, but all avoid asking the JVM to add fields to a loaded class.

## 11. Modifier, Attribute, and Inheritance Limits — Commonly Missed Cases

The Java 17 JVM TI specification explicitly states that in addition to field/method changes, it prohibits:

- **Changing method/class modifiers**: e.g., changing `public` to `private`, `final` to non-`final`, or changing the static nature of a method.
- **Changing the direct superclass**: `extends A` to `extends B`.
- **Changing the set of direct interfaces**: `implements A` to `implements A, B`.
- **Changing `NestHost`/`NestMembers`**: nest relationships used for access control of related classes.
- **Changing the `Record` attribute**: record structural metadata (Java 16+).
- **Changing `PermittedSubclasses`**: the list of permitted subclasses of a sealed class (Java 17+).

A bytecode library might produce a `.class` that is formally valid yet alters these attributes when rebuilding the class. **A valid class file is not enough**, because it must also be valid **as a replacement version of the currently running class itself**.

For example:

```text
Old: class demo.Service extends java.lang.Object
New: class demo.Service extends demo.Parent
```

Even if `Parent` exists and the new class could be loaded normally by the JVM as a standalone type, it **cannot** be installed onto the existing runtime type `demo.Service` via retransformation.

Similarly, changing a `public int f()` to `private int f()` might not change the descriptor yet still makes **the modifiers different**, so it is also prohibited. Do not limit your checklist to comparing field/method names.

## 12. Common Errors: Identifying Capability, Target Class, and Schema Failures

| Symptom | Possible Reason | How to Handle |
|---|---|---|
| `isRetransformClassesSupported()` returns `false` | JVM/agent lacks capability; manifest does not request it | Check `Can-Retransform-Classes: true` and runtime |
| `addTransformer(t, true)` throws `UnsupportedOperationException` | Retransform capability not enabled | Check support before registering |
| `retransformClasses` throws `UnmodifiableClassException` | Target is not modifiable | Check `isModifiableClass(target)` |
| `retransformClasses` throws `UnsupportedOperationException` | Missing capability **or** unsupported schema/other change | Distinguish via pre-check; inspect new bytecode |
| Agent only logs, method does not change | Transformer returns `null`, filter does not match, or not called on retransform | Check internal `className` format, `true` registration, returned bytes |
| Transformer reports success but old method still runs in a thread | That frame was already active beforehand | New invocations use the new method version |
| Body changed but `VerifyError` or classfile error occurs | Invalid bytecode/stack map/constant pool | Run verifier, `javap`, check byte-editing tool |
| Changing `extends` or adding an interface is rejected | Inheritance graph was changed | Keep direct superclass/interfaces unchanged |
| Adding a `private static` field is still rejected | A static field is also part of the class schema | Store state in a helper class/outside the target |
| Helper method does not exist in the original version | Adding a method to the target is prohibited | Move logic to a separate helper class |
| An earlier retransform succeeded, a later one fails | The later bytes contain an invalid change | Ensure the failed attempt does not install a new version; inspect final bytes |
| Reflection does not show the new field | Retransform is not allowed to add fields | Do not use reflection as "proof" that the field was just added |
| `ClassNotFoundException`/`NoClassDefFoundError` from helper | Classloader/module cannot see the new dependency | Check visibility, classpath, loader, and module access |
| `ClassFormatError`/`UnsupportedClassVersionError` | Invalid bytes or incompatible classfile version | Compile for the right target JDK and validate |

**Do not catch every `Throwable` and print "schema rejected"**. An `IOException` from reading the wrong file, a `ClassFormatError` from corrupted data, or a classloader error is completely different from the JVM rejecting an added member. The example in section 6 only treats `UnsupportedOperationException` as an indicator of the prohibited branch after passing the capability pre-check.

## 13. Practical Preflight Before Retransforming in Production

A safe workflow should include:

1. **Lock onto the exact target class:** class name together with `ClassLoader`/`Module`, do not select by string alone when multiple loaders exist.
2. **Check capability:** `inst.isRetransformClassesSupported()`.
3. **Check each class:** `inst.isModifiableClass(clazz)`.
4. **Check manifest:** `Can-Retransform-Classes: true`; if using attach, check dynamic agent loading policies separately.
5. **Evaluate schema:** compare field/method names/descriptors, class modifiers, superclass/interfaces, and prohibited attributes between before and after versions.
6. **Preserve method descriptors and access flags:** especially when libraries tend to generate bridge/synthetic methods.
7. **Check bytecode:** stack map frames, max stack/locals, labels, exception tables, and the verifier.
8. **Test multiple transformers:** ensure no other transformer alters the schema at the final step.
9. **Test active invocations:** do not assume every frame immediately uses the new bytecode.
10. **Test state preservation:** existing object and static state must be preserved.
11. **Plan rollback:** to remove instrumentation, you need to know the transformer chain and source bytes; `return null` in a new callback does not automatically undo all changes from other transformers.
12. **Roll out in stages:** measure callback overhead/latency, verifier errors, classloader leaks, and impact on production traffic.

In a complex pipeline, **the final returned classfile** is what the JVM verifies. It is not enough if your transformer preserves the schema while an adjacent transformer adds a field or modifies modifiers.

### 13.1. Comparing schemas before sending bytes

If you have two class file versions on disk, you can use:

```bash
javap -p -classpath out/base demo.Target
javap -p -classpath out/body demo.Target
javap -p -classpath out/field demo.Target
```

This is an **illustrative check**, not a complete schema comparison for every kind of attribute. For complex problems, use a ClassFile reader/ASM library or the Java Class-File API in an appropriate JDK to compare systematically.

### 13.2. Do not conflate compile-time, load-time, and runtime schemas

There are three things that are often confused:

- **`.class` file on disk:** can be recompiled at any time.
- **New class loaded by the JVM for the first time:** can have an instrumented schema from the start.
- **Already existing `Class` object:** can only be updated within the JVM's retransform/redefine limits.

In the example, `out/field/demo/Target.class` can compile **validly**, but that does not mean it can be installed into the existing runtime class `demo.Target`. The JVM does not just check "are the bytes valid", but also "are the bytes allowed to be **a new version of that exact type**".

## 14. Practice Exercises

**Question 1.** A loaded class has a method `int cost()` returning `3`. An agent modifies the method body to return `5` without changing the method name/descriptor. Can it be retransformed?

**Answer:** Yes, if the capability/class is modifiable and the bytecode is valid; this is a typical body edit.

**Question 2.** An agent wants to add a field `private long startNs` to a loaded class to track per-instance timing. Can `retransformClasses` be used?

**Answer:** No. A new field changes the class schema. Use external state or design the instrumentation before load time; if a real schema change is needed, a different release/architecture path is required.

**Question 3.** An agent adds `private static final String TAG = "x"` to a loaded class, reasoning that a static field does not change object layout. Is this valid?

**Answer:** No. Even though it does not increase instance size, it still adds a **field in the class schema**.

**Question 4.** An agent replaces the body of `foo(int)` with new code while also changing it to `foo(long)`. Is this valid?

**Answer:** No. The descriptor changes from `(I)` to `(J)`; the method signature changed.

**Question 5.** An agent changes `extends BaseA` to `extends BaseB`, where both superclasses are valid and have the same interfaces. Is it accepted?

**Answer:** No. The direct superclass changed, violating the inheritance restriction.

**Question 6.** An agent adds no members, but changes `public` to `private` on a method. What is the result?

**Answer:** Rejected due to the modifier change restriction.

**Question 7.** After retransformation, does a method currently running in Thread A immediately switch to the new code on the next instruction?

**Answer:** No. Active frames continue executing the bytecode of the old method version; new invocations use the new version.

**Question 8.** `Target.counter` is currently `11`. The new classfile version has `private static int counter = 10;`. Does retransformation reset `counter` to `10`?

**Answer:** No. Retransformation does not re-run the class initializer, and existing static state is preserved.

**Question 9.** Another transformer in the pipeline adds a synthetic helper method before the result reaches the JVM. Your transformer only changes `ireturn` in the body. Can retransformation succeed?

**Answer:** Cannot be guaranteed; the JVM inspects the final bytes of the entire chain. If the final result adds a method compared to the runtime schema, that change is not allowed.

**Question 10.** If `retransformClasses(type)` is rejected for adding a field, is the method body from a previous retransformation automatically reset to the original version?

**Answer:** No. A failed update does not install a new definition; the previously successfully installed version remains the active one.

**Question 11.** Can `NestMembers` or `PermittedSubclasses` be changed without adding methods/fields?

**Answer:** No. These are class attributes on the prohibited list in Java 17 JVM TI.

**Question 12.** You want new helper logic to serve the body of `Service.work()`, but `Service` is already loaded. What is an appropriate approach?

**Answer:** Put the helper method in **another visible class** and modify the body of `Service.work()` to call that helper; you must still ensure valid bytecode/loader/module access.

## 15. Summary

- Retransformation is a tool for **updating the bytecode of an already loaded runtime class**, not a tool for changing the entire class schema.
- **Editing method bodies** is the core use case; changing the constant pool and certain attributes can be valid if within limits and passing the verifier.
- **Adding/removing/renaming fields or methods, or changing descriptors, modifiers, or inheritance** are invalid changes for Java 17/JVMTI retransformation.
- `NestHost`, `NestMembers`, `Record`, and `PermittedSubclasses` are also among the class attributes that **must not be changed**.
- `Can-Retransform-Classes: true`, `isRetransformClassesSupported()`, and `isModifiableClass()` are necessary checks, but they do not guarantee the new bytes are valid.
- **Object and static field state are not reset** on retransformation; active stack frames may continue running old bytecode, while new invocations use the new method version.
- `redefineClasses` is **not** a way to work around schema constraints in Java 17.
- When new state/helpers are needed after startup, consider a **helper class**, an **external state store**, or **load-time instrumentation** before the class is defined.
- The JDK 17+ example verified in practice: **body edit succeeds, added field is rejected, state is not lost**.

## Official Documentation

- Oracle Java 17 — [`Instrumentation.retransformClasses(...)`, capabilities, active stack frames, and atomic failure](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html).
- Oracle Java 17 — [JVM Tool Interface, `RetransformClasses`: allowed/prohibited changes, method modifiers, class attributes, error codes](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html).
- Oracle Java 17 — [`ClassFileTransformer`: callbacks, group order, `return null`, and byte usage](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html).
- Oracle Java 17 — [Package `java.lang.instrument`: manifest capabilities and startup agents](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html).
- Oracle Java 17 — [Java Virtual Machine Specification, Class File Format (Chapter 4)](https://docs.oracle.com/en/java/specs/jvms/se17/html/jvms-4.html).
