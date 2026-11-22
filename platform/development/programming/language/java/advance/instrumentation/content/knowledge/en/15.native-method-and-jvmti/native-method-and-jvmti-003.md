# `setNativeMethodPrefix` and `Can-Set-Native-Method-Prefix` in Java Instrumentation

A Java agent can add bytecode to a **regular Java method**, but a method declared `native` **has no Java bytecode body** in which to insert instructions before or after a JNI call. To instrument at the **Java → native boundary**, an agent typically uses a `ClassFileTransformer` to create **a non-`native` wrapper method** and move the original native method to a **prefixed name**. The JVM then needs a mechanism to bind the renamed native method to the **JNI implementation that still carries the old name**.

The set of tools that directly solves this:

- **`Can-Set-Native-Method-Prefix: true`** in the agent JAR's `META-INF/MANIFEST.MF`: **requests the native-method prefix capability**.
- **`Instrumentation.isNativeMethodPrefixSupported()`**: checks whether the current JVM/agent **actually has the capability**.
- **`Instrumentation.setNativeMethodPrefix(transformer, prefix)`**: registers **a prefix associated with a registered transformer**, so that **JNI native method resolution** can try an additional name-matching rule when normal lookup fails.

**Core point:** `setNativeMethodPrefix` **does not transform `.class` files itself, does not create wrappers itself, does not rename Java methods, and does not load `.dll/.so` libraries**. It only **modifies the retry rule when normal native implementation binding fails**. Creating the wrapper + renamed native method is the **separate responsibility of `ClassFileTransformer`**.

This lesson belongs to the **Native and JVM TI** group: it describes the Java Instrumentation mechanism, its correspondence with `JVMTI SetNativeMethodPrefix`, JNI automatic resolution/`RegisterNatives`, how to use the capability safely, and two hands-on labs: one **pure Java 17+** API test and one **real JNI verification with a C library** on Linux.

## 1. Why cannot a `native` method be instrumented like a Java method?

Java example:

~~~java
package demo;

public class NativeTarget {
    public native int add(int value);
}
~~~

A method with the `ACC_NATIVE` flag in a class file **has no `Code` attribute**. It does not carry Java opcodes such as `ILOAD`, `IADD`, `INVOKESTATIC`, or `IRETURN` for a transformer to insert logging or timestamp calls in between.

Comparison:

| Method | Has a `Code` body to modify? | Common instrumentation approach |
|---|---|---|
| `int add(int x) { return x + 5; }` | Yes | Transform the opcodes inside the method |
| `native int add(int x);` | **No** | Create a **Java wrapper** with bytecode; the wrapper calls a separate native method |
| `abstract int add(int x);` | No | Cannot insert into an abstract body; need to target a concrete implementation |

The goal is to turn the call:

~~~text
Application
   └── NativeTarget.add(7)
         └── native implementation add → 12
~~~

into:

~~~text
Application
   └── NativeTarget.add(7)       // Java wrapper
         ├── before JNI: measure time / record event
         ├── call $AgentWrapped$add(7)
         │     └── native implementation add → 12
         └── after JNI: record metric / cleanup
~~~

For a `native` method, the agent does not generate bytecode **inside the C function**; it places measurement code in the **Java wrapper surrounding the JNI boundary**. This is why *native method prefixing* is valuable.

## 2. Before and after wrapping a native method

Suppose the source class has the method:

~~~java
public native boolean foo(int x);
~~~

A class-file transformer can produce the equivalent model:

~~~java
public boolean foo(int x) {
    long start = System.nanoTime();
    try {
        return $AgentWrapped$foo(x);
    } finally {
        record(System.nanoTime() - start);
    }
}

private native boolean $AgentWrapped$foo(int x);
~~~

**This is Java-level pseudocode for the result of a class-file transformation**, not two methods to paste verbatim into a source class without declaring `record(...)`. In a real transformation:

1. The Java method **`foo(int)`** keeps the same name and descriptor so application code still calls `foo` as before, but removes the `ACC_NATIVE` flag and has a `Code` body.
2. The native method is named **`$AgentWrapped$foo`**; it must preserve the **same parameter/return types** and the necessary modifiers for valid linking and calling.
3. The wrapper records metrics and then calls the renamed native method.
4. An existing JNI library may still export the implementation under the name **`foo`**, not `$AgentWrapped$foo`. That is the part `setNativeMethodPrefix` assists with when the JVM performs linking.
5. The final class bytes must pass the class-file verifier. If the wrapper modification is complex, you must properly handle the constant pool, method descriptors, operand stack, exception table, and stack map frames.

Because JNI names and binding involve class/method identity, you cannot simply do an arbitrary `String.replace` on a `.class` file. **Adding the wrapper method, changing `ACC_NATIVE`, and building the code** belong to class-file transformation; this requires ASM, Byte Buddy, or the Class-File API on an appropriate JDK.

## 3. Manifest: `Can-Set-Native-Method-Prefix`

Manifest of an agent run with `-javaagent`:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.PrefixAgent
Can-Set-Native-Method-Prefix: true

~~~

Four basic rules:

