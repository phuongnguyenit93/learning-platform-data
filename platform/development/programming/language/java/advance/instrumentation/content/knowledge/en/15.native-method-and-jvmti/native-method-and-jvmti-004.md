# Per-Transformer Prefix and the Native Resolution Retry Mechanism

A Java agent can insert bytecode before and after many Java methods. However, a method declared `native` **does not have a Java `Code` attribute** into which instructions can be inserted in the body like an ordinary method. To observe native calls, a transformer typically creates a **non-native Java wrapper**, then renames the native declaration to a name with a **transformer-specific prefix**. The next problem is: the original JNI library only knows the old native name, so how does the JVM find the native implementation again?

`Instrumentation.setNativeMethodPrefix(ClassFileTransformer transformer, String prefix)` answers that exact problem. The API changes **the retry mechanism when linking a native method fails**, allowing the JVM to consider the prefixes that the agent has registered. **Each transformer has its own prefix** so that multiple wrapper layers can stack while still finding the original JNI implementation.

This lesson in the **Native and JVM TI** group explains:

1. The differences between a `native` method, a Java wrapper, a JNI function, and a `ClassFileTransformer`.
2. Why `setNativeMethodPrefix` **does not** automatically instrument a method, rename a JNI symbol, or load a native library.
3. The two resolution paths: **JNI automatic symbol lookup** and **`RegisterNatives`**.
4. The order and conditions for applying prefixes when **multiple transformers** create wrappers, including when a transformer skips a method.
5. How to check capabilities/manifest, choose collision-free prefixes, diagnose `UnsatisfiedLinkError`, and experiment on Java 17+ with real C JNI.

## 1. The problem: native methods have no Java bytecode for inserting probes

Consider the Java class:

```java
public final class NativeMath {
    public static native int sum(int left, int right);
}
```

This is an **illustrative snippet**, not runnable standalone: calling `sum` requires loading a native library containing the corresponding JNI implementation. The source only declares the signature and the `native` modifier, while the execution body resides on the native side (for example in a `.so`, `.dylib`, or `.dll`).

For a Java method with a body, a transformer can turn:

```text
calculate(a, b):
    return a + b
```

into:

```text
calculate(a, b):
    Probe.enter()
    try:
        return a + b
    finally:
        Probe.exit()
```

However, the `native int sum(...)` method does not contain such a block of Java bytecode. The JVM can invoke the native implementation directly according to JNI binding rules; there is nowhere for a transformer to insert an `invokestatic Probe.enter` into **the Java body of the native declaration itself**.

### 1.1. The wrapper solution: creating a Java method with the same name

A carefully designed class file transformation can turn:

```java
// Class state before transformation:
public static native int sum(int left, int right);
```

into equivalent logic:

```java
// Source diagram after the transformer has modified the class file:
public static int sum(int left, int right) {
    Probe.enter();
    try {
        return agent_sum(left, right);
    } finally {
        Probe.exit();
    }
}

private static native int agent_sum(int left, int right);
```

**The snippet above is a source simulation, not standalone runnable code:** `Probe` is not declared and generating wrappers requires a class-byte manipulation library. The goal is to recognize the two methods with distinct roles:

- `sum` becomes a **non-native Java method** for inserting probes.
- `agent_sum` is the **remaining native declaration** used to invoke the original JNI implementation.
- The original native implementation can still carry the JNI name for `sum`, such as `Java_NativeMath_sum`. Operators should not be forced to recompile the native library just to rename the function.
- There needs to be a **capability to retry resolving the name `agent_sum` using the `agent_` prefix**, so that the JVM eventually finds the `sum` implementation.

`setNativeMethodPrefix` provides the **resolution retry** part. Meanwhile, the transformer must create valid wrappers and native declarations itself, preserving descriptors, access rules, and proper semantics. Simply calling the prefix-setting API does not create any wrappers.

### 1.2. Distinguishing the names

| Name | Example | Owned by | Role |
|---|---|---|---|
| Pre-transformation Java API name | `sum(int,int)` | Original class | Application call sites invoke this |
| Post-transformation Java wrapper name | `sum(int,int)` | Transformer generates body | Inserts tracing/profiling |
| Post-transformation native declaration name | `agent_sum(int,int)` | Transformer renames/declares | Gateway to call the old native method |
| Transformer prefix | `agent_` | `setNativeMethodPrefix(t,"agent_")` | Rule for the JVM to retry when normal JNI resolution fails |
| Original JNI implementation name | `Java_NativeMath_sum` | Native library | C/JNI symbol executing the computation |
| Native library file | `libnative_math.so` or OS equivalent | Build/deployment | Contains the symbol to resolve |

**Do not confuse** the `agent_sum` name in the class file with a C symbol name that must be renamed to match. It is precisely the retry mechanism that allows using the C/JNI implementation with the original name.

## 2. Prerequisites for enabling a prefix

The API has two parts:

```java
boolean isNativeMethodPrefixSupported();

void setNativeMethodPrefix(
        java.lang.instrument.ClassFileTransformer transformer,
        String prefix);
```

These methods belong to `java.lang.instrument.Instrumentation`, which is the object the agent receives via `premain(String,Instrumentation)` or `agentmain(String,Instrumentation)` if the JVM supports dynamic loading.

### 2.1. The capability is optional; the manifest must request it

`isNativeMethodPrefixSupported()` returns `true` when **the JVM supports it** and the agent has requested the appropriate capability. In the agent JAR's manifest:

```text
Manifest-Version: 1.0
Premain-Class: example.agent.PrefixAgent
Can-Set-Native-Method-Prefix: true

```

This is an **illustrative manifest template** for a class `example.agent.PrefixAgent` that is not defined in this section. In the complete runnable example in section 7, the manifest uses the actual class `PrefixAgent`.

- `Can-Set-Native-Method-Prefix: true` **requests** the JVM to grant the capability; it does not force every JVM implementation to support it.
- If the attribute is not declared or is not `true`, you cannot assume the native prefix capability is enabled.
- `isNativeMethodPrefixSupported()` is invariant within a single JVM instantiation by contract.
- `Can-Retransform-Classes` and `Can-Redefine-Classes` are **separate capabilities** and do not automatically enable native prefixes.
- A working JNI library **does not prove** that the JVM/agent allows setting prefixes.

**Proper precheck:**

```java
// Snippet inside an agent; inst was received from premain/agentmain.
if (!inst.isNativeMethodPrefixSupported()) {
    System.out.println("SKIPPED: NATIVE_PREFIX_UNSUPPORTED");
    return;
}
```

