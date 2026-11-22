# Why Adding a Wrapper After Class Loading Faces Structural Change Restrictions

## 1. The problem: wanting to measure a native method after the class is already loaded

In Java Instrumentation, we can insert timing, tracing, or metric instructions into the **bytecode of a Java method**. However, a native method, such as:

~~~java
package demo;
public final class NativeTarget {
    public native int ping(int input);
}
~~~

is a method with the **`ACC_NATIVE`** flag and does not contain a **`Code`** attribute with a Java bytecode body. The actual execution of `ping` resides in a native implementation linked via JNI or another JVM mechanism. **There is no Java body to directly insert `invokestatic Probe.before()` or `Probe.after()`.**

A common solution is to **wrap** the native call with a **Java wrapper** that has bytecode: the wrapper records timing before/after and then calls the real native method through a renamed name. The `Instrumentation.setNativeMethodPrefix` API (corresponding to JVM TI `SetNativeMethodPrefix`) supports native method name resolution when transforming classes according to this pattern.

**However, adding a new wrapper to an already-loaded class usually requires changing the method table structure:** adding a method or changing the `native` flag of the old method. Java 17 JVM TI `RedefineClasses`/`RetransformClasses` **do not support those schema changes**. A late-attaching agent cannot bypass this restriction simply by calling `setNativeMethodPrefix`.

Objectives of this lesson:

1. Explain why a native method needs a Java wrapper to perform bytecode instrumentation.
2. Show how wrapping **at initial class definition** differs from wrapping **after the class has been loaded**.
3. Distinguish valid method body changes from restricted additions of methods/fields or modifier changes.
4. Understand the actual function of native method prefix and JVMTI `NativeMethodBind`.
5. Practice with Java 17+: adding a wrapper method to a loaded class is rejected; creating the Java/native wrapper shape too late is also rejected; using an **external helper class + modifying only an existing Java method body** succeeds.
6. Choose a solution when the JVM has already loaded the native class: instrument the caller, change the build/startup design, or use a controlled native binding hook.

## 2. Native methods have no Java Code attribute

Consider a normal Java method:

~~~java
public int compute(int input) {
    return input * 2;
}
~~~

After the compiler generates the `.class` file, the `compute` method has bytecode instructions such as `iload`, `imul`, `ireturn`. A bytecode transformer can inspect, transform, add calls, and generate a new classfile (with valid stack frames, constant pool, and descriptors).

In contrast:

~~~java
public native int ping(int input);
~~~

has a declaration and descriptor, but **no Java code** to transform directly. A Java agent using `ClassFileTransformer` cannot pretend that `native ping` has an existing Java method body.

~~~text
Java method:
  Caller -> compute(int) -> bytecode in .class -> result

Native method:
  Caller -> ping(int) -> native method resolution -> JNI function -> result
                                        |
                          Java Code attribute does not exist
~~~

If the goal is only to measure the **Java call-site** leading to `ping`, you can instrument the Java caller that has a body. But if you want a unified Java-level entry/exit hook for **every `ping` invocation**, you need to arrange the wrapper at the right time, or use another native interception mechanism.

**Do not conflate them:** `java.lang.instrument` operates at the Java classfile layer, whereas JVM TI is a broader native API with callbacks/capabilities. The two layers can support each other, but they are not the same concept.

## 3. The wrapper model with setNativeMethodPrefix

The official Java SE 17 documentation illustrates transforming a native declaration:

~~~java
native boolean foo(int x);
~~~

into two methods in the classfile **before the JVM defines the class**:

~~~java
boolean foo(int x) {
    Probe.enter(x);
    try {
        return $agent$foo(x);
    } finally {
        Probe.exit();
    }
}

native boolean $agent$foo(int x);
~~~

This is the **post-transform code shape**, not a standalone runnable Java file: it requires `Probe`, a native implementation, a matching JNI library, and an agent/classfile transformer. The name `$agent$` only illustrates the prefix; production must use a specific, low-collision prefix.

Mechanism:

- Callers still invoke **`foo`**, so the public API does not need to be renamed.
- `foo` is now a **non-native Java wrapper**, with a body to collect entry/exit, record errors, latency, and traces.
- The prefixed method **`$agent$foo`** is the **native declaration** that the wrapper calls.
- The JVM tries to link the name `$agent$foo` to a JNI implementation; thanks to the registered native method prefix, when normal resolution fails the JVM can try stripping the prefix to find the original implementation corresponding to `foo`.
- With `RegisterNatives`, there is also a corresponding retry mechanism under the prefix contract.
- The actual native method is still implemented by the native library; `setNativeMethodPrefix` **does not generate a JNI implementation**.

**What changed?** From **one** method `native foo` to **two** method declarations: Java `foo` and native `$agent$foo`. `foo` had its modifier changed from native to non-native, and `$agent$foo` is a new method. This is precisely what causes problems when the class is already loaded.

### 3.1. A prefix does not mean the wrapper is auto-generated