1. The attribute must be in the **main section** of the **manifest inside the agent JAR** that the JVM actually loads, not a standalone `.MF` file or the manifest of an arbitrary app JAR.
2. **`Can-Set-Native-Method-Prefix` defaults to `false`** when omitted. The boolean `true`/`false` is case-insensitive; any value other than `true` is treated as `false`.
3. Declaring `true` is a **capability request**, not a guarantee that every JVM provides it. You must check at runtime with `isNativeMethodPrefixSupported()`.
4. `Premain-Class` specifies the class with the `premain` callback when using `-javaagent`. If the agent is loaded dynamically in an environment that allows it, the entrypoint typically uses `Agent-Class`/`agentmain`; that is a different startup mechanism and does not change the meaning of the capability.

**Do not confuse it with two other attributes:**

| Manifest attribute | Capability |
|---|---|
| `Can-Set-Native-Method-Prefix` | Allows configuring **native method prefix lookup fallback** |
| `Can-Retransform-Classes` | Allows retransforming already-loaded classes per the JVM contract |
| `Can-Redefine-Classes` | Allows redefining already-loaded classes with new class-file bytes |

The three flags are **independent**. Enabling native prefix does not automatically grant retransform or redefine permissions. To create a wrapper containing a **new method** and change method structure, the common approach is to **transform during initial class definition**, because redefinition/retransformation of already-loaded classes has many restrictions on adding/removing methods and modifying schemas.

## 4. Three Java APIs to understand properly

### 4.1. Querying the capability

~~~java
boolean supported = inst.isNativeMethodPrefixSupported();
~~~

`inst` is the `java.lang.instrument.Instrumentation` instance passed by the JVM to `premain`/`agentmain`, not an object created by the application.

`true` means that in the **current JVM configuration**, setting a native prefix is supported (appropriate manifest and the JVM has the capability). `false` means it is not. Per the API, calling it multiple times in the **same JVM** returns the same result.

You cannot infer "every native method is currently being instrumented" from `true`; this is only the ability to configure resolution.

### 4.2. Registering the transformer first

~~~java
ClassFileTransformer transformer = new ClassFileTransformer() {
    // Can override transform(...) to build the class-file wrapper.
};

inst.addTransformer(transformer, false);
~~~

This is a valid Java snippet inside an agent callback (requires importing `java.lang.instrument.ClassFileTransformer`). Registering the transformer makes it participate in the **class-file transformation chain** at the points supported by the API. In the hands-on demo below, the transformer **intentionally does not modify bytes** because the Java class already has a pre-compiled wrapper.

**The transformer must already be registered with `addTransformer` before setting the prefix.** Calling `setNativeMethodPrefix` for an unregistered transformer throws `IllegalArgumentException`.

### 4.3. Setting the prefix

~~~java
if (inst.isNativeMethodPrefixSupported()) {
    inst.setNativeMethodPrefix(transformer, "$AgentWrapped$");
}
~~~

Signature:

~~~java
void setNativeMethodPrefix(
        ClassFileTransformer transformer, String prefix);
~~~

Meaning:

- `transformer`: **the exact object registered with `addTransformer`**, not just a new object of the same class.
- `prefix`: the prefix string the transformer uses when **naming wrapped native methods**.
- **`null` or empty string `""`**: **do not retry native resolution with a prefix for that transformer**.
- **A separate prefix per transformer** helps the JVM analyze multiple wrapper layers applied sequentially.

**The prefix name should be unlikely to collide with existing valid method names**, for example `"$MyAgentNative$"` or a prefix with a fixed agent-specific namespace. Short names like `"wrapped_"` can collide with existing methods; the Oracle specification also warns about this.

You should not choose a random prefix on every callback when native methods have already been renamed with an older prefix. The prefix must **match exactly** how the transformer names methods and must remain in place during the phase when the JVM can still bind the corresponding native methods.

## 5. How does `setNativeMethodPrefix` actually change **native method resolution**?

There are two typical JNI binding paths:

1. **Automatic native resolution**: the JVM automatically searches for the corresponding JNI symbol in loaded native libraries.
2. **Explicit registration** via JNI **`RegisterNatives`**: native code registers Java methods with C/C++ function pointers.

Both are supported by the native prefix API, though the name-retry direction differs slightly.

### 5.1. Automatic resolution

Suppose the transformer renames the Java native method `foo` to `$AgentWrapped$foo`, while the existing library still exports:

~~~text
Java_somePackage_someClass_foo
~~~

When the native method `$AgentWrapped$foo` is called:

~~~text
Step 1: The JVM tries the normal JNI name of "$AgentWrapped$foo".
             │
             ├─ If a matching symbol is found: use it as normal.
             │
             └─ If not found:
                  try stripping the prefix "$AgentWrapped$"
                  when matching the implementation name
                        │
                        ▼
             Original JNI symbol of "foo"
~~~

In the fallback step, **the JVM does not modify class/method names in bytecode**; it only uses an additional name-resolution rule to reach the implementation of `foo`. If the original native library is not loaded or does not contain the right symbol, the prefix **cannot** conjure up an implementation.

Important point: the prefix **is only considered when normal resolution fails**. It does not disable JNI symbols that actually match the prefixed name and does not unconditionally redirect all native methods.

### 5.2. Explicit `RegisterNatives`

The JNI function has the form:

~~~c
jint RegisterNatives(
        JNIEnv *env, jclass clazz,
        const JNINativeMethod *methods, jint nMethods);
~~~

When a native library uses `RegisterNatives` with the old name `foo`, the transformed class may contain:

~~~text
foo(int)                  → Java wrapper, NOT native
$AgentWrapped$foo(int)     → actual native method
~~~