If unsupported, **do not** try calling `setNativeMethodPrefix`, swallow `UnsupportedOperationException`, and report "native instrumentation active". You may fall back to another measurement point per policy, but Java wrapper instrumentation and JNI binding for this method remain unresolved.

### 2.2. Register the transformer before assigning a prefix

Valid order:

```java
ClassFileTransformer transformer = new MyNativeWrapperTransformer();

inst.addTransformer(transformer);
inst.setNativeMethodPrefix(transformer, "agent_");
```

**This is illustrative code, not standalone**: `MyNativeWrapperTransformer` needs to be implemented. The key is **the exact registered transformer object**.

Invalid order:

```java
ClassFileTransformer transformer = new MyNativeWrapperTransformer();
inst.setNativeMethodPrefix(transformer, "agent_"); // Not added yet.
inst.addTransformer(transformer);
```

`setNativeMethodPrefix` may throw `IllegalArgumentException` because the transformer is not registered. Having the same transformer **class name** is not enough: the exact **instance** passed must be the instance registered via `addTransformer`.

You should not register **the same instance** multiple times to try to change ordering. The `addTransformer` Javadoc strongly discourages doing this; designing multiple wrapper layers using transformers with distinct identities and states is easier to debug.

### 2.3. Three API errors to distinguish

| Situation | Result per contract | How to fix |
|---|---|---|
| `transformer == null` | `NullPointerException` | Create and register a valid instance |
| JVM/manifest does not support prefix | `UnsupportedOperationException` | Check `isNativeMethodPrefixSupported`, manifest, and JVM first |
| Transformer not registered | `IllegalArgumentException` | Call `addTransformer(t)` before `setNativeMethodPrefix(t,...)` |
| `null` or empty `""` prefix | **Does not retry** failed native resolution for this transformer | Used to disable prefix retry for a transformer, not an input error |
| Prefix collides with an existing method name | May cause ambiguity/collision or incorrect name concatenation | Use a unique prefix and thoroughly check the class schema |
| Valid prefix but JNI lib is not loaded | Native linking still fails | Check `System.loadLibrary`/path/JNI symbol |

**Key point:** `setNativeMethodPrefix` does not immediately modify bytecode or symbols when called. It adds a rule **for when native method resolution fails later**.

## 3. Mechanism 1: automatic JNI native method resolution

According to the JNI specification, if Java has a native method `sum(int,int)` in class `NativeMath`, the native implementation typically has an exported name derived from the JNI naming rule with the `Java_` prefix, class name, escaped method name, and optionally an escaped signature for overloaded native methods.

Non-overloaded example:

```java
public final class NativeMath {
    public static native int sum(int a, int b);
}
```

Typical JNI implementation:

```c
#include <jni.h>

JNIEXPORT jint JNICALL Java_NativeMath_sum(
        JNIEnv* env, jclass type, jint a, jint b) {
    (void) env;
    (void) type;
    return a + b;
}
```

This is only an **illustrative declaration pair**: you still need to compile the C JNI code into a shared library and load it. The Java method is `static`, so the second argument of the JNI function is `jclass`; for an instance method it is typically `jobject`.

### 3.1. Without a prefix, the JVM searches by the current native name

After the transformer creates `agent_sum`:

```text
Java native declaration:
    agent_sum(int, int)

Automatic symbol the JVM tries first (excluding overload suffix):
    Java_NativeMath_agent_1sum

Native library only has:
    Java_NativeMath_sum

=> Standard lookup finds no corresponding implementation.
```

In JNI escaping, the `_` character in a Java method name is typically escaped as `_1`. Therefore `agent_sum` does not have the simple JNI symbol `Java_NativeMath_agent_sum`; the automatic name per the specification is `Java_NativeMath_agent_1sum`, not counting overloaded signature representation.

### 3.2. With a prefix: retry only after normal lookup fails

`setNativeMethodPrefix(t, "agent_")` instructs the JVM to perform an additional step:

```text
Native declaration invoked: agent_sum(int,int)

Normal automatic attempt:
  method(agent_sum) -> nativeImplementation(agent_sum)
  look up symbol corresponding to name agent_sum
  FAIL (symbol missing)

Retry with transformer's registered prefix:
  strip "agent_" from the implementation name to look up
  method(agent_sum) -> nativeImplementation(sum)
  look up symbol corresponding to original name sum
  FOUND Java_NativeMath_sum
```

This **does not rename the Java native method back to `sum`**. In the class file, the native declaration is still named `agent_sum`; only the chosen native implementation is the symbol of the original name.

**Why must standard lookup run first?** If a native method `agent_sum` actually has an implementation with that exact name, the JVM must not arbitrarily ignore it in favor of the original symbol. Prefix retry is only a **fallback**. This allows a transformer to selectively wrap individual methods instead of altering resolution for all native methods by default.

### 3.3. JNI short/long names and overloading

JNI has rules for looking up **short** native names first and **long** names with encoded parameter signatures when needed. For example, a non-overloaded `sum(int,int)` readily has the symbol `Java_NativeMath_sum`. If a method is overloaded or contains characters requiring escaping, do not guess the symbol by naive string concatenation.

You must check:

- The binary class name of **the class declaring the native method** after transformation.
- Method name, descriptor/parameter types, and static/instance.
- JNI escaping (for example `_` to `_1`).
- Short/long JNI symbol matching and long-name cases with parameter signatures.
- That the library is loaded into **the appropriate loader** for the class declaring the native method.

`setNativeMethodPrefix` **does not fix** a JNI implementation with the wrong signature, ABI calling convention, or a library loaded in a different class loader.

## 4. Mechanism 2: RegisterNatives differs from automatic symbol lookup

A native library can proactively bind a Java method to a C function using `RegisterNatives(JNIEnv*, jclass, JNINativeMethod*, jint)`. Each entry consists of **method name, JNI descriptor, and function pointer**; there does not necessarily have to be an exported `Java_Class_method` symbol as in the automatic case.

Idea:

```c
// Illustrative C snippet, not standalone.
static jint native_sum(JNIEnv* env, jclass clazz, jint a, jint b) {
    return a + b;
}

/* JNINativeMethod entry for the original:
   { "sum", "(II)I", (void*)native_sum }
*/
```

If the post-transformation class only has native `agent_sum(II)I` and `sum` has become a Java wrapper, the initial mapping:

```text
RegisterNatives:
  method("sum", "(II)I") -> function pointer native_sum

Normal mapping attempt:
  find native method "sum" in class
  FAIL because "sum" is now a non-native Java method

Retry with registered prefix "agent_":
  find native method "agent_sum", descriptor "(II)I"
  FOUND
  bind agent_sum -> native_sum
```

**Reversal that is easy to confuse:**

| Resolution path | Input from native library | During retry, where is the prefix applied? |
|---|---|---|
| **Automatic JNI lookup** | JVM looks up symbol for Java native declaration `agent_sum` | **Strip** the prefix from **the implementation name to look up**, to find implementation `sum` |
| **`RegisterNatives`** | Native code registers method name `sum` + descriptor + pointer | **Try prepending** the prefix to **the Java native method name** being looked up, to match `agent_sum` |

The Instrumentation Javadoc describes two separate mechanisms. Do not conflate `RegisterNatives` with "Java automatically finding an exported `Java_...` symbol"; it is a direct function pointer mapping.

### 4.1. Why is RegisterNatives error-prone when instrumented?

- Native code registers a method name, but the transformer has renamed the native declaration to a prefixed name.
- The descriptor was changed incompatibly, or the method is no longer native under the new schema.
- The prefix was not registered on **the exact transformer instance**.
- The class loader of the JNI class differs from the loader of the class you transformed.
- The native library calls `RegisterNatives` before the transformer/prefix is set up, or with a different class than expected.
- Another library/agent re-registered the native implementation, causing behavioral contention.

Nor should every `RegisterNatives` error be blamed on the prefix. Check `JNIEnv->ExceptionCheck`, JNI return codes, names/descriptors, and the actual loaded classes; the risk of `RegisterNatives` interfering with native logic is significant.

## 5. Why must each transformer have its own prefix?

An agent might have only one transformer, but a JVM often has multiple agents/transformers. For example, transformer A measures latency, transformer B counts invocations, and transformer C adds tracing. Each transformer is allowed to create a **Java wrapper around an existing native declaration**.

The `setNativeMethodPrefix` Javadoc explicitly states: because multiple `ClassFileTransformer`s can modify bytes in order, **each transformer needs its own prefix**. If three transformers all wrap `foo`, the final native name may be:

```text
After A:  a_foo
After B:  b_a_foo
After C:  c_b_a_foo
```

With the Java wrappers:

```text
foo()         [Java wrapper A]
   |
   v
a_foo()       [Java wrapper B]
   |
   v
b_a_foo()     [Java wrapper C]
   |
   v
c_b_a_foo()   [final native declaration]
   |
   v
JNI implementation foo()
```

This is **the model after three transformers generate class bytes**, not automatic output from `setNativeMethodPrefix`. The wrappers are Java methods with `Code`; the innermost method remains `native`. After retries using the registered prefixes, the JVM can link to the original native implementation.

### 5.1. Name concatenation order

If transformers in the same group are applied in the order **A -> B -> C**, each transformer places its prefix **outside** the existing prefixes:

```text
foo
A: a_foo
B: b_a_foo
C: c_b_a_foo
```

Do not reverse it to `a_b_c_foo` just because A was registered first. At the end of the pipeline, the newest prefix typically sits **on the left** of the native name. This is a direct interpretation of the Javadoc's multi-transformer example.

In `ClassFileTransformer`, remember that the JVM divides callbacks into groups:

1. Non-retransformation-capable Java transformers (`canRetransform=false`).
2. Non-retransformation-capable native/JVMTI transformers.
3. Retransformation-capable Java transformers (`canRetransform=true`).
4. Retransformation-capable native/JVMTI transformers.

Only **within each group** does registration order apply. Therefore, before deducing prefix order, you must know the **actual class transformation** order; do not just look at isolated `addTransformer` calls across multiple groups.

### 5.2. When B does not wrap: do not assume B's prefix must be applied

If A and C wrap, but B does not wrap `foo`:

```text
After A:  a_foo (native) + foo (Java wrapper)
After B:  native name unchanged, no wrapper added
After C:  c_a_foo (native) + a_foo (Java wrapper)

There is no b_a_foo or b_foo wrapper.
```

According to the Javadoc, **an intermediate prefix is only applied if the corresponding non-native wrapper exists**. Therefore the result can be `c_a_foo`, not `c_b_a_foo`. Do not design native resolution by blindly "stripping three prefixes from a list" without considering the wrapper structure that the real transformers actually created.

The Javadoc gives an example where the second transformer's wrapper is absent, yet the first transformer's prefix is still considered because **its non-native wrapper is present**. This is why **one prefix per transformer** helps the JVM deduce the right chain across selectively skipped wrapper layers.

### 5.3. Prefix collisions can break distinguishability

There is no prefix namespace automatically allocated by the JVM across all agents. Choosing something too common like `wrapped_` or `agent_` may collide with an existing method or another agent's prefix.

A production prefix pattern might look like:

```text
$$_com_acme_metrics_native_$
$$_com_acme_trace_native_$
```

This is an **example naming convention**, not a standard name required by Java. In JVM bytecode, the `$` character is allowed in normal method names but has JNI escaping rules; when using a prefix, generate bytes and match symbols per the specification rather than manually concatenating unescaped JNI names.

Choose a stable prefix per agent/transformer that is sufficiently distinct, and check the class schema before adding methods. You must account for overloads, bridge methods, synthetic names, and other transformers during integration.

## 6. setNativeMethodPrefix is not a bytecode rewriting tool

Compare the three independent actions:

```text
1. Transformer creates Java body + prefixed native declaration
             |
             v
2. Agent registers prefix for the exact transformer (setNativeMethodPrefix)
             |
             v
3. Native library still has a compatible implementation and is loaded
             |
             v
   When JVM needs to resolve the prefixed native method:
   normal attempt -> fails -> consider prefix -> find original
```

Having step 2 without step 1: app code does not gain a wrapper on its own. Having step 1 without step 2: native `agent_foo` may fail to resolve to JNI implementation `foo`, unless the library also provides a matching symbol/registration. Having steps 1+2 without loading the library: you still get `UnsatisfiedLinkError`.

### 6.1. Manifest and lifecycle

Setting the prefix **before native method resolution is needed** is simpler and more reliable. With a startup agent, you can register in `premain` before target classes are loaded. With dynamic attach, the target may have already loaded classes and JNI bindings earlier; you must re-evaluate retransform/redefine limitations and not assume every native binding already established by the JVM can be changed.