~~~java
inst.setNativeMethodPrefix(transformer, "$agent$");
~~~

The line above **only configures native name-resolution retry** for a registered transformer. It does not:

- auto-generate bytecode for `foo`;
- auto-add `$agent$foo` to the class;
- auto-replace the C/C++ body of the native function;
- bypass schema restrictions of a loaded class;
- auto-load a shared library or fix JNI signatures.

If `foo` is already loaded as native and has no valid Java wrapper, calling prefix alone does not provide Java-level tracing.

### 3.2. Why can you transform before the class is loaded?

Before **the first definition**, `ClassFileTransformer.transform` or JVM TI `ClassFileLoadHook` can produce a **new classfile to be defined by the JVM for the first time**. There is no existing instance layout, class identity, or active frame from an old definition that must be preserved, so the transformed schema can be accepted by the JVM if valid.

~~~text
First load:
   classfile with native foo
         |
   ClassFileTransformer / ClassFileLoadHook
         |
   create Java foo wrapper + prefixed native foo
         |
   JVM verifies and DEFINES CLASS with transformed schema
         |
   Java caller invokes foo -> wrapper -> native binding
~~~

**The decisive point is when the class is defined for the first time**, not just when the agent is attached. A startup agent should register the transformer early and filter specific classes before the classloader loads the target.

## 4. Once loaded, JVM TI restricts method and field changes

According to Java 17 JVM TI, both **`RedefineClasses`** and **`RetransformClasses`** can change **method bodies**, the constant pool, and certain attributes. They **cannot** arbitrarily:

- add, delete, or rename methods/fields;
- change method descriptors/signatures;
- change method/class modifiers, including the `native` flag;
- change superclass/interfaces;
- change certain attributes such as `NestHost`, `NestMembers`, `Record`, or `PermittedSubclasses`.

The specification may be relaxed in future releases, but you must not assume the JVM in use supports schema changes. **A Java agent cannot turn a structurally invalid request into a valid one by enabling more capabilities.**

| Way to modify a loaded class | Scope of change | Restriction risk |
|---|---|---|
| Add a new `wrapper()` inside the class | Add method | Not allowed under standard JVMTI limits |
| Change native `foo` to Java `foo` | Change `ACC_NATIVE`/method code shape | Not arbitrarily allowed |
| Add native `$prefix$foo` | Add method | Not allowed |
| Add field `probeState` | Change field/layout | Not allowed |
| Insert `Probe.enter` into an **existing Java method** body | Body-only, schema preserved | Potentially valid |
| Modify an existing Java method to call **another helper class** | Body-only in target | Potentially valid, requires helper visibility |
| Intercept at a Java caller that has a body | Caller's body | Potentially valid, depends on scope and loader |
| Register a native `NativeMethodBind` proxy | Native binding address, no Java method added | Different mechanism and capability |

### 4.1. Important error codes

At the JVM TI layer, there are the following codes:

- `JVMTI_ERROR_UNSUPPORTED_REDEFINITION_METHOD_ADDED`: replacement requires adding a method;
- `JVMTI_ERROR_UNSUPPORTED_REDEFINITION_METHOD_DELETED`: replacement deletes a method;
- `JVMTI_ERROR_UNSUPPORTED_REDEFINITION_SCHEMA_CHANGED`: field change;
- `JVMTI_ERROR_UNSUPPORTED_REDEFINITION_METHOD_MODIFIERS_CHANGED`: method modifier changed, possibly `native`;
- `JVMTI_ERROR_UNSUPPORTED_REDEFINITION_HIERARCHY_CHANGED`: hierarchy changed.

At the Java Instrumentation layer, `redefineClasses` or `retransformClasses` may throw **`UnsupportedOperationException`** for unsupported changes. Specific messages vary across JVMs; do not expect a Java exception whose name verbatim matches the JVMTI error code.

**`isModifiableClass(target) == true` is only a necessary condition**, not proof that you can add methods. A class can be modifiable for **body edits** while still not modifiable for **schema additions**.

### 4.2. Do not mix up error types

- `UnmodifiableClassException`: the target class is not modifiable.
- `UnsupportedOperationException`: VM/config does not allow the operation or the change is unsupported.
- `ClassFormatError`/`VerifyError`: malformed bytes or verifier failure.
- `NoClassDefFoundError`/`IllegalAccessError`: may be due to class name/helper/loader/linkage.
- `UnsatisfiedLinkError`: native function cannot be linked yet, usually requiring checking library/prefix/JNI names.
- `UnsupportedClassVersionError`: classfile major version exceeds runtime.

Do not rely on a malformed classfile error to judge wrapper addition capability. The lab below uses validly compiled files that are rejected due to **schema**.

## 5. setNativeMethodPrefix: capability and when to use it

`Instrumentation.setNativeMethodPrefix(ClassFileTransformer, String)` is an **optional capability**. For a Java agent:

1. The main manifest has **`Can-Set-Native-Method-Prefix: true`**.
2. The JVM returns `inst.isNativeMethodPrefixSupported() == true`.
3. `ClassFileTransformer` must be registered with `addTransformer` first.
4. The agent associates a **dedicated prefix** with the transformer using `setNativeMethodPrefix`.
5. The transformer generates a valid wrapper classfile **at load-time** if it needs to add methods/change the native modifier.
6. The prefix is kept as long as prefixed native methods may still need resolution.

Configuration pattern:

~~~java
public static void premain(String arg, Instrumentation inst) {
    if (!inst.isNativeMethodPrefixSupported()) {
        throw new IllegalStateException(
                "Native prefix not supported");
    }
    ClassFileTransformer tx = createNativeWrapperTransformer();
    inst.addTransformer(tx);
    inst.setNativeMethodPrefix(tx, "$myagent$");
}
~~~

**This is an illustrative snippet, not a standalone compilable program**: `createNativeWrapperTransformer` needs to be implemented to produce a valid classfile; `java.lang.instrument.*` must be imported. Do not use it with an already-loaded `Target` and assume schema changes will succeed.

Manifest for an agent of this kind:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.NativeWrapAgent
Can-Set-Native-Method-Prefix: true

~~~

Keep a trailing newline in the manifest. The capabilities **`Can-Redefine-Classes`**, **`Can-Retransform-Classes`**, and **`Can-Set-Native-Method-Prefix`** are distinct things. Enabling prefix does not relax class schema restrictions.

### 5.1. Prefix naming and JNI native resolution

When the `$myagent$foo` method cannot find a JNI implementation under the renamed name, the JVM can retry based on the prefix to locate the implementation of `foo`. This applies according to the corresponding rules for JNI name lookup and `RegisterNatives`.

- The prefix must be distinct enough not to match an existing method.
- The native function must have the correct JNI ABI/signature.
- The native library must be loaded in the appropriate context.
- Multiple transformers can stack multiple layers of wrappers/prefixes, so ordering must be controlled.
- Native resolution can happen lazily; do not remove the prefix as soon as the `transform` callback finishes.

If there is no valid native implementation, `UnsatisfiedLinkError` will still occur. The prefix **does not create C/C++ symbols for you**.

## 6. Choosing a solution if the class is already loaded

There are four different approaches, not mutually exclusive.

### A. Insert at the Java call-site

Replace the body of the Java method that **calls** the native target, inserting probes before and after the call instruction:

~~~text
Java caller:
  before:  result = nativeTarget.ping(x)
  after:   beforeNativeCall()
           result = nativeTarget.ping(x)
           afterNativeCall()
~~~

This is an **algorithmic diagram**, not a complete Java method. Advantage: does not modify the native method and does not require adding methods to the native target class. Disadvantage: only covers **call-sites that are actually instrumented**; calls from native code or other callers may not go through the hook.

### B. External helper class + body-only transform of an existing Java method

If the target is a Java method `compute` that already has a body, we can replace its body to call **another `Wrapper` class**. The target does not need any added methods or fields. This is the path the lab will verify.

However, **a native method has no Java body** to replace in this way. You must not use the success of `compute` to infer that `native ping` can also have its body modified.

### C. NativeMethodBind in JVM TI

At the native layer, JVM TI provides **`NativeMethodBind`**, an event fired when the VM binds a Java native method to a native function address. A native agent can change `*new_address_ptr` to use a native proxy with the correct JNI ABI.

This is **native binding interception**, which does not add Java methods to a loaded class. Conditions: the capability must be held, the callback registered, and the event enabled before the binding time you want to intercept; bindings that have already occurred are not automatically replayed when an agent attaches late.

### D. Startup/load-time wrapper or new deployment

If you want the exact **Java wrapper + native prefix** technique, the more provable option is to register the agent **before the class is first defined** or bake the wrapper into the **source/build artifact** before deployment. If the schema needs to change and the class is already loaded, consider a new JVM/process rather than pretending redefinition can migrate the old schema.

## 7. Java 17+ lab: verifying the restrictions with a real agent

This lab uses `Instrumentation.redefineClasses` with **replacement class bytes**. It tests:

1. Adding `wrapper(int)` **inside an already-loaded class** is rejected.
2. Attempting to turn `native ping` into a Java wrapper + a new native method is also rejected.
3. Keeping the old schema while modifying the **body of Java method `compute`** to call an **independent `Wrapper` helper class** succeeds.
4. Existing objects retain their old state; the computation still returns the right result.

**No JNI library is needed** because in the lab we only **load `NativeTarget.class`** and **do not call `native ping`**. This lab measures **schema change capability**, not native prefix resolution.

### 7.1. Directory tree