With a registered prefix, if the normal association for `foo` fails, the JVM can **try adding the prefix** to find the right native method `$AgentWrapped$foo` and attach the function pointer that was provided under the name `foo`.

This is the **reverse search direction** compared to automatic JNI symbol lookup:

| JNI binding | Initially the JVM tries | Fallback on failure |
|---|---|---|
| Automatic | Prefixed native Java method → prefixed JNI symbol | Strip prefix from the target implementation name → original JNI symbol |
| `RegisterNatives` | Method name in the native registration table | Prepend prefix to candidate Java method name to find the renamed native method |

This mechanism is not a JNI compiler, does not patch DLLs/SOs, and does not guarantee the right provider/native function if the class loader, symbol, or method descriptor is wrong.

## 6. Lab 1: testing capability and API errors with Java 17+

The first lab **does not need a C compiler**. It demonstrates that the manifest determines the capability, that a valid transformer must be registered first, and the errors related to the transformer object. This is **not** a native binding demo; the real JNI example is in the next section.

Structure:

~~~text
prefix-api-lab/
├── src/demo/
│   ├── PrefixAgent.java
│   ├── ProbeTarget.java
│   └── ProbeMain.java
├── PREFIX-ON.MF
├── PREFIX-OFF.MF
└── out/
~~~

### 6.1. `src/demo/PrefixAgent.java`

~~~java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class PrefixAgent {
    public static void premain(String args, Instrumentation inst) {
        System.out.println("supported="
                + inst.isNativeMethodPrefixSupported());

        ClassFileTransformer transformer =
                new ClassFileTransformer() {
                    @Override
                    public byte[] transform(
                            Module module,
                            ClassLoader loader,
                            String className,
                            Class<?> classBeingRedefined,
                            ProtectionDomain protectionDomain,
                            byte[] classfileBuffer) {
                        if ("demo/ProbeTarget".equals(className)) {
                            System.out.println("transformTarget=true");
                        }
                        return null;
                    }
                };

        inst.addTransformer(transformer, false);

        try {
            inst.setNativeMethodPrefix(transformer, "$Agent_");
            System.out.println("prefix=registered");
        } catch (UnsupportedOperationException error) {
            System.out.println("prefix=unsupported");
        }

        if (inst.isNativeMethodPrefixSupported()) {
            try {
                inst.setNativeMethodPrefix(
                        new ClassFileTransformer() {},
                        "$Unknown_");
            } catch (IllegalArgumentException error) {
                System.out.println(
                        "unregistered=IllegalArgumentException");
            }

            try {
                inst.setNativeMethodPrefix(null, "$Other_");
            } catch (NullPointerException error) {
                System.out.println(
                        "nullTransformer=NullPointerException");
            }
        }
    }
}
~~~

**Explanation:**

- `transformer` is registered **by its specific object instance**; the prefix is set for that exact object.
- The `transform` method only prints a log for `demo/ProbeTarget`, then **`return null`**. It **does not modify `.class`** and does not create a wrapper. Therefore this program measures **API registration**, and does not prove JNI linking.
- The prefix is still set validly because the JVM/agent has the capability if `isNativeMethodPrefixSupported()` is `true`.
- For an **unregistered** transformer (the second anonymous instance), the API throws `IllegalArgumentException`.
- For `transformer=null`, the API throws `NullPointerException`.
- A manifest with the capability disabled causes the otherwise valid call (`setNativeMethodPrefix` on a registered transformer) to throw `UnsupportedOperationException`; the code catches it and prints `prefix=unsupported`.

### 6.2. `src/demo/ProbeTarget.java`

~~~java
package demo;

public final class ProbeTarget {
    public static String message() {
        return "ok";
    }
}
~~~

### 6.3. `src/demo/ProbeMain.java`

~~~java
package demo;

public final class ProbeMain {
    public static void main(String[] args) {
        System.out.println("result=" + ProbeTarget.message());
    }
}
~~~

### 6.4. Two manifest files

`PREFIX-ON.MF`:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.PrefixAgent
Can-Set-Native-Method-Prefix: true

~~~

`PREFIX-OFF.MF`:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.PrefixAgent
Can-Set-Native-Method-Prefix: false

~~~

Keep the **trailing blank line**. Besides `false`, **omitting** the attribute altogether in the manifest also makes it default to `false`.

### 6.5. Compile, package JARs, and run

From `prefix-api-lab`, create the `out` directory. With Bash/Git Bash:

~~~bash
mkdir -p out
~~~

With Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
~~~

Run on JDK 17+:

~~~bash
javac --release 17 -d out src/demo/PrefixAgent.java src/demo/ProbeTarget.java src/demo/ProbeMain.java

jar --create --file agent-on.jar --manifest PREFIX-ON.MF -C out demo/PrefixAgent.class -C out 'demo/PrefixAgent$1.class' -C out 'demo/PrefixAgent$2.class'
jar --create --file agent-off.jar --manifest PREFIX-OFF.MF -C out demo/PrefixAgent.class -C out 'demo/PrefixAgent$1.class' -C out 'demo/PrefixAgent$2.class'
jar --create --file app.jar -C out demo/ProbeMain.class -C out demo/ProbeTarget.class

java -javaagent:agent-on.jar -cp app.jar demo.ProbeMain
java -javaagent:agent-off.jar -cp app.jar demo.ProbeMain
~~~

