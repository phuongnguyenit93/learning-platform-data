# Native Methods Have No Bytecode to Instrument Directly

## 1. Core Problem: A Java Declaration Without a JVM Instruction Body

A method declared with the `native` keyword is **an interface point from Java to an implementation that does not reside in the JVM bytecode of that method itself**. The Java compiler still writes method metadata into the `.class` file: name, descriptor (parameter/return types), access flags, annotations, and other valid metadata. However, it **does not write a `Code` body containing instructions** for that method.

Example:

~~~java
public final class NativeExample {
    public static native int add(int left, int right);

    public static int addJava(int left, int right) {
        return left + right;
    }
}
~~~

This is **illustrative source code** (it can be saved as `NativeExample.java` and compiled), without an accompanying native library to call `add` successfully. Both methods have the same parameter and return types, but:

- `add` has the **`ACC_NATIVE`** flag. In the class file's `method_info`, there is **no `Code` attribute**.
- `addJava` has a normal Java implementation, compiled by `javac` into bytecode (for example, instructions equivalent to loading two parameters, adding them, and then `ireturn`).
- A call to `add` must be linked by the JVM to a **native implementation** via an appropriate mechanism, such as JNI. Native execution does not equate to an array of JVM instructions for ASM/Byte Buddy to insert into.
- A `ClassFileTransformer` still **sees the class file bytes containing the native method declaration**, but there is no bytecode body of that method itself in which to add entry/exit probes.

**Immediate conclusion:** "native has no bytecode to instrument directly" does **not** mean "nothing can be observed about native." It means **JVM instructions cannot be placed directly into the non-existent `Code` of a native method**. There are other mechanisms: Java wrappers, native-method prefixes in Java instrumentation, or JVM TI events/hooks.

### 1.1. Distinguishing Four Technology Layers

| Layer | Role | Is there JVM bytecode to weave? |
| --- | --- | --- |
| `method_info` of the native method | Declares name, descriptor, `ACC_NATIVE` | **No** `Code` in the native method |
| Java method calling native | Contains `invokestatic`, `invokevirtual`, or an appropriate call instruction | **Yes**, the call site can be instrumented |
| Java wrapper around native | Contains before/after/try-finally and calls native | **Yes**, the wrapper can be instrumented |
| Native implementation | Machine code/library or mechanism provided by the JVM | **Cannot** be modified by inserting JVM bytecode into the native method |

Do not use "JNI" and "native" as absolute synonyms: many JDK native methods use specialized execution paths or are optimized by the JVM as intrinsics, whereas **JNI** is a standard interface for connecting Java code and native libraries. The C/JNI exercise below is one concrete example, not a claim that every native method must execute through a custom `.so` file.

## 2. JVM Specification Basis: `ACC_NATIVE` and the `Code` Rule

According to the Java Virtual Machine Specification (JVMS), each method declaration has a `method_info` structure consisting of fields such as `access_flags`, `name_index`, `descriptor_index`, and the `attributes` table. `Code` is an attribute that describes **the instructions and execution metadata of a method**.