`removeTransformer(t)` only unregisters future transformations. It **does not automatically roll back** already installed class bytes, does not automatically remove generated Java wrappers, and does not guarantee already linked native methods are unbound. Similarly, `setNativeMethodPrefix(t,"")` means disabling **future failed-resolution retries for the transformer**, not automatically restoring all old bindings.

### 6.2. How native prefix differs from commonly confused APIs

| Concept | Purpose | Does it perform `setNativeMethodPrefix`'s job? |
|---|---|---|
| `ClassFileTransformer.transform` | Generate/modify class bytes, create wrappers | **Does not** configure native retry rules |
| `setNativeMethodPrefix` | Specifies retry rules for native method resolution of a transformer | **Does not** write bytecode itself |
| `-javaagent` / `premain` | Launches a Java instrumentation agent | Only provides access to `Instrumentation` |
| `-agentpath` / native `Agent_OnLoad` | Launches a native JVMTI agent | Different API/agent lifecycle from a Javaagent |
| `System.loadLibrary` | Loads a JNI native library into the process/appropriate loader context | Does not create wrappers or prefixes |
| `RegisterNatives` | Binds Java native name+signature to a native function pointer | Uses prefix retry when applicable, but is still a JNI binding mechanism |
| `NativeMethodBind` JVMTI event | Observes/adjusts native binding at the JVMTI level when capability is present | A different observation path, unlike Java wrappers/prefixes |
| `retransformClasses` | Re-runs the transformation process on loaded classes if supported | Does not guarantee JNI binding or schema changes are allowed |
| `redefineClasses` | Replaces a class definition with supplied bytes | Not equivalent to setting a prefix |

## 7. Runnable example on Java 17+ and C JNI: two prefixes, one original implementation

This example intentionally **pre-writes two Java wrappers in source** so the learner can focus on **the native method resolution mechanism** without having to write an ASM bytecode transformer. The two registered `ClassFileTransformer`s are **identity placeholders** whose `transform` returns `null`; they only supply two registered prefixes allowing the JVM to handle the pre-wrapped native name.

**What the example demonstrates:** the Java structure after two real transformers have wrapped a native method while the native implementation keeps only the original name. It **does not** prove that two no-op transformers created the Java wrappers themselves. Generating wrappers automatically in a production agent requires a separate bytecode transform and dedicated schema/verification testing.

### 7.1. Environment requirements

- **JDK 17+** with `java`, `javac`, and `jar`.
- A C compiler such as `gcc`/`clang` or MSVC capable of building a JNI shared library.
- JNI headers `jni.h` in `$JAVA_HOME/include` and the platform-specific include directory.
- A JVM supporting the native-prefix capability and an agent manifest requesting `Can-Set-Native-Method-Prefix: true`.
- Run experiments only in a controlled environment. It loads native code into the same JVM process; do not test untrusted libraries on production machines.

Create the files in a `native-prefix-lab` directory:

```text
native-prefix-lab/
  NativeApi.java
  NativePrefixDemo.java
  PrefixAgent.java
  NoOpTransformer.java
  nativeprefixdemo.c
  agent.mf
```

There is no package declaration so the original JNI symbol stays easy to read. In real applications, classes should have their own packages and JNI symbols must escape the full class name.

### 7.2. `NativeApi.java`: two Java wrappers and one native declaration

```java
public final class NativeApi {
    static {
        System.loadLibrary("nativeprefixdemo");
    }

    private NativeApi() {
    }

    public static int sum(int a, int b) {
        System.out.println("WRAPPER_A");
        return a_sum(a, b);
    }

    private static int a_sum(int a, int b) {
        System.out.println("WRAPPER_B");
        return b_a_sum(a, b);
    }

    private static native int b_a_sum(int a, int b);
}
```

Timeline interpretation:

```text
Initial source concept:     native sum(II)I

After simulated transformer A:
    Java sum(II)I           -> calls a_sum(II)I
    native a_sum(II)I

After simulated transformer B:
    Java sum(II)I           -> calls a_sum(II)I
    Java a_sum(II)I         -> calls b_a_sum(II)I
    native b_a_sum(II)I
```

This is **Java source simulating transformed output**, not runtime bytecode produced by the two no-op transformers. Both prefixes are kept short as `a_` and `b_` **only in this lab** for readability; production should use more unique, collision-resistant prefixes.

### 7.3. `NativePrefixDemo.java`: the Java application

```java
public final class NativePrefixDemo {
    public static void main(String[] args) {
        int result = NativeApi.sum(4, 5);
        System.out.println("RESULT=" + result);
    }
}
```

`NativeApi` is only initialized when first used; the static block will load the JNI library `nativeprefixdemo`. If the library has not been built or the path is wrong, `UnsatisfiedLinkError: no nativeprefixdemo in java.library.path` may appear before attempting to resolve `b_a_sum`.

### 7.4. `NoOpTransformer.java`: a separate instance per registration

```java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

public final class NoOpTransformer implements ClassFileTransformer {
    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain domain,
            byte[] classfileBuffer) {
        return null;
    }
}
```

`return null` means **no bytecode modification at this step**. That is intentional: the wrappers are already simulated in `NativeApi.java`, so the demo needs no bytecode generator. In a real agent, transformer A must create wrapper A, transformer B must wrap A's native declaration next, and both must have their corresponding prefixes registered.

### 7.5. `PrefixAgent.java`: two prefixes for two transformer instances

```java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;

public final class PrefixAgent {
    public static void premain(String options, Instrumentation inst) {
        boolean supported = inst.isNativeMethodPrefixSupported();
        System.out.println("PREFIX_CAPABILITY=" + supported);

        if (!supported) {
            // Do not claim JNI binding has been established.
            throw new IllegalStateException(
                    "NATIVE_METHOD_PREFIX_UNSUPPORTED");
        }

        ClassFileTransformer first = new NoOpTransformer();
        ClassFileTransformer second = new NoOpTransformer();

        // In the exact order of the simulated wrapper layers.
        inst.addTransformer(first);
        inst.setNativeMethodPrefix(first, "a_");

        inst.addTransformer(second);
        inst.setNativeMethodPrefix(second, "b_");

        System.out.println("PREFIXES=a_,b_");
    }
}
```

Both transformers are registered in the `canRetransform=false` Java group, because the `addTransformer(transformer)` overload is used. They are created with **two separate `new` calls**, not reusing the same instance.