~~~text
loaded-wrapper-lab/
├── agent.mf
├── src/
│   ├── agent/demo/SwapAgent.java
│   ├── app/demo/Main.java
│   ├── app/demo/Wrapper.java
│   ├── v1/demo/Target.java
│   ├── bad/demo/Target.java
│   ├── good/demo/Target.java
│   ├── native1/demo/NativeTarget.java
│   └── nativebad/demo/NativeTarget.java
└── out/
    ├── agent/
    ├── base/
    ├── bad/
    ├── good/
    ├── nativebad/
    └── swap-agent.jar
~~~

**Having three `Target.java` files with the same package/class name** is intentional to build **three separate classfiles**; they must not be compiled together. The runtime classpath only uses **`out/base`**, while the agent reads `.class` files in `out/bad`, `out/good`, and `out/nativebad` as replacement bytes.

### 7.2. Agent: src/agent/demo/SwapAgent.java

~~~java
package demo;

import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class SwapAgent {
    private static Instrumentation inst;

    public static void premain(
            String args, Instrumentation instrumentation) {
        inst = instrumentation;
    }

    public static void change(
            Class<?> target, Path path) throws Exception {
        if (!inst.isRedefineClassesSupported()
                || !inst.isModifiableClass(target)) {
            throw new IllegalStateException(
                    "Redefinition unsupported");
        }
        inst.redefineClasses(new ClassDefinition(
                target, Files.readAllBytes(path)));
    }
}
~~~

This is the **complete agent for the lab**. `premain` captures `Instrumentation`; `change` reads the compiled classfile bytes, checks permissions, and calls `redefineClasses`. If a schema change is forbidden, the JVM throws an error and does not install the invalid definition.

Main manifest `agent.mf`:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.SwapAgent
Can-Redefine-Classes: true

~~~

`Can-Redefine-Classes` only requests permission to redefine; it does not grant permission to add methods/fields to a loaded class. Running with `-javaagent` loads the agent before `main`, but `change` is only called **after the app has created objects and loaded the target**.

### 7.3. Class V1: src/v1/demo/Target.java

~~~java
package demo;

public final class Target {
    private int factor = 2;

    public void setFactor(int factor) {
        this.factor = factor;
    }

    public int raw(int input) {
        return input * factor;
    }

    public int compute(int input) {
        return raw(input);
    }
}
~~~

The initial class has the methods `setFactor`, `raw`, `compute`, and the default constructor. Main sets `factor=7`, so `compute(5) == 35`.

### 7.4. Rejected V2: src/bad/demo/Target.java

~~~java
package demo;

public final class Target {
    private int factor = 2;

    public void setFactor(int factor) {
        this.factor = factor;
    }

    public int raw(int input) {
        return input * factor;
    }

    public int compute(int input) {
        return wrapper(input);
    }

    private int wrapper(int input) {
        return raw(input);
    }
}
~~~

This version only adds a simple private method `wrapper(int)`. However, because the **method list differs from V1**, a standard VM rejects the redefinition. It does not matter whether the new method has minor side effects or not: this is a **schema change**.

### 7.5. Body-only V3: src/good/demo/Target.java

~~~java
package demo;

public final class Target {
    private int factor = 2;

    public void setFactor(int factor) {
        this.factor = factor;
    }

    public int raw(int input) {
        return input * factor;
    }

    public int compute(int input) {
        return Wrapper.around(this, input);
    }
}
~~~

V3 has the **exact same field list/method list/descriptors as V1**. Only the body of `compute` changes from `raw(input)` to `Wrapper.around(this,input)`. Because `Wrapper` is **another class** rather than a new method on `Target`, the target schema does not change.

The correctness of V3 also depends on the helper being loadable by the JVM, having appropriate visibility, and not recursing back into `compute`.

### 7.6. Helper: src/app/demo/Wrapper.java

~~~java
package demo;

public final class Wrapper {
    private Wrapper() {
    }

    public static int around(Target target, int input) {
        System.out.println("wrapper:before input=" + input);

        int result = target.raw(input);

        System.out.println("wrapper:after result=" + result);

        return result;
    }
}
~~~

`Wrapper` is an **independent** class, already compiled along with the application into `out/base`. `around` calls **`raw`** to preserve the original logic, **not `compute`**: because V3 `compute` calls `around`, calling back into `compute` would create infinite recursion.

### 7.7. NativeTarget V1: src/native1/demo/NativeTarget.java

~~~java
package demo;

public final class NativeTarget {
    public native int ping(int input);
}
~~~

`ping` is not called in the lab, so there is no native library requirement. We only need to load `NativeTarget.class` so the VM has its class identity and then attempt redefinition.

### 7.8. Too-late native wrapper: src/nativebad/demo/NativeTarget.java

~~~java
package demo;

public final class NativeTarget {
    public int ping(int input) {
        return wrappedPing(input);
    }

    private native int wrappedPing(int input);
}
~~~

Starting from an initial `native ping`, V2 attempts to:

- change `ping` from native to a Java method with a body;
- add a new method `wrappedPing` with the native flag.

**Both types of changes are problematic** for the schema of an already-loaded class. This is a test file for VM rejection, not a standalone runnable JNI wrapper.