Note that `PrefixAgent$1.class` and `PrefixAgent$2.class` are compiler-generated anonymous classes; **both must be included in the agent JAR**. Single quotes around the names in the `jar` command prevent Bash/PowerShell from interpreting `$1`, `$2` as variables. You can replace this with a command that packages all agent class files when the project structure is separated accordingly.

**Verified stdout on JDK 24, compiled with `--release 17`:**

When using `agent-on.jar`:

~~~text
supported=true
prefix=registered
unregistered=IllegalArgumentException
nullTransformer=NullPointerException
transformTarget=true
result=ok
~~~

When using `agent-off.jar`:

~~~text
supported=false
prefix=unsupported
transformTarget=true
result=ok
~~~

Reading the output:

- `supported=true` shows the capability was requested by the manifest **and** granted by the JVM.
- `prefix=registered` does not mean `ProbeTarget` was instrumented; because the transformer `return null`, `message()` still returns `"ok"`.
- `IllegalArgumentException` and `NullPointerException` prove the preconditions on transformer registration and parameter validity.
- `supported=false` does not prevent `addTransformer(..., false)` from working for **Java class definition**, it only prevents setting a prefix for JNI resolution.

**Do not run extra `prefix=""` or `prefix=null` variants in the main lab**, because they disable retry for that transformer. If you intentionally change the prefix when a class already has prefixed native methods, you must consider the timing of JNI resolution: binding can happen later than class loading.

## 7. Lab 2: end-to-end JNI with a pre-existing wrapper

This lab **includes both Java + C** and demonstrates **real native resolution fallback**. To focus on `setNativeMethodPrefix`, we **pre-compile** the Java wrapper and the prefixed native method; a no-op transformer only provides the registration to attach the prefix to. In a production agent, the equivalent wrapper must be **generated by a class-file transformer during initial class definition**. Do not confuse this prewrapped example with a transformer capable of writing bytecode itself.

**Tested environment:** OpenJDK 21 on Linux and GCC; Java source compiled with `--release 17`. No Gradle/Maven or external Java libraries needed. If running on Windows/macOS, you must have a C compiler and use the OS-specific native library build method; see the end of this section.

Structure:

~~~text
native-prefix-jni/
├── src/demo/
│   ├── PrefixAgent.java
│   ├── NativeTarget.java
│   └── NativeMain.java
├── native.c
├── ON.MF
├── OFF.MF
└── out/
~~~

### 7.1. `src/demo/PrefixAgent.java` (agent that attaches the prefix)

~~~java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;

public final class PrefixAgent {
    public static void premain(String args, Instrumentation inst) {
        System.out.println("supported="
                + inst.isNativeMethodPrefixSupported());

        ClassFileTransformer transformer =
                new ClassFileTransformer() {};
        inst.addTransformer(transformer, false);

        if (inst.isNativeMethodPrefixSupported()) {
            inst.setNativeMethodPrefix(transformer, "$AgentWrapped$");
            System.out.println("prefix=registered");
        } else {
            System.out.println("prefix=unsupported");
        }
    }
}
~~~

Here `ClassFileTransformer` uses the **default/no-op implementation**, solely so the JVM has a registered transformer corresponding to the prefix. The `NativeTarget` Java source below **already contains the wrapper**; the example is meant to isolate specifically the **JNI link resolution** part.

### 7.2. `src/demo/NativeTarget.java`

~~~java
package demo;

public final class NativeTarget {
    public int add(int x) {
        System.out.println("wrapper-enter");
        int result = $AgentWrapped$add(x);
        System.out.println("wrapper-exit");
        return result;
    }

    private native int $AgentWrapped$add(int x);
}
~~~

**The `add(int)` method is non-native**, with bytecode that can be instrumented. **The `$AgentWrapped$add(int)` method is native**, has no bytecode, and requires JNI binding. The exact prefix is `"$AgentWrapped$"`; the remaining original name is `add`.

`javac` accepts `$` in Java identifiers, though such names should not be used arbitrarily in application APIs. In a real class that initially only has `native int add(int)`, the transformer will be responsible for producing a class with a structure equivalent to the snippet above.

### 7.3. `src/demo/NativeMain.java`

~~~java
package demo;

public final class NativeMain {
    public static void main(String[] args) {
        System.load(args[0]);

        try {
            System.out.println(
                    "value=" + new NativeTarget().add(7));
        } catch (UnsatisfiedLinkError error) {
            System.out.println(
                    "nativeResolution="
                            + error.getClass().getSimpleName());
        }
    }
}
~~~

`System.load` takes the **absolute path** of the native library. `UnsatisfiedLinkError` is caught intentionally to compare the two configurations; production code should not use this pattern to mask JNI errors. If `System.load` itself fails (missing file, wrong architecture), the error occurs **before the `try` block**; fix the path/library instead of concluding that native prefix does not work.

### 7.4. `native.c` — JNI implementation carrying only the **original name**

~~~c
#include <jni.h>

JNIEXPORT jint JNICALL
Java_demo_NativeTarget_add(JNIEnv* env, jobject self, jint x) {
    return x + 5;
}
~~~

Notable detail: the library **does not export** a function named for `$AgentWrapped$add`, and only exports the JNI name of the original method **`add`**. That is the premise for testing the fallback.

The JNI function receives `JNIEnv*`, the instance's `jobject` (because the Java method is not `static`), and `jint x`. `JNIEXPORT`/`JNICALL` are macros from `jni.h`. Here the native implementation always returns `x+5`, so `add(7)` produces `12`.