If the JVM does not support the capability, the agent throws an error and startup may halt; that is **fail-fast for the lab only** because the test would no longer be meaningful. For optional production telemetry, you should report `SKIPPED` and choose an approved fallback instead of crashing the application.

### 7.6. `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: PrefixAgent
Can-Set-Native-Method-Prefix: true

```

Ensure the file ends with a newline and blank line per the manifest format. `Can-Retransform-Classes: true` is not needed in this experiment; the two transformers do not retransform classes. `Agent-Class` is not needed because the startup `premain` agent is used.

### 7.7. `nativeprefixdemo.c`: JNI implementation **using only the original name**

```c
#include <jni.h>
#include <stdio.h>

/*
 * Only a native symbol for "sum" exists, NO symbol
 * for the Java native declaration "b_a_sum".
 */
JNIEXPORT jint JNICALL Java_NativeApi_sum(
        JNIEnv* env, jclass clazz, jint a, jint b) {

    (void) env;
    (void) clazz;

    puts("JNI_ORIGINAL");
    fflush(stdout);
    return a + b;
}
```

The native C code defines neither `Java_NativeApi_b_1a_1sum` nor `Java_NativeApi_a_1sum`. If the JVM tries normal automatic lookup for the Java declaration `b_a_sum`, it will not find an implementation. Only after applying the prefix rules from the two transformers can it locate `Java_NativeApi_sum`.

**Why not use `javac -h` to get the prototype directly for the final symbol?** `javac -h` generates a header based on **the native declaration currently in the source**, namely `b_a_sum`; in this lab, we **intentionally export the JNI symbol under the original name `sum`** to test the retry mechanism. Therefore the C function is declared explicitly, and must match the `(II)I` signature and JNI calling convention. That is a test point, not a bug in the example.

### 7.8. Compiling and running: Linux (Bash)

Set `JAVA_HOME` to your JDK 17+ directory; C compiler pre-installed:

```shell
# Step 1: build Java code and agent JAR.
javac NativeApi.java NativePrefixDemo.java PrefixAgent.java NoOpTransformer.java
jar cfm prefix-agent.jar agent.mf PrefixAgent.class NoOpTransformer.class

# Step 2: build shared JNI library for Linux.
gcc -shared -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libnativeprefixdemo.so nativeprefixdemo.c

# Step 3: startup agent -> app -> JNI native resolution.
java -javaagent:prefix-agent.jar \
  -Djava.library.path=. \
  -cp . NativePrefixDemo
```

The commands require a valid `JAVA_HOME` and `gcc` on `PATH`. You can check beforehand:

```shell
java -version
javac -version
test -f "$JAVA_HOME/include/jni.h" && echo JNI_HEADERS_OK
```

The `test` snippet is a Bash shell command and does not run in PowerShell. If `JAVA_HOME` is not set, point it to the actual JDK directory instead of guessing the path. `java.library.path=.` allows `System.loadLibrary("nativeprefixdemo")` to find `libnativeprefixdemo.so` in the current directory in typical Linux environments.

### 7.9. Compiling C on macOS or Windows

On macOS with `clang`/`cc` and a selected JDK:

```shell
cc -dynamiclib -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -o libnativeprefixdemo.dylib nativeprefixdemo.c

java -javaagent:prefix-agent.jar \
  -Djava.library.path=. \
  -cp . NativePrefixDemo
```

On Windows, run **Developer Command Prompt** with the MSVC compiler and `JAVA_HOME` pointing to the JDK:

```bat
javac NativeApi.java NativePrefixDemo.java PrefixAgent.java NoOpTransformer.java
jar cfm prefix-agent.jar agent.mf PrefixAgent.class NoOpTransformer.class
cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" nativeprefixdemo.c /link /OUT:nativeprefixdemo.dll
java -javaagent:prefix-agent.jar -Djava.library.path=. -cp . NativePrefixDemo
```

Exact C commands depend on toolchain/architecture; use a JDK and native compiler of the same architecture (for example x64 with x64). The example does not guarantee execution if the system lacks a C compiler, appropriate build flags, or permission to load native libraries.

### 7.10. Expected stdout when capability and automatic resolution work

On a HotSpot JDK 17/21 JVM with the native prefix capability and a properly built/loaded JNI library:

```text
PREFIX_CAPABILITY=true
PREFIXES=a_,b_
WRAPPER_A
WRAPPER_B
JNI_ORIGINAL
RESULT=9
```

This is **the expected output according to the API's JNI native prefix model**, not a log from a verified run on the current machine. This sequence is well-founded:

1. `premain` runs before the app, prints the capability, and registers `first->a_`, `second->b_`.
2. `NativePrefixDemo.main` calls `NativeApi.sum(4,5)`.
3. `sum` is Java wrapper A, prints `WRAPPER_A`, then calls `a_sum`.
4. `a_sum` is Java wrapper B, prints `WRAPPER_B`, then calls native `b_a_sum`.
5. Normal JNI lookup for `b_a_sum` fails because the library only has `Java_NativeApi_sum`. The JVM evaluates the prefixes attached to transformers per the rules and finds the original implementation.
6. Native C prints `JNI_ORIGINAL` and returns `9`.
7. Java prints `RESULT=9`.

**Testing limitation:** the two wrappers are written in source, **not** generated by `NoOpTransformer.transform`. A lab transitioning to real bytecode transformation must add QA for class schema, wrapper ordering, method descriptors, and compatibility with other transformers.

### 7.11. Control check: omitting `-javaagent`

If run **without the agent**:

```shell
java -Djava.library.path=. -cp . NativePrefixDemo
```

Java still enters `sum` and then `a_sum`. However, for the native declaration `b_a_sum`, the library has no symbol with that name, and there are no registered prefixes to retry. The predicted result is **`UnsatisfiedLinkError`** on the native resolution branch, without the `RESULT=9` line.

Do not match the entire stack trace or error message verbatim: it depends on the JVM and platform. What needs to be proven is that **the library was loaded but the native method could not be linked**; if the error is instead "no nativeprefixdemo in java.library.path", you are testing the wrong condition (library load failed before resolution).

### 7.12. Control check: registering only the first prefix

If only `a_` is assigned without `b_`, the Java source still calls native `b_a_sum`. In this situation there are not enough wrapper-prefix rules to get back to `sum`. Under the illustrated mechanism, the native method may fail to resolve and throw `UnsatisfiedLinkError`, unless the native library actually exports a symbol matching another resolution path.

This is an important reason to register **one prefix per wrapper layer created by each transformer**. You cannot use transformer A's prefix to cover B's responsibility as well.

## 8. One transformer skips the method: corresponding to a skipped middle prefix

Suppose A creates a wrapper, B is registered but does not match the target, and C creates a wrapper. Final class file state:

```text
Java foo()            -> Java wrapper A
Java a_foo()          -> Java wrapper C
native c_a_foo()      -> JNI implementation foo
```

B created neither `b_foo` nor `b_a_foo`. The final name is `c_a_foo`. This is a **realistic** scenario when agents have class filters, method exclusions, overload filters, or lack a capability for a specific transformer.

### 8.1. Why does the VM need to check intermediate wrappers?

If all prefixes were applied rigidly, the VM might try a name `c_b_a_foo` that does not exist in the class. According to the Javadoc, an intermediate prefix is only applied when **the corresponding non-native wrapper is present**. There must be evidence that the transformer actually transformed the method, not just a globally configured prefix.

This protects selectivity: an agent that wraps only a few native methods can still register its prefix without forcing every other native method through the same naming chain.

### 8.2. Example matrix

| T1 prefix `a_` | T2 prefix `b_` | T3 prefix `c_` | Possible final native method generated | Prerequisite |
|---|---|---|---|---|
| Wraps | Wraps | Wraps | `c_b_a_foo` | Wrappers from all three exist |
| Wraps | Skips | Wraps | `c_a_foo` | Wrappers A and C exist |
| Skips | Wraps | Wraps | `c_b_foo` | Wrappers B and C exist |
| Wraps | Wraps | Skips | `b_a_foo` | Wrappers A and B exist |
| Skips | Skips | Skips | `foo` remains native | No prefix retry needed if original JNI name resolves normally |

This is **a naming model of transformation output**, not a guarantee that every combination will be permitted if method descriptors/schema/loaders are incompatible. Each transformer must inspect the current class/method, without assuming all preceding transformers created wrappers.

### 8.3. Do not resolve by writing custom prefix string deletion

A common mistake is an agent coding logic like:

```java
// Illustrative anti-pattern: do not use as a JNI resolution mechanism.
String original = nativeName.replace("a_", "")
                            .replace("b_", "")
                            .replace("c_", "");