### 7.9. Main: src/app/demo/Main.java

~~~java
package demo;

import java.nio.file.Path;

public final class Main {
    public static void main(String[] args)
            throws Exception {
        Target target = new Target();
        target.setFactor(7);

        System.out.println("before=" + target.compute(5));

        try {
            SwapAgent.change(Target.class, Path.of(args[0]));
            System.out.println("added-method:accepted");
        } catch (UnsupportedOperationException expected) {
            System.out.println("added-method:rejected");
        }

        System.out.println(
                "after-rejected=" + target.compute(5));

        try {
            SwapAgent.change(
                    NativeTarget.class, Path.of(args[2]));
            System.out.println("native-wrap:accepted");
        } catch (UnsupportedOperationException expected) {
            System.out.println("native-wrap:rejected");
        }

        SwapAgent.change(
                Target.class, Path.of(args[1]));
        System.out.println("body-only:accepted");
        System.out.println(
                "after-valid=" + target.compute(5));
    }
}
~~~

Sequence:

1. Create **one Target object**, set factor=7, call V1 `compute(5)`.
2. Attempt to redefine to V2 with an added method → JVM rejects; V1 continues to work.
3. Attempt to redefine the native class to a Java wrapper + new prefixed native method → JVM rejects.
4. Redefine target to V3 **without adding methods/fields**, only changing the body of `compute`.
5. Call `compute(5)` on the **original object**, the helper prints before/after, and the result is still 35.

The lab catches `UnsupportedOperationException` to keep output consistent across HotSpot VMs that support redefinition. In a real application, you should log the detailed reason and not treat a rejection as "changed successfully".

## 8. Build commands and verified output

At the root of the `loaded-wrapper-lab` project, create output directories using Bash:

~~~bash
mkdir -p out/agent out/base out/bad out/good out/nativebad
~~~

Or PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/agent, out/base, out/bad, out/good, out/nativebad
~~~

Compile with **JDK 17+ supporting `--release 17`**:

~~~bash
javac --release 17 -d out/agent src/agent/demo/SwapAgent.java
javac --release 17 -cp out/agent -d out/base src/v1/demo/Target.java src/native1/demo/NativeTarget.java src/app/demo/Wrapper.java src/app/demo/Main.java
javac --release 17 -d out/bad src/bad/demo/Target.java
javac --release 17 -cp out/base -d out/good src/good/demo/Target.java
javac --release 17 -d out/nativebad src/nativebad/demo/NativeTarget.java
jar --create --file out/swap-agent.jar --manifest agent.mf -C out/agent .
~~~

In the output directories:

- `out/base` has target V1, native V1, `Main`, and `Wrapper`.
- `out/bad` has target V2 with the new method.
- `out/good` has target V3 with the same schema.
- `out/nativebad` has the invalid post-load native-wrapper replacement.
- The agent JAR contains `SwapAgent.class` and the manifest; it does not contain the replacement classes.

Run:

~~~bash
java -Xverify:all -javaagent:out/swap-agent.jar -cp out/base demo.Main out/bad/demo/Target.class out/good/demo/Target.class out/nativebad/demo/NativeTarget.class
~~~

**Measured stdout from a test run on JDK 24.0.2 with bytecode compiled with `--release 17`:**

~~~text
before=35
added-method:rejected
after-rejected=35
native-wrap:rejected
body-only:accepted
wrapper:before input=5
wrapper:after result=35
after-valid=35
~~~

The lab compiled and ran successfully with `-Xverify:all`, exit code 0. The output above shows that **exactly the two schema change cases are rejected by the VM**, while the body-only wrapper call is accepted.

| Line | Evidence |
|---|---|
| `before=35` | V1 is running, object has factor=7 |
| `added-method:rejected` | V2 adding a method inside the already-loaded class is rejected |
| `after-rejected=35` | Failed update did not overwrite V1 |
| `native-wrap:rejected` | Post-load native-to-Java wrapper violates structure |
| `body-only:accepted` | Replacing method body while preserving schema is accepted |
| `wrapper:before input=5` | External helper class outside target is invoked |
| `wrapper:after result=35` | Helper calls the old business path and gets the right result |
| `after-valid=35` | New invocation on the old object uses the modified body |

### 8.1. Using javap to inspect the schema

~~~bash
javap -p -s -classpath out/base demo.Target
javap -p -s -classpath out/bad demo.Target
javap -p -s -classpath out/good demo.Target
javap -p -s -classpath out/base demo.NativeTarget
javap -p -s -classpath out/nativebad demo.NativeTarget
~~~

Look for `wrapper(int)` present only in V2 bad; V3 good has no new methods. Compare `native ping` and Java `ping`/`native wrappedPing` in the two native versions. To inspect method bodies, use `javap -c -p`.

**Remember:** Compiling V2/V3 into valid classfiles **for initial load** does not mean you can **redefine an already-loaded class** with those bytes. These are two stages with different constraints.