This lab **does not use `RegisterNatives`**, and instead tests **automatic JNI symbol resolution**. The `RegisterNatives` part was explained in section 5, without pretending it is executed in the demo.

### 7.5. `ON.MF` and `OFF.MF`

`ON.MF`:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.PrefixAgent
Can-Set-Native-Method-Prefix: true

~~~

`OFF.MF`:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.PrefixAgent
Can-Set-Native-Method-Prefix: false

~~~

### 7.6. Full commands on Linux (verified)

Create `out`:

~~~bash
mkdir -p out
~~~

Compile Java targeting Java 17, package agent and application **into separate JARs**:

~~~bash
javac --release 17 -d out src/demo/PrefixAgent.java src/demo/NativeTarget.java src/demo/NativeMain.java

jar --create --file agent-on.jar --manifest ON.MF -C out demo/PrefixAgent.class -C out 'demo/PrefixAgent$1.class'
jar --create --file agent-off.jar --manifest OFF.MF -C out demo/PrefixAgent.class -C out 'demo/PrefixAgent$1.class'
jar --create --file app.jar -C out demo/NativeTarget.class -C out demo/NativeMain.class
~~~

**Compile the native library with GCC**, using the JNI headers of the current JDK:

~~~bash
JDK_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"

gcc -shared -fPIC \
    -I"$JDK_HOME/include" \
    -I"$JDK_HOME/include/linux" \
    native.c -o libnativeprefixdemo.so
~~~

In custom JDK environments, verify that `JDK_HOME` points to the right `jni.h` and `jni_md.h` headers. The native output file on Linux is `.so`. The trailing `\` in Bash only allows line continuation; GCC can be written on a single line.

Run **in two separate JVMs**:

~~~bash
java -javaagent:agent-on.jar -cp app.jar demo.NativeMain "$PWD/libnativeprefixdemo.so"
java -javaagent:agent-off.jar -cp app.jar demo.NativeMain "$PWD/libnativeprefixdemo.so"
~~~

The path `"$PWD/libnativeprefixdemo.so"` is the **absolute path** required by `System.load`.

**Verified stdout on OpenJDK 21 + GCC:**

Manifest **ON**:

~~~text
supported=true
prefix=registered
wrapper-enter
wrapper-exit
value=12
~~~

Manifest **OFF**:

~~~text
supported=false
prefix=unsupported
wrapper-enter
nativeResolution=UnsatisfiedLinkError
~~~

### 7.7. Why does the output confirm the mechanism?

In both JVMs, the `NativeTarget` class files and the native library are **identical**. Only the **agent's** manifest differs.

- **ON:** The Java native method named `$AgentWrapped$add` is called. JNI lookup by the prefixed name finds nothing. The JVM **tries stripping the prefix per the registered configuration**, finds the symbol `Java_demo_NativeTarget_add`, returns `12`, and then the wrapper prints `wrapper-exit`.
- **OFF:** JNI lookup has no prefix fallback; the same native method `$AgentWrapped$add` **cannot find a symbol**. The JVM throws `UnsatisfiedLinkError` before the wrapper can print `wrapper-exit`.
- **There is no classfile rewrite step in this example**: both the Java wrapper and the prefixed native method are already present in the source. The lab isolates the **native method prefix resolution** capability; it does not prove that the agent generated the wrapper itself.
- If the JVM does not support the capability even with the manifest ON, the result will follow the unsupported branch. Do not assume every JVM distribution will yield a successful ON output.
- The native library is only loaded into the JVM by `System.load`. A prefix does not make a library appear if `System.load` is missing.

**On Windows**, the extension is typically `.dll`, requiring JNI headers under `include/win32` and a compatible C compiler toolchain (MSVC/MinGW). **On macOS**, the extension is typically `.dylib` and compile/link flags differ. The Linux commands above **must not be used verbatim** on those two operating systems; compile the library for the proper target OS/architecture first and pass the corresponding absolute path to `NativeMain`.

## 8. Debugging Java classes and JNI symbols in the experiment

### 8.1. Inspecting the actual methods in the class file

~~~bash
javap -p -s out/demo/NativeTarget.class
~~~

You will see the **Java wrapper method** `add(int)` and the **native method** `$AgentWrapped$add(int)`; both take `int` and return `int`, so the JVM descriptor is `(I)I`.

The `native` flag belongs to the **second method**. You can use `javap -v` to inspect `ACC_NATIVE` and confirm that method has no `Code` attribute.

### 8.2. Inspecting symbols exported by the Linux library

~~~bash
nm -D libnativeprefixdemo.so | grep Java_demo_NativeTarget_add
~~~

If the `nm` tool is available, the result finds the JNI symbol of the **original name**, not `$AgentWrapped$add`. `nm` is not required to run the demo; this is only a helper step for debugging native symbol exports.

### 8.3. Ways the experiment can fail

- `ClassNotFoundException` for `demo.NativeMain`: check `app.jar` on `-cp`.
- `NoClassDefFoundError` for `demo.PrefixAgent$1`: forgot to package the anonymous class into the **agent JAR**.
- `UnsatisfiedLinkError: Can't load library`: incorrect absolute path, missing `.so`/`.dll`, or mismatched architecture.
- `UnsatisfiedLinkError` even with manifest enabled: prefix differs from method name, library lacks the symbol, native method was not wrapped properly, JVM does not support the capability, or lookup by class/signature does not match.
- `NoSuchMethodError` in the wrapper: class file and helper methods are incompatible; check names/descriptors and whether the transformation broke the schema.
- JVM verifier rejects the transformed class: class-file bytes were generated incorrectly. This case is **different** from native-method resolution failure.