The rule in **JVMS `4.7.3**:

- A **`native` or `abstract`** method **must not contain** a `Code` attribute in `method_info`.
- A method that is neither native nor abstract requires a `Code` attribute according to the class file format constraints.
- `ACC_NATIVE` has the bit mask `0x0100` in `method_info.access_flags`.
- `ACC_ABSTRACT` is a different case: it also has no code, but because **there is no implementation in the method itself**, rather than calling out to a native implementation.

Diagram:

~~~text
method_info of a Java method with a body:
    name_index -> "addJava"
    descriptor -> "(II)I"
    flags      -> ACC_PUBLIC, ACC_STATIC
    attributes -> Code {
        max_stack, max_locals,
        code[] = JVM instructions
        exception_table, ...
    }

method_info of a native method:
    name_index -> "add"
    descriptor -> "(II)I"
    flags      -> ACC_PUBLIC, ACC_STATIC, ACC_NATIVE
    attributes -> (may have annotations / Exceptions / other metadata)
    NO Code attribute
~~~

This is a **structural model**, not a byte dump by offset. Every bytecode tool must obey this rule when writing class-file output. Attaching `Code` to a method that still carries `ACC_NATIVE` will produce an invalid class file under JVMS; it is not a trick to make the JVM execute the new `Code`.

**Do not confuse "has no `Code`" with "has no class-file entry."** A native method still has a name/descriptor/flags and can be accessed via reflection such as `Class.getDeclaredMethod(...)` or checked with `Modifier.isNative(...)`.

Source: [JVMS Java 17 — `4.6 Methods and `4.7.3 Code Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html).

## 3. `javap` Shows the Difference Visually

Compile the `NativeExample.java` example above:

~~~bash
javac --release 17 NativeExample.java
javap -p -c NativeExample
javap -p -v NativeExample
~~~

`javap -c` prints instructions for methods that have a `Code` section. It displays the native method declaration, but **has no instruction list for the native method itself**.

Meaningful abridged output:

~~~text
public static native int add(int, int);

public static int addJava(int, int);
  Code:
     0: iload_0
     1: iload_1
     2: iadd
     3: ireturn
~~~

This is an **illustrative excerpt of `javap -c`**, not the full output (constructor, constant pool, and other details are omitted). When using `javap -v`, look for the `ACC_NATIVE` flag and verify that **there is no `Code:` belonging to the native method**. Subsequent `Code:` lines may belong to the constructor or other Java methods, so do not search for the raw string `Code:` across the entire file and draw the wrong conclusion.

If a parser using ASM or a bytecode library detects the `ACC_NATIVE` flag, it must **not treat the native method as a method with an instruction list**. The fact that `visitMethod` is called when the parser encounters a native declaration does not mean `visitCode` has a valid body to instrument.

## 4. Why Cannot a Transformer Simply Insert Code Into a Native Body?

In a Java agent, `ClassFileTransformer.transform(...)` receives **the entire array of class-file bytes**. Therefore, the agent can still:

- Observe the native method **declaration**: class name, method name, descriptor, flags.
- Modify **Java methods that have `Code`** in the same class, such as the `someNative(...)` call site.
- At an allowed class-loading phase, transform the **class structure** to add a Java wrapper and change how the native name is bound via a supported mechanism.
- Return valid reconstructed class-file bytes.

However, `transform` **does not receive the machine address** of the native function as a list of JVM instructions. Two invariants hold:

1. The original native method with `ACC_NATIVE` has no `Code` to place `onEnter/onExit` via JVM bytecode at the "beginning/end" of the method itself.
2. The JVM/Java agent does not provide an API to "arbitrarily modify the C/C++ implementation of a JNI function" through `ClassFileTransformer`.

Callback-style example:

~~~java
@Override
public byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain,
        byte[] classfileBuffer) {

    if (className == null || !className.startsWith("demo/")) {
        return null;
    }

    // The parser can recognize method_info carrying ACC_NATIVE.
    // There is no Code attribute to insert instructions into that method.
    // When only observing, return null to leave the class bytes unchanged.
    return null;
}
~~~

This is a **code snippet inside a class implementing `ClassFileTransformer`**, requiring imports/agent setup, not a standalone program. `return null` means this transformer does not modify the bytes; it does not prevent other transformers from applying.

**Key distinction:** modifying **Java call sites** is possible, but it is not guaranteed to capture every call to the native function (some call sites are outside the instrumentation scope, some native methods have multiple entry paths, or the JVM applies specialized mechanisms). If you need to observe at **the time the native function is bound/called**, you must choose a tool at the appropriate layer rather than claiming to have modified the native body.

### 4.1. Comparison with Abstract Methods

`abstract` also has no `Code`, but the situation is different:

- An abstract method has no implementation in the declaring class/interface; the JVM dispatches to a **concrete implementation** in a subclass or implementing class.
- A native method has an implementation **outside the JVM bytecode of that method**, typically through native binding.
- For abstract methods, you can instrument the overriding method **that has code**.
- For native methods, you typically instrument a **wrapper/call site**, or use native/JVM TI capabilities.

Both cases lack `Code`, but the instrumentation solutions are not the same.

## 5. Simplest Practical Approach: Using a Java Wrapper

If you **control the source or API version**, place a non-native Java method around the native declaration:

~~~java
private static native int nativeAdd(int a, int b);

public static int add(int a, int b) {
    long start = System.nanoTime();
    try {
        return nativeAdd(a, b);
    } finally {
        long elapsed = System.nanoTime() - start;
        recordElapsed(elapsed);
    }
}
~~~

This is a **code snippet inside a class**; `recordElapsed` is defined by the application. The wrapper `add` has Java bytecode, including `try/finally` and the call instruction to `nativeAdd`. It can be further instrumented with ASM, Byte Buddy, the JDK Class-File API (JDK 24+), or another suitable approach.

Pros: easy to reason about, provides entry/exit and duration, clear Java stack/caller context, and can be unit tested. Cons: only measures calls **going through the wrapper**; code calling the native declaration directly bypasses the wrapper. If the native function calls back into Java or runs asynchronously on a native thread, the wrapper's duration does not necessarily equal all the underlying native work.

**`finally`** runs on normal return and on normal exception/error unwinding. It does not guarantee that the event is emitted if the process is terminated abruptly or if native code crashes the JVM. The recorder itself must also be designed with low overhead and must not mask business errors.

### 5.1. Measuring the Call Boundary vs. Measuring Native CPU Time

| Measurement | Observes | Does not assert by itself |
| --- | --- | --- |
| Wrapper `startNanos → finally` | Wall-clock elapsed time of a call across the boundary | How much time is CPU, syscalls, I/O, GC, or scheduler |
| Counting passes through the wrapper | Number of wrapper invocations | Every native call path in the JVM |
| `ClassFileTransformer` on Java caller | Java bytecode calling native | Instructions inside the JNI function |
| JVMTI native bind event | Moment the native implementation is **bound** | Number of times the native function is called |
| Sampling profiler/native stack profiler | Stack/CPU samples depending on the tool | Every short call or all internal variables |

Do not use an `onEnter` counter at a call site and label it "system-wide native method invocations" if other uninstrumented call paths exist.

## 6. Real Java 17 + C JNI Example: Seeing the Native Declaration and the Wrapper With Code

The example below **builds and loads a real native library**, then calls a Java wrapper. On Linux x86_64/aarch64 with OpenJDK headers + appropriate GCC, the entire example compiles and runs. It uses a function that adds two numbers so that stdout does not depend on timing or scheduling.

**Structure:**

~~~text
native-boundary/
├── NativeBoundaryDemo.java
├── NativeBoundaryDemo.c
├── NativeBoundaryDemo.h          (generated by javac -h)
├── NativeBoundaryDemo.class      (generated by javac)
└── libnativeboundary.so          (generated by gcc, Linux name)
~~~

### 6.1. File `NativeBoundaryDemo.java`

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public final class NativeBoundaryDemo {
    static {
        System.loadLibrary("nativeboundary");
    }

    private static native int nativeAdd(int left, int right);

    private static int observedAdd(int left, int right) {
        System.out.println("enter");
        try {
            return nativeAdd(left, right);
        } finally {
            System.out.println("exit");
        }
    }

    public static void main(String[] args) throws Exception {
        Method nativeMethod = NativeBoundaryDemo.class.getDeclaredMethod(
                "nativeAdd", int.class, int.class);
        Method wrapperMethod = NativeBoundaryDemo.class.getDeclaredMethod(
                "observedAdd", int.class, int.class);
        System.out.println("nativeFlag="
                + Modifier.isNative(nativeMethod.getModifiers()));
        System.out.println("wrapperNativeFlag="
                + Modifier.isNative(wrapperMethod.getModifiers()));
        System.out.println("result=" + observedAdd(7, 5));
    }
}
~~~

**Note:** `NativeBoundaryDemo.nativeAdd` is a private static native declaration **without a Java body**. `observedAdd` is a normal Java method, for which `javac` generates `Code`; it calls `nativeAdd` from inside a `try/finally` block. `System.loadLibrary("nativeboundary")` requires the OS/JVM to locate the native library via `java.library.path`.

### 6.2. File `NativeBoundaryDemo.c`

~~~c
#include <jni.h>

JNIEXPORT jint JNICALL Java_NativeBoundaryDemo_nativeAdd(
        JNIEnv *env, jclass type, jint left, jint right) {
    (void) env;
    (void) type;
    return left + right;
}
~~~

This is **a real JNI function**. The name `Java_NativeBoundaryDemo_nativeAdd` is generated according to JNI rules for mapping Java class/method names to native library symbols. `JNIEnv*` and `jclass` are parameters passed by the JVM to static native methods; this example does not need to use them.

Use `javac -h .` to generate the `NativeBoundaryDemo.h` header and verify the function signature. Do not guess JNI symbol names manually when the package/name contains underscores, special characters, or overloads; the JNI mangling algorithm has specific escaping rules and long-name schemes.

### 6.3. Commands on Linux (JDK 17+, GCC)

In the directory containing the two source files above:

~~~bash
javac --release 17 -h . NativeBoundaryDemo.java

# JAVA_HOME must point to the JDK directory in use:
gcc -std=c11 -Wall -Wextra -Werror -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  NativeBoundaryDemo.c -o libnativeboundary.so

java -Djava.library.path=. NativeBoundaryDemo

javap -p -c NativeBoundaryDemo
javap -p -v NativeBoundaryDemo
~~~

The trailing `\` in the `gcc` command is **Unix/Linux shell syntax**. Windows users need a toolchain that produces **`nativeboundary.dll`** and uses the JDK header path `include/win32`; on macOS the library is typically `libnativeboundary.dylib` with corresponding linker/header options. **Do not** copy the Linux `gcc` command above and run it verbatim in PowerShell.

Check `JAVA_HOME` if it is not already set. `javac -h .` generates the JNI header. On JDK 21, the test used `javac --release 17` to demonstrate Java 17 source/API compatibility. `java -Djava.library.path=.` must be run in the directory containing the built library.

### 6.4. Exact Stdout When the Native Library Loads Successfully

~~~text
nativeFlag=true
wrapperNativeFlag=false
enter
exit
result=12
~~~

The output was tested with OpenJDK 21 using `javac --release 17` and GCC on Linux; the lines appear in the exact order above. Because `observedAdd` executes `return nativeAdd(...)` inside `try`, the `finally` block prints `exit` **before** `main` prints `result=12`.

`javap -p -v NativeBoundaryDemo` confirms at the `nativeAdd` declaration:

~~~text
private static native int nativeAdd(int, int);
  descriptor: (II)I
  flags: (0x010a) ACC_PRIVATE, ACC_STATIC, ACC_NATIVE

private static int observedAdd(int, int);
  descriptor: (II)I
  flags: (0x000a) ACC_PRIVATE, ACC_STATIC
  Code:
~~~

This is a **selected excerpt** from `javap -v`, not the full output with constant pool and line numbers. The decisive difference is that **`nativeAdd` has no `Code:`**, while the wrapper `observedAdd` does.

### 6.5. What Happens When the Native Library Is Missing?

If you delete/rename `libnativeboundary.so` or omit the `java.library.path` path, the program may throw **`UnsatisfiedLinkError`** right at `System.loadLibrary`. If the library is present but lacks the corresponding symbol or does not register the native function properly, the error may occur when the JVM resolves/calls `nativeAdd`.

A native binding error **does not prove** whether a method has bytecode or not; those are two different layers. When debugging, clearly distinguish:

1. Can the JVM load the OS library?
2. Is the native function mapped with the right name/descriptor via a JNI symbol or `RegisterNatives`?
3. Does the Java wrapper receive the exception/linkage error and record it properly?
4. If the native library causes a crash/process abort, Java exception handling and `finally` may **not** run.

## 7. For a Java Agent Without Modifying Source: `setNativeMethodPrefix` Is the Supported Wrapper Mechanism

If you cannot modify the source code to create a wrapper, a Java agent has a special capability:

~~~java
boolean available = inst.isNativeMethodPrefixSupported();
inst.setNativeMethodPrefix(transformer, "$AgentNative$_");
~~~

This is a **code snippet inside an agent**, requiring an `Instrumentation inst` and a **`ClassFileTransformer transformer` that has already been registered**. Only call `setNativeMethodPrefix` if `isNativeMethodPrefixSupported()` returns `true`; this flag also depends on the agent manifest and the JVM.

### 7.1. The Idea of Turning a Native Method Into a Java Wrapper

The official Javadoc describes transforming:

~~~java
native boolean foo(int x);
~~~

Into the **conceptual** form:

~~~java
boolean foo(int x) {
    // Record enter event, start time, context...
    return $AgentNative$_foo(x);
}
native boolean $AgentNative$_foo(int x);
~~~

The two snippets above are a **signature transformation pattern**, not standalone runnable source. In the transformed class:

- Method `foo` is a **non-native wrapper** with `Code` so the agent can install logic before/after the call.
- The native method is renamed to `$AgentNative$_foo`, still without `Code`.
- The JVM may not find a native symbol under the new name; when normal native resolution fails, the **native prefix mechanism** allows retrying with the prefix stripped according to the contract.
- As a result, the renamed native method can be linked to the implementation originally intended for the original name `foo`.

**`setNativeMethodPrefix` does not automatically generate a wrapper!** The transformer must **actually rewrite the class file** to provide the appropriate wrapper. Merely configuring a prefix while the transformer always returns `null` leaves the original native method uninstrumented.

Choose a unique prefix to avoid colliding with existing method names. Multiple transformers can create multiple wrapper layers with their own prefixes; the specification describes the prefix retry order and cases where a layer does not apply a wrapper. Do not mechanically rename all native methods when unnecessary.

### 7.2. When Is Setting a Prefix the Right Choice?

It is suitable when the agent can **transform classes at initial definition**, wants to preserve the original method API, and wants to record before/after each native call via a Java wrapper. This is a **native resolution auxiliary capability**, not a native machine code debugger/profiler.

Check the following:

- The JAR manifest has `Can-Set-Native-Method-Prefix: true`.
- The JVM and agent configuration return `isNativeMethodPrefixSupported() == true`.
- The transformer has been passed to `addTransformer(...)` **before** calling `setNativeMethodPrefix`.
- The transformer generates a **wrapper method with valid `Code`** and renames the native method with the matching prefix/descriptor.
- No conflicts with native symbols/JNI `RegisterNatives`, overloads, class loaders, modules, or static/native flags.
- Real tests exist where the target native implementation is linked and the method is called.

**Critical constraint:** Turning a native method into a non-native wrapper and creating/modifying methods can constitute **schema/modifier changes**. Do not assume `retransformClasses`/`redefineClasses` on an **already loaded class** allows this. On standard HotSpot/JVMs, many schema or method modifier changes are restricted. That is why the Javadoc places the native wrapping example at **initial class definition**. Design the agent to run early, or choose a different technique for already loaded classes.

### 7.3. Two Different Capability Checks

| Check | What does it mean? | What does it not prove? |
| --- | --- | --- |
| `isNativeMethodPrefixSupported()` | Agent/JVM has the capability to retry native binding using a prefix | That the transformer created a wrapper or that native calls are measured |
| `isRetransformClassesSupported()` | Permission to request retransformation of loaded classes when other conditions hold | That changing a native method into a Java wrapper on a loaded class is allowed |
| `isRedefineClassesSupported()` | Permission to redefine loaded classes under JVM constraints | That the native implementation has a bytecode body to instrument |
| `isModifiableClass(type)` | A specific class can be a target of redefine/retransform | That native methods inside the class have `Code` |

These are capabilities at **multiple layers**. `Can-Set-Native-Method-Prefix` does not replace `Can-Retransform-Classes`, nor is it proof that all native methods are successfully instrumented.

## 8. Java 17 Example: Checking the Native Prefix Capability of a Real Agent

This example checks the **native prefix capability and transformer registration order** in the JVM. To stay independent of bytecode libraries, the transformer **intentionally does not modify any class**; therefore, this is a **configuration check** example, not a native weaving demo.

**File `NativePrefixAgent.java`:**

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class NativePrefixAgent {
    public static void premain(String options, Instrumentation inst) {
        System.out.println("prefixSupported="
                + inst.isNativeMethodPrefixSupported());
        ClassFileTransformer transformer = new ClassFileTransformer() {
            @Override
            public byte[] transform(ClassLoader loader, String name,
                    Class<?> type, ProtectionDomain domain, byte[] bytes) {
                return null;
            }
        };
        inst.addTransformer(transformer, false);
        if (inst.isNativeMethodPrefixSupported()) {
            inst.setNativeMethodPrefix(transformer, "$DemoNative$_");
            System.out.println("prefixConfigured=true");
        }
    }
}
~~~

**File `Target.java`:**

~~~java
public final class Target {
    public static void main(String[] args) {
        System.out.println("target=run");
    }
}
~~~

**File `MANIFEST.MF`:**

~~~text
Manifest-Version: 1.0
Premain-Class: NativePrefixAgent
Can-Set-Native-Method-Prefix: true

~~~

The manifest has a trailing blank line ending the main attributes. `Can-Retransform-Classes: true` is not needed in the example because the transformer uses `addTransformer(..., false)`.

### 8.1. Compile and Run

Place all three files in the same directory and run with JDK 17+:

~~~bash
javac --release 17 NativePrefixAgent.java Target.java
jar --create --file prefix-agent.jar --manifest MANIFEST.MF NativePrefixAgent.class 'NativePrefixAgent$1.class'
java -javaagent:prefix-agent.jar Target
~~~

When building in a Unix shell or Windows PowerShell, the single quotes in `'NativePrefixAgent$1.class'` prevent `$1` from being expanded as a shell variable. This is the anonymous class name generated by the compiler. If you replace it with a named nested class, the JAR packaging command must be updated.

**Stdout tested on OpenJDK 21 (HotSpot):**

~~~text
prefixSupported=true
prefixConfigured=true
target=run
~~~

Other environments/JVMs may return `prefixSupported=false`; in that case the code **skips** `setNativeMethodPrefix`, printing only `prefixSupported=false` and `target=run`. This is a runtime capability result and should not be hardcoded as `true` across all VMs.

**Easy-to-miss detail:** `ClassFileTransformer` in Java 17 **is not a functional interface** in the sense of having a single abstract method; therefore, you cannot replace the anonymous class in the example with a lambda `(loader, name, ...) -> null` like `Predicate`. Implement/override the appropriate overload.

### 8.2. Prefix Is Different From Immediately Renaming Every Native Method

After the example above:

- The agent has the prefix capability.
- A transformer has been registered and associated with a prefix.
- **No native wrapper has been generated** because `transform` always returns `null`.
- The methods of `Target` are unmodified and `target=run` still prints normally.
- The agent also does not touch any JNI library or implement a `NativeMethodBind` callback.

This is a test of **an API capability**, not to be presented as a "complete native method measurement" tool. To have a real wrapper, you must add bytecode transformation, class matching, and JNI binding tests.

## 9. JVM TI: Observing Native at the VM Layer Without a `Code` Attribute

**JVM Tool Interface (JVM TI / JVMTI)** is a native interface for debuggers, profilers, and agents at the JVM level. It has events/capabilities related to native methods, which are **different** from Java's `ClassFileTransformer`.

### 9.1. `NativeMethodBind`: Event When Binding a Method to a Native Address

According to the JVM TI specification:

- `JVMTI_EVENT_NATIVE_METHOD_BIND` can be sent when the VM **binds** a native method to an implementation function address.
- This can happen when the native method is called **for the first time** or when JNI `RegisterNatives` registers the function.
- The callback has parameters `jmethodID method`, `void *address` (the intended bind address), and `void **new_address_ptr` (which can be used to redirect).
- The agent must have the optional capability `can_generate_native_method_bind_events` and enable the corresponding event notification per the spec.
- **Replacing the address** is a native-level technique that requires a proxy matching the calling convention/ABI/JNI signature and managing function pointer lifetimes; it should not be done with untested sample code.

**Very important:** `NativeMethodBind` is an event **at binding time**, not **per invocation**. A native method can be called a million times after being bound, yet JVM TI only emits the bind event at the respective binding/registration points. Do not use a bind event counter as an invocation counter.

Model:

~~~text
JNI/VM resolves native method -> NativeMethodBind event
     |
     +-- original address: 0x... 
     +-- agent may choose an appropriate proxy address
     |
     v
Many subsequent native method invocations
     -> does not automatically emit NativeMethodBind each time
~~~

If the goal is time spent inside the native implementation itself, an appropriate native proxy wrapper can measure it, or a controlled native-stack/sampling profiler can be used. This is a different technique from placing `onEnter` into Java bytecode.

### 9.2. `MethodEntry` and `MethodExit` in JVM TI

JVM TI also has **method entry/exit** events, which can include **native methods** per the specification. They **do not require `Code` in the native method** because the JVM emits events from VM-level execution/observation mechanisms, not from Java instructions inserted by an agent.

However:

- You need the corresponding capabilities, to enable events with `SetEventNotificationMode`, and to check phase/thread filters per JVM TI.
- Method entry/exit events **can be very expensive** on many JVMs; the specification advises caution when enabling them broadly in performance-critical applications.
- Callbacks can occur in multi-threaded environments and special phases; native agent logic must respect ABI, thread safety, and lifecycle rules.
- JVM TI method entry/exit **is not** equivalent to adding instructions to `ACC_NATIVE`; it is a **different event mechanism**.

**Distinction:** `NativeMethodBind` aims to intercept/replace the address during resolution; `MethodEntry/Exit` observes the invocation boundary. Neither event should be described as automatically providing complete data on native CPU samples, stack traces, or native code logic.

Source: [JVM TI 17 Specification — Native Method Bind and Method Entry/Exit](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html).

### 9.3. Why Not Present a Pseudo-C JVMTI Agent as a "Ready-to-Run Example"?

A complete native JVMTI agent must provide `Agent_OnLoad`, request capabilities, install `jvmtiEventCallbacks`, enable events, handle JNI references/phases properly, and be built into a shared library. Abridged C snippets missing these steps **are not runnable**, so this article chooses separate **runnable JNI** and **runnable Java agent** examples above to demonstrate two verifiable parts, rather than labeling an unimplemented JVMTI snippet as "complete."

## 10. JNI Binding, Native Symbols, and Easy-to-Confuse Errors

In the JNI example, Java declares:

~~~java
private static native int nativeAdd(int left, int right);
~~~

The native function name in the packageless example is:

~~~c
JNIEXPORT jint JNICALL Java_NativeBoundaryDemo_nativeAdd(
        JNIEnv *env, jclass type, jint left, jint right);
~~~

This is an **illustrative C signature**; the implementation is in section 6. JNI also supports `RegisterNatives` to bind a class/method descriptor directly to a function pointer instead of relying solely on symbol names. Therefore, having a native function not named `Java_...` in a library **does not by itself prove** it is unregistered; you must check the actual registration path.

| Error/symptom | Layer with issue | Hint |
| --- | --- | --- |
| `UnsatisfiedLinkError` at `System.loadLibrary` | OS loader cannot find/load the library | Path, filename, CPU architecture, ABI, and native dependencies |
| `UnsatisfiedLinkError` when calling native method | JNI binding failed to resolve the right function/descriptor | Check `javac -h` header, exported symbols, `RegisterNatives` |
| `ClassFormatError` after transforming native declaration | Class-file output violates format | Do not create `Code` inside `ACC_NATIVE`, check flags/schema |
| `VerifyError` or `LinkageError` when weaving wrapper | Java bytecode/descriptor/stackmap or linking is wrong | Verify output, matching signature, loader/module visibility |
| `IllegalArgumentException` from `setNativeMethodPrefix` | Transformer not yet registered | `addTransformer` before setting prefix |
| `UnsupportedOperationException` from `setNativeMethodPrefix` | Native prefix capability not enabled | Check manifest/JVM and `isNativeMethodPrefixSupported` |
| `NullPointerException` at `setNativeMethodPrefix` | Null transformer passed | Use a non-null registered transformer |
| JNI method runs but metric stays 0 | Probe placed at caller/wrapper does not cover all paths | Determine coverage, test each call path |
| Native crash/JVM crash | Unsafe native code/ABI/lifetime | Debug native stack, sanitizers, crash logs, and ownership |

**Do not confuse two forms of `LinkageError`:** Failing to find a native implementation can throw `UnsatisfiedLinkError`, which is a subtype of `LinkageError`. However, `LinkageError` has many other causes (loader constraints, binary mismatch, duplicate class definition). Diagnose using the actual subclass and stack trace.

### 10.1. A JNI Symbol Is Not a JVM Instruction

JVM bytecode only records a call instruction with a symbolic reference to the Java method. When that method has `ACC_NATIVE`, the VM uses the native implementation resolution path. Instructions inside the C function are compiled by the native compiler into **ABI-specific machine code**, not `Code` in a class file.

Likewise, you cannot use `javap -c` to inspect the instructions of `libnativeboundary.so`. If you need to read machine code, that is the job of an appropriate native disassembler, requiring attention to symbol stripping/optimization, and **does not belong to Java `ClassFileTransformer`**.

## 11. When a Class Is Already Loaded: Schema Changes Are Not Exempt

`Instrumentation.retransformClasses(...)` and `redefineClasses(...)` may allow applying new bytecode to already loaded classes when supported by the JVM and when the class is modifiable. However, **do not assume** that every structural class change is valid.

A native wrapping transformation may require:

- Changing `ACC_NATIVE` of the original method to a Java wrapper.
- Renaming the native method or creating a new method to hold the native declaration.
- Adding `Code` for the wrapper and updating the constant pool/stack maps accordingly.
- Preserving the original function's JNI native binding.

Changes to the **method set/modifiers** are often restricted during retransformation/redefinition of a running class. On common HotSpot JVMs, adding/removing methods or changing modifiers/schema in this way may be rejected with `UnsupportedOperationException`. A transformer that works perfectly **when the class is first defined** may **not** be applicable to an already loaded class.

If the goal is to observe a native method that already exists in the JVM:

- You can instrument **existing Java call sites or wrappers** if they have bytecode and the class qualifies.
- Use an appropriate profiler/event at the JVM TI/native level, if capabilities and overhead allow.
- Consider restarting the JVM with the Java agent loaded **from startup** if native-method prefix wrapping is needed.
- Do not try to turn every already-loaded native method into a Java wrapper via a `retransformClasses` call and then treat the error as the JVM "not supporting Java agents."

The difference between **instrumenting a class file at initial definition** and **retransforming/redefining an existing class** is central when designing native support.

## 12. Instrumentation Architecture: Place Probes at the Boundary Matching the Goal

~~~text
Java caller A ---> Java wrapper W ---> native method N ---> C/JNI function
       |                |                    |                  |
  Call-site probe   Wrapper probe       JVM TI event       Native profiler /
  counts A->W       counts passes       entry/bind         C proxy/counter
                    through W
~~~

Where to place the probe depends on the question:

| System question | Appropriate choice |
| --- | --- |
| How many times does a service call a native API through a standard wrapper? | Instrument the controlled Java wrapper |
| How many times does a specific call site call native? | Transform **caller** bytecode |
| Want to keep the native API signature but auto-generate a Java wrapper at class load? | `ClassFileTransformer` + `setNativeMethodPrefix` if capability is supported |
| How many times does the JVM bind a native function? | JVM TI `NativeMethodBind`, **do not treat as invocation** |
| Measure method entry/exit including native in JVM TI | Use `MethodEntry/MethodExit` if VM/capability supports it, accepting overhead |
| Which C/C++ function is hot on CPU? | Native stack sampling/profiling or native tracing |
| Missing JNI function fails to resolve | Check `UnsatisfiedLinkError`, JNI exports, and `RegisterNatives` |
| Only need to know which methods in a class are native | Reflection `Modifier.isNative`, `javap -v`, or reading `ACC_NATIVE` from the class file |

**You should not always instrument native code:** if the goal is simply the latency of a Java API calling native, a wrapper/call-site probe is usually sufficient. Deep native hooks can increase overhead, ABI risk, and process crashes.

### 12.1. Example of Duration and Exceptions

With a wrapper like:

~~~java
long start = System.nanoTime();
try {
    return nativeOperation();
} finally {
    recordNanos(System.nanoTime() - start);
}
~~~

This is an **illustrative code snippet inside a method where `nativeOperation()`/`recordNanos` already exist**, not a complete program. The duration is **elapsed wall-clock time within the same JVM**, including time crossing the Java-to-native boundary and any waiting/scheduling time, without separating out native CPU time. `System.nanoTime()` is suitable for comparing elapsed time within one JVM; do not subtract two `nanoTime` values from different JVMs.

For a JNI call that throws `UnsatisfiedLinkError` (an `Error`), `finally` can still run during normal stack unwinding. For a JNI native function that causes a segmentation fault/process abort, Java `finally` **is not guaranteed to execute**. You need an observability model that tolerates lost events and distinguishes process crashes from method-level exceptions.

## 13. Safety, Compatibility, and Performance Notes

1. **Platform compatibility:** `.so`, `.dylib`, and `.dll` differ; JNI C compilation/linking requires headers/ABI matching the target JDK and CPU architecture. Java source may be JDK 17 compatible, but a native binary built on another machine is not guaranteed to load.
2. **Exact JNI signature:** static native takes `jclass`, instance native receives `jobject`; a wrong signature can cause memory corruption/crash, not just a Java exception.
3. **Do not turn prefixes into a global search:** multiple agents/native wrappers may have their own prefixes; use a sufficiently specific namespace and test the order of transformation/native resolution.
4. **Do not treat `isNativeMethodPrefixSupported` as an instrumentation action:** it is only a capability query. You must have a real transformer and successful native resolution.
5. **Do not log infinitely inside `transform`:** loggers/helpers can themselves trigger class loading; filter early and avoid reentrancy.
6. **Avoid measuring all JVM TI MethodEntry in production:** event volume/overhead can be large. Enable only for the needed scope/time with appropriate capabilities/filters.
7. **Data crossing the JNI boundary:** native code can hold references, spawn threads, and call back into Java; each has its own rules for JNI references, attaching/detaching threads, and error handling.
8. **Do not write to `classfileBuffer` in place:** the transformer must return a new byte array when making changes, not mutate the input. For a native method, you can change **structure at load time**, but there is no original `Code` to insert instructions into.
9. **Protect fallbacks:** if the JVM does not support native prefix, the agent should skip with reporting/an alternative mechanism, not crash the application just for lacking a capability.
10. **Accurate metric semantics:** JNI binding events, method entries, Java call-site calls, and native CPU samples are four non-equivalent data sources.
11. **JVM structure and version:** instrumenting a wrapper at initial load is usually easier than transforming the schema of an already loaded class; check retransform/redefine limits on the target VM.
12. **Permissions and security:** JNI/native libraries run inside the JVM process; an untrusted library can read/write memory or crash the process. Do not load JNI from untrusted sources just to "add metrics."
13. **Module/class-loader access:** the Java wrapper/helper must see the right classes/helpers/modules according to JPMS and loading rules; native symbol lookup also has its own namespace/lifetime.
14. **Sufficient testing:** the test suite should cover normal return, exception/link error, multiple threads, overloads, absent native library, class-load order, and multiple agents.

## 14. Diagnostic Checklist: Native Method Is Not Instrumented

A workflow applicable to Java 17+:

1. **Identify the method kind:** `Modifier.isNative(method.getModifiers())` or check `ACC_NATIVE` in `javap -v`.
2. **Inspect the class file:** a native method **has no `Code`**; do not look for `visitCode`/instructions of the method itself.
3. **Define the goal:** do you need to measure Java call sites, the Java-to-native boundary, native bind addresses, or C/C++ CPU?
4. **If a wrapper already exists:** instrument the wrapper/non-native caller; check whether any bypass paths exist.
5. **If the agent wants to auto-generate a wrapper:** check the transformer/matcher, `isNativeMethodPrefixSupported` capability, and manifest `Can-Set-Native-Method-Prefix: true`.
6. **Register in the right order:** `addTransformer` before `setNativeMethodPrefix`.
7. **Verify the output class:** the wrapper has `Code`, the renamed native method still has `ACC_NATIVE` and no `Code`; the class file is valid.
8. **Check JNI binding:** can the library be loaded, does the native symbol/`RegisterNatives` map properly, is there a prefix collision?
9. **If the class is already loaded:** check whether schema changes are disallowed; consider a startup agent or another measurement approach.
10. **If using JVM TI:** verify capabilities, event timing/phase, and overhead; do not treat `NativeMethodBind` as per-invocation.
11. **Cross-check results:** call the native function in a test with deterministic output, verify counts/exceptions and that application logic is unchanged.
12. **Operations:** ensure helpers/loggers/recorders are not self-instrumented, and define a policy for when native code crashes.

### A Decision Example

~~~text
Need to count calls to System.nanoTime()?
    |
    +-- Only specific application Java call sites?
    |      -> instrument the caller or a wrapper you control
    |
    +-- Want every call site to that native API through the JDK class?
    |      -> must investigate coverage scope, module/JDK internals,
    |         intrinsics, and runtime risks; do not assume weaving callers alone suffices
    |
    +-- Want CPU time inside the VM/native implementation?
           -> native/JVM TI profiler, not inserting JVM bytecode
              into a native method that has no Code
~~~

This is a **tool-selection model**, not executable code. For methods specially optimized by the JDK, the practical definition of "one native call" also needs to be determined per execution path.

## 15. Common Misconceptions

1. **"A native method has no `Code`, meaning it does not appear in `.class`."** False: it still has `method_info`, name, descriptor, and `ACC_NATIVE`.
2. **"You can insert instructions right before the first instruction of a native method."** False: that method has no first bytecode instruction.
3. **"Without `Code`, native cannot be measured."** False: measure via wrapper, caller, JVM TI, or native profiler depending on the goal.
4. **"`setNativeMethodPrefix` automatically creates a wrapper."** False: the transformer must still perform the class-file transformation.
5. **"`Can-Set-Native-Method-Prefix: true` guarantees every JVM supports it."** False: it also depends on JVM capability; check at runtime.
6. **"`setNativeMethodPrefix` immediately renames the native function in C."** False: it changes the prefix-based native resolution retry mechanism, not patches machine code.
7. **"A native method has `Code` after the transformer changes its flags?"** A method that is **no longer native** can have `Code` as a wrapper, but a method that **still keeps `ACC_NATIVE`** must not have `Code`.
8. **"A Java agent can transform every loaded native method via retransform."** False: retransform/redefine has schema and modifier restrictions.
9. **"`NativeMethodBind` counts native invocations."** False: the event occurs when binding the function.
10. **"JVMTI cannot observe native because there is no bytecode."** False: JVM TI has entry/exit and native binding events when supported.
11. **"A JNI C function is JVM bytecode printed by `javap -c`."** False: C is compiled by a native compiler into machine code.
12. **"`UnsatisfiedLinkError` proves the Java method did not compile properly."** Not necessarily: the Java declaration may be valid while the native library is missing or mismatched.
13. **"Just use a lambda to declare `ClassFileTransformer` in Java 17."** False: the interface does not have a single abstract method in Java 17; the example uses an implementing class.
14. **"A wrapper `finally` always runs even if the JVM crashes."** False: crash/halt does not follow normal Java stack unwinding.
15. **"You can capture all native elapsed time from one call site."** False: this misses other call paths and does not separate scheduling from CPU.
16. **"Every JVM native method is a JNI function in a separate library."** False: the runtime/JDK has multiple implementation and optimization styles; JNI is one standard mechanism shown in the demo.

## 16. Self-Check Questions

1. In JVMS, which access flag marks a native method?
2. If a method has `ACC_NATIVE`, is it allowed to have a `Code` attribute? Why?
3. Why does `javap -c` not display instructions for `nativeAdd` while displaying instructions for `observedAdd`?
4. Can `ClassFileTransformer` modify a Java caller method of a native method? Does that mean modifying the native implementation?
5. Why does a Java wrapper need `try/finally` if it wants to record an exit event even when an exception occurs?
6. Does `setNativeMethodPrefix` automatically generate a wrapper, or does the transformer need to produce the appropriate class output?
7. Which manifest attribute relates to native prefix, and which API queries this capability at runtime?
8. Why must `addTransformer` be called before `setNativeMethodPrefix`?
9. When a native method has already been defined, why is `retransformClasses` not guaranteed to allow changing it into a non-native wrapper?
10. How do JVM TI's `NativeMethodBind` and `MethodEntry` differ in event timing?
11. Why can you not use the `NativeMethodBind` count to calculate how many times a JNI function was called?
12. When a native library is missing, what exception typically appears at `System.loadLibrary` or when resolving the native method?
13. Why can Java code be compatible with `--release 17` while `libnativeboundary.so` still depends on the OS/CPU?
14. If a JNI function causes a segmentation fault, is Java `finally` guaranteed to run?
15. When you need to know CPU hotspots inside a C function, what should you use instead of `ClassFileTransformer`?

**Remember:** A Java `native` method has **a declaration in `.class` but no `Code` attribute**. Because there are no JVM instructions in that body itself, an agent cannot "insert a probe at the first bytecode line of the native method" the way it does for normal Java methods. Choose a **non-native wrapper or call site**, use **`setNativeMethodPrefix`** if you need to transform it into a wrapper at class load time and the JVM allows it, or choose **JVM TI/native tooling** to observe binding/invocation at the appropriate level. Do not confuse a native binding event with each invocation, or confuse a Java agent capability with permission to modify machine code.

### Official References

- [JVMS Java 17 — `4.6 Methods and `4.7.3 Code Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html)
- [Java 17 — Instrumentation: isNativeMethodPrefixSupported and setNativeMethodPrefix](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [Java 17 — java.lang.instrument manifest: Can-Set-Native-Method-Prefix](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [JNI Specification Java 17 — Resolving Native Method Names](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html)
- [JVM TI Specification Java 17 — NativeMethodBind, MethodEntry/MethodExit](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html)