## 9. JVMTI NativeMethodBind as an alternative

JVM TI has the **`NativeMethodBind`** event when the VM binds a Java native method to a C/C++ implementation address — for example, on the first native call or during JNI `RegisterNatives`. A native agent can specify **a different function address** as a replacement binding.

Callback signature (C API illustration):

~~~c
void JNICALL NativeMethodBind(
    jvmtiEnv* jvmti_env,
    JNIEnv* jni_env,
    jthread thread,
    jmethodID method,
    void* address,
    void** new_address_ptr);
~~~

This is **not a complete native agent**. To run, you need a C/C++ library, JVMTI env, capability, callback registration, and ABI/JNI signature handling.

It can support cases where the native target class **has already been loaded** without adding a new Java method:

- The event is tied to **native function binding** time, not changing the class method schema.
- If the agent possesses the **`can_generate_native_method_bind_events`** capability and enables the event in time, it can replace `*new_address_ptr` with a native proxy address.
- The native proxy must match the JNI calling convention, `jobject/jclass` receiver, parameter types, return type, and exception behavior.
- If binding **already occurred before the agent attached/enabled the event**, the event does not automatically replay for old binds.
- Native function pointer redirection has its own conditions; it is not an arbitrary Java wrapper syntax.
- Replacing the wrong address or making incorrect JNI calls can crash the JVM, so thorough native-level testing is required.

**Do not confuse the two mechanisms**:

| Mechanism | Where does it intervene? | Does it create a new Java wrapper? |
|---|---|---|
| `setNativeMethodPrefix` + load-time transformer | Classfile before define and native name-resolution fallback | Possibly, if the transformer generates the classfile |
| JVM TI `NativeMethodBind` | Native implementation function pointer at bind time | No |
| `redefineClasses` modifying existing Java body | Bytecode of a Java method in a loaded class | No need to add a method |
| Java caller instrumentation | Bytecode at the native method call site | No need to modify the native target |

## 10. Implications of late attachment

An agent attached after an application has been running for a while may find `NativeTarget` already loaded. Things to check in order:

1. Does the JVM allow attach/dynamic agent loading? Newer JDKs have related flags/warnings/policies.
2. Which exact class identity/class loader holds the target? Two loaders can define classes with the same name.
3. Has the class been **loaded** yet, and has the native method been **bound** to an implementation yet? These are two different milestones.
4. Are there Java call-sites that can still be transformed?
5. Does the JVM support `isRedefineClassesSupported`, `isRetransformClassesSupported`, and `isModifiableClass` for the relevant class?
6. Do you need to **add a wrapper method** inside the target? If so, redefine/retransform normally cannot be used at this stage.
7. Can you use an external helper class and replace an **existing Java body**?
8. If you need to observe native binding, does the JVM TI agent have the `NativeMethodBind` capability and catch the bind time?
9. If not, can you move the logic to **startup/pre-load** or build-time weaving?

Avoid faulty logic: “`setNativeMethodPrefix` is supported, so I can insert a new Java method into any loaded class.” The prefix capability only controls name resolution; it does not alter the conditions allowing schema transformation.

### 10.1. getAllLoadedClasses is not a lock

`Instrumentation.getAllLoadedClasses()` reports the set of classes currently loaded by the JVM at the time of the call. Not seeing a class in the list **does not lock other threads from loading it immediately afterward**. If you need to guarantee the transformer runs before the first define, design the agent/startup/classloading order properly rather than relying on a check followed by a sleep.

## 11. Additional conditions for external helpers/wrappers

The body-only `compute` pattern in the lab succeeded because both `Target` and `Wrapper` were in the same package and the same application classloader. In real systems, it may differ:

- The app may have custom classloaders or different module layers; a helper loaded by the agent/system loader may not be visible to the target.
- If inserting calls into a named module, proper readability/export relationships are required; see `Instrumentation.redefineModule` when expanding the module graph, without granting excessive permissions.
- The agent should avoid instrumenting the helper itself to prevent recursion.
- The helper may need to hold `ThreadLocal`/tracing context, and must clean up state to avoid leaks.
- If the helper throws an exception, it can cause an otherwise working business method to fail.
- A wrapper performing synchronous I/O on a hot path can significantly increase latency.
- A JNI proxy must also preserve pending native exceptions, local/global refs, and ABI.
- If the wrapper needs to capture both success and failure, `try/finally` is needed while preserving return value/exception semantics.

Example structure of a Java helper (illustrative only, requires a `Probe` class):

~~~java
static int around(Target target, int value) {
    Probe.enter();
    try {
        return target.raw(value);
    } finally {
        Probe.exit();
    }
}
~~~

`Probe.exit()` must also be safe, avoiding masking the original error with a new exception.

### 11.1. Avoiding recursion

If the new `Target.compute` calls `Wrapper.around`, and `Wrapper.around` calls `target.compute`, the cycle will continue infinitely until `StackOverflowError`. The lab uses `target.raw` because it is an **existing execution path** that does not call back into the wrapped entry method.