```

This `String.replace` call does not respect prefix boundaries (it can delete substrings in the middle of a method name), nor does it consider wrapper existence, method descriptors, JNI symbol escaping, or transformer order. Worse, it **cannot replace the JVM's JNI mechanism**. Let `setNativeMethodPrefix` handle retries per contract; the transformer only creates valid wrappers/renamed natives.

## 9. Practical transformer design: preconditions and post-checks

A professional native wrapping transformer must perform a **controlled bytecode transformation**, not just string replacement on method names. Pseudocode:

```text
on transform(classBytes):
  parse class
  for each method:
    if method is not native:
      keep unchanged
    if !allowlisted(class, method, signature):
      keep unchanged
    if wrapper or prefixed native name already exists:
      report duplicate/conflict; SKIP or FAIL by policy

    capture original name, descriptor, flags
    move native declaration to prefix + originalName
    create non-native wrapper at originalName with same calling contract
    wrapper:
      collect approved minimal metrics
      invoke renamed native declaration using correct static/instance dispatch
      preserve return / exception semantics
    verify class file, frames, descriptors and access rules
  return new class bytes if modified else null
```

The code above is an **illustrative algorithm**, not a DSL or Java code. Important details:

- Exact **method descriptor**, return type, `static`/instance, access flags, and exceptions.
- The wrapper must pass argument types verbatim, without arbitrary boxing/unboxing that could break ABI.
- For instance methods, preserve the `this` receiver with proper semantics.
- Do not add duplicate method name+descriptor pairs within the same class.
- The new native declaration needs to link to the original native implementation; the prefix must match the transformer's registration.
- Creating a wrapper typically alters **the method count and the `native` modifier**; therefore **you must not assume the same transformation can be applied via retransformation/redefinition** to an already loaded class (schema changes are restricted).
- If the helper calls back into application code or a JNI library, guard against recursion and preserve failure semantics.
- Do not treat `transform` returning bytes as sufficient post-verification; you need JVM verification/native linking and real method testing.

### 9.1. Initialization timing: why is load-time usually the primary path?

Replacing native method `foo` with a Java wrapper `foo` and adding native declaration `agent_foo` changes the class's **method schema**. Standard HotSwap (`retransformClasses`/`redefineClasses`) typically **does not** allow adding/removing/renaming methods. Therefore this style of wrapper transformation should be designed for **initial class definition** (load-time) or a strategy compatible with deployment constraints.

An agent attached after the target class has loaded cannot simply call `setNativeMethodPrefix` and expect wrappers to appear automatically. It should report `SKIPPED_EXISTING_CLASS` or choose another tested mechanism, rather than forcing an invalid schema retransform.

### 9.2. Transformer ordering and idempotency

If multiple transformers wrap native methods:

- Each transformer must know **the current native name** in the input bytes, which may already carry a previous transformer's prefix.
- The decision to create a wrapper must be based on the actual target method (name+descriptor, owner), not arbitrary substring matching.
- If a transformer runs again in a valid context, it must not unintentionally add two identical wrapper layers.
- During retransformation, non-retransformation-capable transformers are not called again; the JVM reapplies their previous results per rules. Native wrappers created at load time do not mean method schema changes in a new retransform pass are always allowed.
- The order of Java/native transformer groups may differ from simple `addTransformer` order, so prefix conventions must reflect the actual pipeline output.
- If a transformer does not wrap, **return `null`** and do not create a dummy prefix in the method name.

### 9.3. Prefix selection rules

- A prefix belongs to **one transformer with a defined identity**; do not share one prefix across multiple independent transformers.
- Choose a name unlikely to collide in apps/libraries; test against real method names/descriptors before generating.
- If the name contains `$`/`_`, verify full JNI escaping; do not deduce C symbols from a single string alone.
- Avoid changing the prefix after classes have loaded/native methods have been resolved; if a new rollout is needed, test with a fresh JVM.
- When clearing a prefix (`""`/`null`), do not assume already established native bindings will automatically be unbound.
- Include agent version, transformer ID, and prefix in controlled configuration logs; do not log raw method arguments on the hot path.

## 10. Diagnosing native method prefix: common failure table

| Symptom | Possible cause | What to check |
|---|---|---|
| `isNativeMethodPrefixSupported()==false` | JVM does not support it or manifest does not request it | `Can-Set-Native-Method-Prefix: true`; VM version/vendor |
| `UnsupportedOperationException` when setting prefix | Capability unavailable | Precheck, manifest, and JVM configuration |
| `IllegalArgumentException` when setting prefix | Transformer instance not registered | `addTransformer(t)` must be executed first |
| `NullPointerException` when setting prefix | `null` transformer parameter | Do not confuse with a valid `null` prefix |
| `UnsatisfiedLinkError: no X in java.library.path` | Native library not loaded/found | `System.loadLibrary`, `java.library.path`, OS-specific library name |
| `UnsatisfiedLinkError` when calling prefixed method | JNI symbol/descriptor mismatch or prefix retry not applied | Check Java native name, JNI escaping, prefix registration, library exports |
| App instrumented but no wrapper logs | Transformer did not match, class loaded before agent registered, bytes overwritten by another transformer | Check class loader, transform callbacks, load-time ordering |
| Wrapper A runs but B does not | B skipped method or B's wrapper/code was dropped | Check output class file and prefix/method descriptors |
| C JNI symbol exists yet still fails to link | Wrong class name, overloaded signature, architecture/ABI, loader ownership | `javap`, `nm -D`/`dumpbin`, JNI header/signature |
| Method behaves incorrectly after wrapping | Return/exception handling, receiver, or descriptor mismatch | Compare before/after behavior, test primitives/references/throws |
| Prefix too generic like `wrapped_` | Name already defined by app or collides with another agent | Choose a unique namespace; check collisions first |
| `RegisterNatives` returns an error | Name/signature mismatch, wrong class, wrong mapping | Check `JNINativeMethod`, actual method list, and JNI exceptions |
| Only registered prefix, JNI still calls original implementation with no probe | No class transformation creating Java wrapper | Registering a prefix does not auto-instrument |
| Agent attaches late and cannot wrap running class | Schema change is restricted | Design a startup agent or clearly reported fallback |
| Cannot use helper from target class | Class-loader/module visibility | Check helper path and access; prefix does not cure `NoClassDefFoundError` |
| Native call bound before changing prefix | Binding lifecycle does not roll back/re-resolve as hoped | Start early, do not rely on late prefix changes |
| Multiple agents, wrong prefix order | Transformer order/grouping differs from expectation | Trace callback order and final class bytes |

### 10.1. Minimal debugging sequence

1. **Precheck:** `isNativeMethodPrefixSupported` and manifest `Can-Set-Native-Method-Prefix`.
2. **Registration:** confirm the exact `ClassFileTransformer` instance was added, prefix is accurate, and it does not collide with another agent.
3. **Class source:** identify binary class name, defining loader, class load order, method signatures.
4. **Output bytes:** use `javap -p -s -c Target` to verify whether Java wrapper(s) and the final native declaration exist.
5. **Library:** verify `System.loadLibrary` succeeds and the shared library matches the architecture/runtime.
6. **JNI binding mode:** automatic symbol lookup or `RegisterNatives`? Debug along the corresponding retry direction.
7. **JNI names:** check escaped method/class names and overload descriptors. On Linux you can use `nm -D libname.so` or `readelf -Ws` to inspect exports; on Windows use `dumpbin /exports` when MSVC is available.
8. **Runtime test:** call the real native method with input/expected output; distinguish wrapper logs from JNI logs.
9. **Multiple transformers:** check actual order and which intermediate Java wrappers exist.
10. **Report:** `PREFIX_CONFIGURED` is distinct from `WRAPPER_GENERATED`, `NATIVE_RESOLVED`, and `FEATURE_VERIFIED`.

### 10.2. Suggested report format

```json
{
  "feature": "native-call-latency",
  "targetClass": "com.example.NativeMath",
  "method": "sum",
  "descriptor": "(II)I",
  "nativePrefixCapability": true,
  "transformerId": "latency-v3",
  "registeredPrefix": "$$_agent_latency_$",
  "wrapperGenerated": true,
  "nativeResolution": "VERIFIED",
  "status": "APPLIED"
}
```

This is an **illustrative log schema**, not generated by the JVM itself. `nativeResolution=VERIFIED` should only be recorded after a native call is tested/observed succeeding; `setNativeMethodPrefix` returning is not enough to conclude resolution succeeded. If dynamically attaching to an already loaded class and a wrapper cannot be created, report `SKIPPED` with the reason instead of reporting the feature enabled.

## 11. Limitations to state clearly in production

### 11.1. Does not replace the JNI library itself

The prefix mechanism only helps **find the right existing implementation** when the native declaration is renamed. It does not change compiler flags, C functionality, JNI API version, how the library is loaded, or permissions to run native code. If `JNI_OnLoad` fails, the native library has the wrong CPU architecture, or the C function has a mismatched signature, the prefix cannot help.

### 11.2. Not every native method should be wrapped

There are sensitive native methods at the runtime/VM or system library level. Altering class schema/call paths can affect class loading, thread synchronization, signal handling, native resource ownership, or JNI assumptions. Filter targets tightly, test per JDK/OS/arch, and avoid instrumenting native methods without a specific measurement goal.

### 11.3. Cannot observe C internals from a Java wrapper alone

A Java wrapper lets you measure **entry/exit timing** of a native call and information designed to be collected on the Java side. It does not automatically provide traces of JNI function calls **inside the C implementation**, nor does it replace a native JVMTI profiler. If you need native stack/call internals, you need appropriate native tooling, permission controls, and overhead management.

### 11.4. Multi-agent ordering is not a global native renaming API

Two agents can register transformers and prefixes independently. Native resolution respects ordering rules and wrapper existence, rather than blindly stripping every prefix-looking string. You must test **actual agent combinations**; never assume your agent always runs first or last.

### 11.5. Security and privacy concerns

Native methods may receive pointers, key buffers, byte arrays, or sensitive data over JNI. Helpers inside Java wrappers should avoid arbitrarily calling `toString`/serializing arguments, avoid logging raw buffers, and preserve exception/return semantics. Prefix resolution aids linkage, not automatic data protection.

## 12. Case studies

### Case A — One transformer wraps, library keeps original JNI name

- Initially: `native int foo(int)` and JNI symbol for `foo`.
- After transform: `int foo(int) { return a_foo(int); }` + `native int a_foo(int)`.
- Agent: `setNativeMethodPrefix(t,"a_")` for the exact registered transformer.
- Automatic resolution: tries symbol for `a_foo`; if missing, retries looking up symbol for `foo`.

**Conclusion:** the old JNI implementation can be kept if all class/method signatures and JNI binding conditions are valid.

### Case B — T1 creates wrapper, T2 skips, T3 creates wrapper

- Registered prefixes: `a_`, `b_`, `c_`.
- Actual wrapped Java methods: `foo` and `a_foo`.
- Final native declaration: `c_a_foo`.
- No `b_a_foo`.

**Conclusion:** prefix `b_` is not required in the native name. The JVM inspects intermediate wrappers to determine a meaningful chain, rather than rigidly stripping every registered prefix.

### Case C — Agent only sets prefix, no wrapper

- `inst.setNativeMethodPrefix(t,"agent_")` returns successfully.
- Target class still has `native foo`, no Java wrapper.

**Conclusion:** native resolution of `foo` may still work normally. **No Java probe was inserted**, so do not report "native method traced".

### Case D — Prefixed declaration exists but library is not loaded

- Class has `native agent_foo` and a valid prefix.
- `System.loadLibrary` fails or the loader cannot find the native library.

**Conclusion:** the prefix does not fix loader/library failures. Fix loading paths/packaging and verify JNI symbols first.

### Case E — RegisterNatives binds by original name

- Native code registers `"foo"` + descriptor + pointer.
- Java method `foo` is non-native after wrapping.
- Prefixed native declaration `agent_foo` is present, and the prefix is registered.

**Conclusion:** when normal mapping fails, the retry mechanism considers **the prefixed Java method name** to bind the function pointer. Do not confuse this with automatic JNI lookup, which goes in the direction of stripping the prefix from the implementation name.

## 13. Self-check questions

1. **Why can't `ClassFileTransformer` insert Java bytecode into a `native` body?** Because a native declaration has no Java `Code` attribute; a non-native Java wrapper must be created.
2. **Does `setNativeMethodPrefix` create wrappers itself?** No. It only changes the retry rules for failed native resolution.
3. **What capability is required?** `isNativeMethodPrefixSupported()` true and the manifest requesting `Can-Set-Native-Method-Prefix: true`.
4. **What error can occur if `setNativeMethodPrefix` is called before `addTransformer`?** `IllegalArgumentException` because the transformer is not registered.
5. **How does passing a `null` transformer differ from a `null` prefix?** A null transformer causes `NullPointerException`; a null/empty prefix means disabling retry for the transformer.
6. **With automatic JNI lookup, what does the JVM try first?** Looking up the symbol by the current native declaration name. Only when that fails does it try the prefix mechanism.
7. **In which direction does automatic fallback apply the prefix?** Strips the prefix from the implementation name to look up in order to revert to the original native symbol.
8. **In which direction does `RegisterNatives` fallback apply?** When the original mapping fails, it considers the Java native method name with the corresponding prefix.
9. **Three transformers A->B->C all wrap `foo`; what is the final native name in the example?** `c_b_a_foo`.
10. **If B does not wrap, is the name forced to be `c_b_a_foo`?** No, the result can be `c_a_foo`.
11. **Why is an intermediate prefix only considered when the corresponding wrapper exists?** So the JVM distinguishes transformers that actually wrapped the method from those that skipped it.
12. **Why is `wrapped_` considered a poor prefix by the Javadoc?** It may collide with an existing method name.
13. **What might the JNI symbol of a Java method containing `_` require?** JNI escaping, such as `_1`; do not concatenate raw names.
14. **An agent assigned a prefix but forgot to load the library. Will it work automatically?** No, the native implementation must still exist and be loaded.
15. **Does merely seeing `setNativeMethodPrefix` return successfully prove the probe works?** No; wrapper, native binding, and effect verification are needed.
16. **Is it good to register two prefixes using the same transformer instance multiple times?** No; the Javadoc discourages duplicate instance registration and clear identity is needed.
17. **Can native wrapping that changes the method schema be freely applied via retransforming an already loaded class?** No; HotSwap generally restricts adding/removing/renaming methods, so load-time is the better path.
18. **Does `removeTransformer` automatically remove installed Java wrappers?** No.
19. **Does native prefix specify the `.so`/`.dll` path?** No; library loading is an independent step.
20. **Is the `NativeMethodBind` JVMTI event the same as `setNativeMethodPrefix`?** No, that is a mechanism for tracking/altering bindings in JVMTI when the capability is present.
21. **In the demo, why is the JNI C function named `Java_NativeApi_sum` even though the Java native declaration is `b_a_sum`?** Because the lab tests retrying through two prefixes `a_` and `b_` to find the original implementation.
22. **Without the agent, what error does the lab encounter when calling native `b_a_sum`?** Expected `UnsatisfiedLinkError` at native method binding, assuming the library is loaded and only has the original symbol.
23. **If the JNI C function has the wrong signature, can the prefix fix it?** No. The JNI ABI/descriptor must still be correct.
24. **Should system native methods be instrumented just because the JVM allows prefixes?** No. Separate scoping, compatibility, performance, and testing are required.

## 14. Official references

- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `isNativeMethodPrefixSupported`, `setNativeMethodPrefix`, the two retry mechanisms, multiple transformer prefixes, exceptions/capabilities.
- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): compatibility contract with Java 17+ and manifest requirements.
- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): ordering of the four transformer groups, output bytes, and retransformation behavior.
- [Java SE 21 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent entry points, manifest `Can-Set-Native-Method-Prefix`.
- [Java SE 21 — JNI Specification, Design Overview](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html): automatic JNI name mapping, name mangling, short/long symbol lookup, native library/class-loader behavior.
- [Java SE 21 — JNI Functions](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html): `RegisterNatives`, `JNINativeMethod`, name/signature/function pointer.
- [Java SE 21 — JVM TI Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html): `SetNativeMethodPrefix`/`SetNativeMethodPrefixes` for native JVMTI agents, multiple environments, and native binding lifecycle.
- [Java SE 21 — java launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `-javaagent`, `-Djava.library.path`, and runtime options.

**Key takeaway:** **each transformer creating a native wrapper needs its own prefix**. The JVM attempts normal JNI binding first; only when that fails does it use prefixes to retry, following **different paths** for automatic symbol lookup and `RegisterNatives`. A prefix only solves **native resolution**; it does not generate wrappers, replace JNI libraries, or prove probes are working. Success requires **valid wrapper class bytes + prefix on the exact instance/order + compatible JNI implementation + runtime verification** together.