In real applications, a `native` method may use multiple JNI export names due to overloading and signatures. Do not treat a short symbol name like `Java_demo_NativeTarget_add` as the complete formula for **all** signatures; follow the JNI Name Mangling Spec and check overloads when writing native libraries.

## 9. From the "prewrapped" example to a real `ClassFileTransformer`

A production transformer typically has the flow:

~~~text
Original class not yet defined by the JVM
  |
  v
ClassFileTransformer.transform(...)
  |
  +-- Filter target class + native method by name/descriptor/flags
  |
  +-- Replace "native int add(int)" with Java wrapper "int add(int)"
  |      - attach valid Code attribute
  |      - add measurement / logging
  |      - call "$AgentWrapped$add"
  |
  +-- Create native method "$AgentWrapped$add(int)"
  |      - preserve valid descriptor and linkage
  |      - has ACC_NATIVE and NO Code
  |
  +-- return new class file byte[]
  |
  v
JVM defines the transformed class
  |
  v
Java call add() → wrapper → "$AgentWrapped$add" → JNI fallback
~~~

This is a **conceptual workflow**, not a complete `transform` implementation. Generating bytes can be done with:

- **ASM/Byte Buddy** on supported target JDKs, especially when the agent needs to run on Java 17.
- **Java Class-File API** (`java.lang.classfile`) standardized in **JDK 24**; to use this API in an agent, **the JVM running the agent must have the corresponding API**—you cannot compile with JDK 24 and run directly on Java 17.
- A class-file generation toolkit capable of producing Code, exception tables, and frames valid for the target class version.

**Minimum requirements for the transformer:**

1. Select the right class from `className`, loader/module, avoiding instrumenting bootstrap/JDK classes or the agent itself unless specifically designed for it.
2. Select the right native method by **name and full method descriptor**, not by name alone.
3. Detect **whether it has already been wrapped**; do not add duplicate wrapper/native methods with the same name if the transformer can run again.
4. Preserve the semantics of **static vs instance**, method parameters, return type, required access flags, and exceptions.
5. Ensure the wrapper preserves/returns the result or throws exceptions according to business logic. Instrumentation in `finally` must not let the recorder itself throw an error that masks a JNI exception.
6. Do not change the public method API that callers use; the wrapper should keep the original name and signature.
7. Do not create prefix names that easily collide. If multiple agents/wrappers participate, handle ordering and classfile schema appropriately.
8. Register the prefix **before native methods can be linked**, and keep it long enough because JNI resolution may happen late.
9. Do not rely on `redefineClasses` to add new methods to an **already-loaded** class. Class schema restrictions make creating wrappers at **initial class load** generally more appropriate.
10. Check `isNativeMethodPrefixSupported()` and have a useful fallback if the capability does not exist.

## 10. Multiple agents and multiple wrapper layers

Each `ClassFileTransformer` can create a different wrapper, so **each transformer needs its own prefix**. Per the specification:

~~~text
foo
  → $trans1_foo
  → $trans2_$trans1_foo
  → $trans3_$trans2_$trans1_foo
~~~

In practice, wrappers can be applied in transformation order; a wrapper layer only appears when that transformer **actually wraps** the method. For example, if the second transformer does not modify `foo`, the prefix chain may only consist of `$trans3_$trans1_foo`.

The JVM considers prefixes in an order matching the transformation chain, and **does not automatically assume an intermediate prefix exists**: the specification uses the existence of the corresponding non-native wrapper to deduce the correct prefix chain.

**Why not share a prefix?** When two transformers use the same prefix and have methods with the same name, the final name can become ambiguous, JNI lookup can match the wrong method, or diagnosis becomes difficult. Each agent should have a clear prefix namespace, while checking method names before/after transformation.

**Why not clear the prefix too early?** JVM TI explicitly states that native binding can be delayed arbitrarily. The prefix must be retained **as long as there are still prefixed native methods that need to be linked**. Disabling the prefix with `null`/`""` while transformed classes still use prefixed native methods can cause subsequent native resolution attempts to fail.

The content above is **Java Instrumentation/JVMTI method prefixing**, not **`MethodHandles.Lookup`**, nor a feature for renaming methods in Java source code.

## 11. `setNativeMethodPrefix` does not replace other JVMTI native events

At the native agent layer, JVMTI also has:

- **`SetNativeMethodPrefix`**: the same idea of prefix-based **JNI resolution fallback**, requiring the `can_set_native_method_prefix` capability.
- **`SetNativeMethodPrefixes`**: a JVM TI environment, such as a meta-agent, can provide **a list of prefixes** for multiple independent transformations.
- **`NativeMethodBind` event**: observes when the JVM binds a native method to a native function address and can redirect the binding under appropriate JVMTI conditions; this is a **different mechanism** from creating a Java wrapper and setting a prefix.
- **`RegisterNatives`**: a JNI function that native code uses to register implementations, not a Java `Instrumentation` API.

Do not conflate them:

| Goal | API/mechanism |
|---|---|
| Allow a new native wrapper to link to an old-named JNI implementation | `setNativeMethodPrefix` |
| Insert Java bytecode to record latency before/after a JNI call | `ClassFileTransformer` building a Java wrapper |
| Monitor native binding in a JVMTI native agent | `NativeMethodBind` |
| Explicitly bind a JNI function pointer from a native library | `RegisterNatives` |
| Transform bytecode of non-native Java methods | Normal class-file transformation |

The fact that JNI libraries have their own lookup mechanisms, `JNI_OnLoad`, `RegisterNatives`, class loader visibility, and module access makes native instrumentation more complex than inserting a `System.nanoTime()` into a regular Java method. When you need to inspect **inside C/C++ functions**, a Java wrapper **does not provide** visibility into individual native instructions; appropriate profilers/native tooling are needed.

## 12. Error handling in the Java API

The `setNativeMethodPrefix` contract has three main exceptions:

| Exception | When | How to handle |
|---|---|---|
| `UnsupportedOperationException` | The JVM/agent **does not support** the capability (`isNativeMethodPrefixSupported() == false`) | Check `Can-Set-Native-Method-Prefix` in the **actual agent JAR**; query at runtime; do not force calling the API |
| `IllegalArgumentException` | `transformer` **has not been registered** via `addTransformer` | Keep the exact registered instance; do not create a new instance when setting the prefix |
| `NullPointerException` | `transformer == null` | Ensure a valid object, initialized before calling |

`prefix == null` is **not** an error equivalent to `transformer == null`: a null prefix is used to **disable retry** for that transformer. You can also pass `""` to disable prefix-based retry.

**Defensive coding in `premain`:**

~~~java
ClassFileTransformer transformer = createTransformer();

inst.addTransformer(transformer, false);

if (inst.isNativeMethodPrefixSupported()) {
    inst.setNativeMethodPrefix(transformer, "$MyAgentNative$");
} else {
    // Do not create prefixed native wrappers if there is no compatible
    // JNI binding strategy; native instrumentation can be skipped.
}
~~~

This is a **fragment**, requiring a `createTransformer()` method defined by the agent. Notably: if the JVM lacks the capability, **do not still create prefixed native methods and hope they will link**. Choose a clear fallback, such as not instrumenting native methods, or using another measurement approach that does not require renaming.

When an agent runs with `-javaagent`, an uncaught exception in `premain` can cause the JVM to **abort startup**. Therefore, capability validation and transformer registration must happen before risky changes.

## 13. Independent JNI conditions to verify

**Having a valid prefix is not enough for a native method to run.** A JNI call also depends on:

1. **Class loader/library association:** the native library must be loaded in the appropriate context; multiple loaders/plugins have their own rules for loading native libraries.
2. **Matching architecture:** x86-64/ARM64, 32/64-bit, and toolchain ABI must match the JVM.
3. **Correct symbol name:** JNI mangling follows class/package/method names and descriptors when overloaded. Prefix lookup does not ignore the remaining parts.
4. **Correct method kind:** `static` native uses `jclass` instead of `jobject` as the second parameter of the JNI function; instance native uses `jobject`.
5. **Correct method descriptor:** `int` is `I`, `long` is `J`, arrays/objects have their own encodings. The wrapper and native method must match.
6. **Correct timing:** the method must not have already been bound incorrectly or failed resolution before the prefix is registered.
7. **Valid class-file bytes:** the transformed class must pass the verifier and not violate module/classloader constraints.
8. **Proper lifecycle:** the prefix remains active for prefixed methods that still need to be resolved; do not disable it early.
9. **Multi-agent ordering:** prefixes are applied along the transformation chain and may interact with other transformers.
10. **Proper error-handling strategy:** `UnsatisfiedLinkError` is a `LinkageError`, not an `Exception`; `catch (Exception)` will not catch it.

Use `javap -p -s -v` and native symbol tools (`nm`, `objdump`, `dumpbin`) to inspect the actual bytes and symbols before concluding that an error is caused by the capability.

## 14. Common misconceptions

| Claim | True/False | Explanation |
|---|---|---|
| "Manifest `true` means the JVM definitely supports it" | **False** | The capability also depends on the JVM |
| "No need for `addTransformer`, you can set the prefix first" | **False** | The transformer must already be registered |
| "`setNativeMethodPrefix` renames methods in the class file itself" | **False** | It only modifies resolution retry; class rewriting is separate |
| "Prefix acts as an unconditional alias" | **False** | It is only considered if normal resolution fails |
| "Native methods have a `Code` body for inserting logging" | **False** | A non-native Java wrapper is needed |
| "A null prefix causes NullPointerException" | **False** | A null/empty prefix disables prefix retry; a null transformer is the error |
| "With a prefix, no native library is needed" | **False** | The library and native implementation must still exist |
| "Enabling prefix automatically enables retransformation" | **False** | Capabilities are independent |
| "You can arbitrarily add new wrappers when retransforming an already-loaded class" | **False** | Schema/JVMTI restrictions apply; wrapping is usually done at initial definition |
| "A transformer must share a prefix with other agents" | **False** | Each transformer needs its own prefix to avoid wrapper layer confusion |
| "Prefix only affects automatic JNI symbol lookup" | **False** | The API also specifies `RegisterNatives` fallback |
| "Without a native C compiler you can still test real JNI fallback?" | **Not with this demo** | The Java-only probe only tests capability; the JNI demo requires a library with a real symbol |
| "Disabling the prefix right after class load is safe" | **Not guaranteed** | Native resolution can occur later |
| "`-javaagent` placed after the main class works the same as before it?" | **False** | `-javaagent` is a JVM option and must precede the main class/`-jar` per launcher syntax |