If there is no original method to delegate to safely, insert probes directly into the **existing Java method body**, preserving the original instructions, instead of creating a helper that calls back into the entry method itself.

## 12. Notes on JVM TI events, tracing, and native method lifecycle

- JVM TI `MethodEntry`/`MethodExit` can assist with tracking method-level events if the VM has the appropriate capabilities, but the overhead is completely different from bytecode probes and events/threads must be configured properly; do not automatically assume all native behavior will be visible like Java bytecode.
- `NativeMethodBind` observes **binding time**, and does not automatically record an event for **every invocation**. A successful bind callback is not full method invocation tracing.
- JNI native functions can hold locks, global references, pinned arrays, or native memory; a Java wrapper does not automatically manage those resources properly.
- A native method can make callbacks into Java or spawn threads. A Java-level timing wrapper measures the duration from caller to native completion on that thread, which does not equate to the latency of every asynchronous task initiated by native code.
- Stack frames already running prior to a redefinition/retransformation may continue executing the old bytecode; new probes in a Java caller do not retroactively appear in an old active frame.
- You need to test overhead and JNI error propagation when enabling instrumentation on production traffic.

## 13. Common misconceptions

**Misconception 1 — “A native method can have probes inserted into its body just like a Java method.”** No: native methods have no Java `Code` attribute.

**Misconception 2 — “A Java wrapper can be created at any time.”** No: if it requires adding a method or changing the native modifier in an already-loaded class, it will hit schema limits.

**Misconception 3 — “Enabling `Can-Redefine-Classes` allows adding fields/methods.”** No: the capability only grants permission for the operation; it does not relax structural change restrictions.

**Misconception 4 — “setNativeMethodPrefix automatically modifies bytecode.”** No: the transformer must still generate the classfile and JNI linking must be valid.

**Misconception 5 — “The prefix guarantees the native library exists.”** No: the JNI implementation must still be loaded/linked; `UnsatisfiedLinkError` can still occur.

**Misconception 6 — “An external helper can even wrap a native method that has no body.”** Not directly; the helper must sit at the **call-site**, or in another Java method with a body, or use a native-level hook.

**Misconception 7 — “If classfile V2 compiles successfully, redefinition is guaranteed to work.”** False: compilation only confirms it is a classfile that can be defined from scratch, not that it can alter the schema of an already-loaded class.

**Misconception 8 — “NativeMethodBind is an event for every native call.”** No: it is a **binding** event, not an entry/exit for every invocation.

**Misconception 9 — “Attaching after binding automatically replays NativeMethodBind.”** No. You must consider the binding lifecycle and appropriate registration mechanisms.

**Misconception 10 — “Adding an external helper class is always safe.”** Not necessarily: loader/module visibility, recursion, performance, GC, JNI state, and exception handling must be verified.

## 14. Practice exercises

### A. Predict output before running

With `Main` in section 7, predict the result of `Target.compute(5)` before and after the two redefinitions. Explain why `after-rejected` is still 35, whereas after the body-only update there are additional wrapper logs.

**Answer:** The V2 schema change is rejected, so V1 remains in use. V3 adds no methods/fields, only replacing the `compute` body to call the helper; the business result remains 35.

### B. Verify schema yourself with javap

Use `javap -p -s` to compare V1, V2, and V3 of Target. Point out the **`wrapper(int)`** method present in V2 but not in V1/V3. Use `javap -c -p` to locate the call to `Wrapper.around` in the V3 body.

### C. Test the error when a native method has no library

In an isolated test environment, try calling `new NativeTarget().ping(1)` without a JNI implementation. Observe `UnsatisfiedLinkError`. Why is it a **native resolution error**, not evidence of a schema limit?

### D. Choose how to instrument when the target is already loaded

A late-attaching agent wants to measure all calls to `foo`. Compare three solutions: instrumenting Java call-sites; JVM TI `NativeMethodBind` if binding conditions still hold; restarting the JVM with a load-time wrapper. State the coverage, permissions/capabilities, and limitations of each approach.

### E. Distinguish native prefix from JNI symbol

Suppose the output class has `native $trace$foo` while the shared library only has the JNI implementation of `foo`. Which transformer must the prefix be registered with? If the prefix is not registered yet, what can happen when the JVM resolves the native call?

**Answer:** register the prefix for the transformer that created the wrapper; if missing, lookup of the prefixed name may fail and cause `UnsatisfiedLinkError`.

### F. Find recursion in an external helper

Change `Wrapper.around` to call `target.compute` instead of `target.raw`. Analyze the call graph and explain the risk of `StackOverflowError`. Then restore the correct version.

### G. Add a field to store probe state

Add `long startTime` only in Target V3; compile it successfully and then try to redefine. Why is wanting convenient state storage blocked by schema restrictions? Propose storing state outside the class or measuring using local variables in the existing body (with valid bytecode/frames).

### Quick self-check

1. **Why is a wrapper needed to insert Java probes around a native method?** — Native methods have no Java bytecode.
2. **When is the best time for a wrapper to alter the method table?** — Before the class is defined for the first time.
3. **After class loading, is adding a wrapper method via redefine guaranteed?** — No.
4. **Is changing `ACC_NATIVE` of a loaded method a body-only change?** — No.
5. **Does `Can-Set-Native-Method-Prefix` replace `Can-Redefine-Classes`?** — No.
6. **Which kind of method does the external helper pattern tested in the lab apply to?** — Java methods with a body and an unchanged schema.
7. **Does `NativeMethodBind` change the method list of a Java class?** — No, it intercepts native function binding.
8. **If there is no JNI library yet, does calling prefix alone fix the error?** — No.
9. **When redefinition throws an exception, are any classes in the set successfully replaced?** — According to Java Instrumentation, no.
10. **How do you check for schema differences?** — `javap -p -s`, comparing field/method descriptors and modifiers.

## 15. Checklist for Java agents / native agents

### Before implementation

- [ ] Determine whether the target has Java bytecode or is a native declaration.
- [ ] Check whether the class is already loaded and whether the native method is already bound.
- [ ] Confirm whether you intend to use a pre-load transformer or late redefine/retransform.
- [ ] Compare before/after schemas: methods, fields, descriptors, native flags.
- [ ] If using a prefix, verify manifest `Can-Set-Native-Method-Prefix: true` and `isNativeMethodPrefixSupported`.
- [ ] If using redefine, verify `Can-Redefine-Classes` and `isModifiableClass`; do not confuse capability with schema support.
- [ ] If using native binding events, verify the JVM TI capability and callback registration.
- [ ] Verify the JNI implementation has the correct symbol/signature/lifecycle.
- [ ] Prepare a fallback when the target is already loaded and a wrapper cannot be added.

### During instrumentation

- [ ] Filter classes by binary name **and class loader/module identity**.
- [ ] Produce valid class bytes without mutating the input buffer.
- [ ] Do not add methods/fields to an already-loaded target when the VM does not support it.
- [ ] Do not call `setNativeMethodPrefix` on an unregistered transformer.
- [ ] Do not log or perform blocking I/O at high frequency in probes.
- [ ] Avoid instrumenting the helper class itself and avoid recursion.
- [ ] Preserve try/finally/exception flow, return type, and stack frames.
- [ ] Avoid using a JNI proxy function with the wrong ABI that crashes the VM.

### After instrumentation

- [ ] Use `javap -p -s` and `javap -c -p` to verify schema/bytecode.
- [ ] Test with `-Xverify:all` on the target runtime.
- [ ] Test real JNI binding if a native wrapper is deployed.
- [ ] Distinguish `UnsupportedOperationException` from `UnsatisfiedLinkError`/`VerifyError`.
- [ ] Check helper class loader/module visibility.
- [ ] Confirm the probe preserves exact return values and exception behavior.
- [ ] Measure overhead, GC, memory leaks, JNI references, and latency.
- [ ] Document call-site coverage/native invocations that are not observed.
- [ ] Prepare a controlled rollback/restart plan.

## 16. Summary and authoritative sources

**Why add a wrapper?** Because a native method contains no Java bytecode; a Java wrapper provides a method body to add timing/tracing and then forwards the call to the native implementation via a prefixed method. **Why is an already-loaded class a problem?** Because adding a wrapper inside the class itself usually adds a method or changes the `native` modifier, whereas Java 17 JVM TI `RedefineClasses` and `RetransformClasses` do not support these structural changes.

When a class is already loaded, choose a **valid intervention point**: an existing Java method body, a Java call-site, a separate helper class, JVM TI `NativeMethodBind` if appropriate, or a load-time wrapper design for the next startup. **`setNativeMethodPrefix` does not bypass schema limits by itself.**

Authoritative documentation:

- [Java SE 17 — Instrumentation.setNativeMethodPrefix](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#setNativeMethodPrefix(java.lang.instrument.ClassFileTransformer,java.lang.String)): native wrappers, prefix-based JNI resolution, capability, and transformer registration.
- [Java SE 17 — Instrumentation.redefineClasses](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#redefineClasses(java.lang.instrument.ClassDefinition...)): class replacement, errors, and limitations.
- [Java SE 17 — java.lang.instrument](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): Java agents and manifest capabilities.
- [JVM TI Java 17 — RedefineClasses](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html#RedefineClasses): schema restrictions and error codes.
- [JVM TI Java 17 — RetransformClasses](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html#RetransformClasses): live class transform limits.
- [JVM TI Java 17 — SetNativeMethodPrefix](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html#SetNativeMethodPrefix): support for prefixed native binding.
- [JVM TI Java 17 — NativeMethodBind](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html#NativeMethodBind): native bind event, proxy address, and capability.
- [JNI Specification — Resolving Native Method Names](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html#resolving-native-method-names): rules for locating JNI functions.