## 15. Checklist for real agent implementation

1. **Clarify the goal:** measure timing at the JNI boundary or actually need to observe inside the native implementation? Prefix + Java wrapper only surrounds the **call boundary**.
2. **Request the capability** with manifest `Can-Set-Native-Method-Prefix: true`.
3. **Use the right entrypoint**: `premain` for a startup agent, or `agentmain` when the environment supports appropriate dynamic loading.
4. **Check `isNativeMethodPrefixSupported()`** before deciding to create prefixed native methods.
5. **Register `ClassFileTransformer` first**, keeping the exact instance.
6. **Call `setNativeMethodPrefix` with a unique and stable prefix**, before transformed native methods are bound.
7. **Transform only the targeted classes/methods**, especially with system or core JNI classes that risk affecting the entire JVM.
8. **At initial class definition**: create the non-native wrapper and prefixed native method with the right names/descriptors/modifiers, and build valid bytes.
9. **Preserve original method semantics**: return value, exceptions, synchronization, native transitions, class loading, and thread safety.
10. **Test JNI resolution** with a real native library, both automatic symbol lookup and `RegisterNatives` if the product requires both paths.
11. **Test the capability-OFF path**: the agent skips incompatible changes, and the application still runs or shows a clear message.
12. **Test multiple prefixes/agents**: avoid collisions and double instrumentation; verify chain ordering.
13. **Do not reset the prefix early**: the JVM may resolve native implementations later than when the class is defined.
14. **Measure overhead and stability**: Java wrappers have cost and can affect JIT, class loading, and timing.
15. **Test on production JVM/OS**: JNI binary format, JVM TI capability, class-file version, and module boundaries must be compatible.

## 16. Self-check

1. **Does `native int add(int)` have `Code` for a transformer to insert opcodes into?** No.
2. **To measure native call timing from Java, what should be created?** A non-native Java wrapper method that calls a renamed native method.
3. **What is the default value of `Can-Set-Native-Method-Prefix`?** `false`.
4. **Does manifest `true` force `isNativeMethodPrefixSupported()` to return `true`?** No; it also depends on the JVM.
5. **Does `setNativeMethodPrefix` create the wrapper itself?** No; it only adjusts native resolution fallback.
6. **Is setting the prefix before calling `addTransformer` valid?** No; it throws `IllegalArgumentException`.
7. **What happens if `transformer == null`?** `NullPointerException`.
8. **What happens if `prefix == null`?** Disables native resolution retry for that transformer.
9. **If automatic JNI lookup of a prefixed native method fails, what does the JVM try?** It considers stripping the prefix to find the original-named implementation.
10. **With JNI `RegisterNatives` registering the original name, what can the JVM try?** Prepending the prefix to match the prefixed native method in the class.
11. **Why does the JNI demo section use a C function named `Java_demo_NativeTarget_add`?** To test that the prefixed Java native method is linked to the **original-named** implementation via fallback.
12. **Why does the OFF manifest of the JNI demo produce `UnsatisfiedLinkError` even though `.so` is loaded?** There is no prefix fallback; the prefixed native method has no matching JNI symbol.
13. **Does the JNI experiment perform classfile transformation?** No. The source already contains the wrapper/prefixed native method; the transformer is intentionally a no-op to isolate resolution.
14. **Does enabling native prefix allow arbitrarily adding methods when retransforming an already-loaded class?** No; JVM TI/class schema restrictions still apply.
15. **Why should multiple transformers use separate prefixes?** So the JVM can find the right consecutive wrapper layers, avoiding name collisions and resolver confusion.
16. **Why not disable the prefix right after class load?** JNI binding can be deferred until a later call.
17. **Does a prefix help with linking if `.dll/.so` does not exist?** No; the library and native function must still exist.
18. **To handle native binding from a JVM TI native agent, what other mechanism exists?** The `NativeMethodBind` event, which is different from Java wrapper prefixing.

### Official documentation

- [Java SE 21 — `Instrumentation`: `isNativeMethodPrefixSupported` and `setNativeMethodPrefix`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): capability conditions, registration, two types of JNI resolution fallback, multiple prefixes, and exceptions.
- [Java SE 21 — `java.lang.instrument` package specification](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent manifest and `Can-Set-Native-Method-Prefix`.
- [Java SE 21 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): bytecode transformation callback and transformer ordering.
- [Java SE 21 — JVM Tool Interface: Set Native Method Prefix / Prefixes](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html): `can_set_native_method_prefix` capability, automatic resolution, `RegisterNatives`, multiple wrapper layers, and lifetime.
- [JNI Specification — Design Overview](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html): JNI name mangling, native method lookup, and libraries.
- [JNI Specification — Functions: `RegisterNatives`](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html): explicit JNI method registration.
- [Java Virtual Machine Specification, §4.6 Methods](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.6): method flags and `Code` attribute.

**Conclusion:** `Can-Set-Native-Method-Prefix` is the **agent's request**, `isNativeMethodPrefixSupported()` is the **capability check**, `ClassFileTransformer` is **where the Java wrapper/prefixed native method is created**, and `setNativeMethodPrefix` helps the JVM **find the original-named JNI implementation when normal native resolution fails**. Distinguishing these four roles will prevent most native linking errors in Java instrumentation.