# How a Java Agent Differs from a Native Agent Library Using -agentlib or -agentpath

**Topic:** Java Advance → instrumentation → **Native and JVM TI**.

Profiling, debugging, tracing, and bytecode instrumentation tools often declare an agent at JVM startup. There are three options that are very easy to confuse:

- **`-javaagent:/path/to/agent.jar[=options]`**: loads a **Java agent JAR**, relying on `Premain-Class` in the manifest and `public static void premain(...)`. The standard Java path for intercepting bytecode is `java.lang.instrument.Instrumentation`.
- **`-agentlib:agentname[=options]`**: loads a **native agent shared library** by library name and the OS/JVM native library search mechanism, then invokes the exported `Agent_OnLoad`. A native agent can use **JVMTI** and **JNI**.
- **`-agentpath:/absolute/path/libagent.so[=options]`**: also loads a **native shared library**, but specifies the file by an explicit path instead of a short name.

**You cannot swap the three options for the same file.** A Java agent JAR does not turn into a `.so`/`.dll` on its own; a native library does not have a `Premain-Class` manifest and the JVM does not call `premain` from it. The difference between `-agentlib` and `-agentpath` is mainly **how the native file is located**, not a different pair of JVMTI APIs.

This lesson explains the differences in **entry points, lifecycle, APIs, capabilities, packaging, ABI, load rules, concurrency, security, and common errors**. After that are two independent Java 17+ and native C labs, with complete source code, build commands, expected stdout, and verification steps.

> **Environment scope:** The Java lab runs on JDK 17+; the C JVMTI lab requires JDK headers and a C compiler, with the primary instructions using GCC/Linux. The native library must be compiled separately for the appropriate OS, CPU architecture, runtime library, and ABI. All examples use a **startup agent** and do not require dynamic attach.

## 1. Fundamental Comparison Table

| Aspect | Java agent `-javaagent` | Native `-agentlib` / `-agentpath` |
| --- | --- | --- |
| Deployment file | JAR containing `.class` files and manifest | Native library: `.so`, `.dylib`, or `.dll` |
| Entry point at JVM start | `premain(String, Instrumentation)` or `premain(String)` | `Agent_OnLoad(JavaVM*, char*, void*)` |
| Primary API | `java.lang.instrument.Instrumentation`, `ClassFileTransformer` | `jvmtiEnv*`, `jvmtiEventCallbacks`, JNI |
| Loading mechanism | JVM reads the agent JAR and manifest | JVM/OS loader loads the binary and resolves the exported C symbol |
| Platform compatibility | Bytecode JAR can run across OSes if JDK/JVM and dependencies match | Must be built and tested per OS/CPU/ABI/libc |
| Class manipulation capability | Transformer, redefine/retransform if supported by VM | `ClassFileLoadHook`, JVMTI events/capabilities if supported by VM |
| Memory safety | Java memory model and GC, though instrumentation bugs can still occur | Native pointers/memory; a single bug can crash the entire process |
| Configuration | Agent JAR manifest and `options` string | Exported functions, native dependencies, `options` string |
| Post-startup loading | `Agent-Class` and `agentmain`, when attach is allowed | `Agent_OnAttach`, when native attach is allowed |
| Common errors | Wrong JAR, missing manifest, invalid `premain`, missing class | Library not found, missing symbol, wrong architecture, JVMTI error |

### 1.1. Both Can Coexist

A single JVM can run both a Java agent and a JVMTI agent. Choosing `-javaagent` does not preclude the program from using JNI; a native JVMTI agent can also interact with Java objects when the phase/API allows. However, the **JVM agent startup protocol** remains different. When two agents transform the same class, you must consider the pipeline, callback order, class file validity, and potential duplicate instrumentation.

## 2. Java Agent Startup Flow: JAR → manifest → `premain`

Sample command:

```bash
java -javaagent:java-agent.jar=demo -cp out lab.App
```

Flow:

```text
JVM startup
    │
    ├── read META-INF/MANIFEST.MF in java-agent.jar
    │      Premain-Class: lab.JavaAgent
    │
    ├── load class lab.JavaAgent
    ├── invoke premain(agentArgs, Instrumentation)
    │      └── may call addTransformer(...)
    │
    └── invoke main(...) of lab.App
```

The `java.lang.instrument` Javadoc allows two Java signatures:

```java
public static void premain(
        String agentArgs, Instrumentation instrumentation);

public static void premain(String agentArgs);
```

These are **illustrative API signatures**, not a standalone compilable Java source file. The JVM prefers the overload that accepts `Instrumentation`. With startup `-javaagent`, the JVM invokes `premain` before `main`. If the agent fails to start or `premain` throws an uncaught error, the JVM may **abort before running the application**.

Common Java agent manifest entries:

| Entry | When is it used? |
| --- | --- |
| `Premain-Class` | **Required** for startup `-javaagent` |
| `Agent-Class` | For dynamic loading of a Java agent after startup if supported by the implementation |
| `Can-Redefine-Classes` | Agent requests redefine capability, defaults to `false` |
| `Can-Retransform-Classes` | Agent requests retransform capability, defaults to `false` |
| `Can-Set-Native-Method-Prefix` | Requests native method prefix capability |
| `Boot-Class-Path` | Appends class search paths for the bootstrap loader per spec |

**Manifest flags are not a guarantee of granted permissions.** When redefine/retransform is needed, you still must call `Instrumentation.isRedefineClassesSupported()` / `isRetransformClassesSupported()` and check `isModifiableClass(clazz)`.

### 2.1. What Does Java `Instrumentation` Do?

A Java agent can:

- Register a `ClassFileTransformer` via `addTransformer(transformer)`, or `addTransformer(transformer,true)` if retransformation is needed and supported by the JVM.
- Observe `getAllLoadedClasses()` / `getInitiatedClasses(loader)`.
- Request `retransformClasses(...)` or `redefineClasses(...)` within schema/capability limits.
- Query `isModifiableClass`, module modification capabilities, and append JARs to the class-loader search.
- Read `classfileBuffer` in the callback. If no transformation is made, **return `null`**; if transformed, **return a new `byte[]` array** containing a valid class file. **Do not mutate the array provided by the JVM in place.**

Normally, you do not need native pointers or C code just to intercept or load Java classes. However, a Java agent still carries risks such as recursive class loading, logger deadlocks, unverified code, or invalid bytecode.

## 3. Native JVMTI Agent: binary → `Agent_OnLoad` → callback

Example option:

```bash
java -agentpath:/opt/agents/libnativeprobe.so=demo -cp out lab.App
```

The JVM loads the shared library into the **same process**, then looks up the exported symbol `Agent_OnLoad`. C signature:

```c
JNIEXPORT jint JNICALL Agent_OnLoad(
        JavaVM *vm, char *options, void *reserved);
```

This is a **C fragment**, requiring the `jni.h` and `jvmti.h` headers. `options` contains the string after the `=` sign; `reserved` is unused in this lab. An agent that initializes successfully typically returns `JNI_OK`; otherwise, it returns an appropriate error code, and the JVM may not enter `main`.

Other entry points:

```c
JNIEXPORT jint JNICALL Agent_OnAttach(
        JavaVM *vm, char *options, void *reserved);

JNIEXPORT void JNICALL Agent_OnUnload(JavaVM *vm);
```

- `Agent_OnAttach` is for loading a native agent **into a running JVM** if the VM/policy permits.
- `Agent_OnUnload` is called when the agent is about to be unloaded according to its lifecycle, suitable for cleaning up resources.
- Do not treat `Agent_OnAttach` as the default callback for `-agentpath` at startup.
- These entry points do not replace Java `premain`/`agentmain`.

### 3.1. `JavaVM*`, `JNIEnv*`, and `jvmtiEnv*`

| Native type | Purpose |
| --- | --- |
| `JavaVM*` | JVM invocation interface handle, passed by the JVM into the C agent |
| `JNIEnv*` | JNI interface of the **current thread** for interacting with Java objects/classes |
| `jvmtiEnv*` | JVMTI interface for acquiring capabilities, registering events, and querying the VM |
| `jvmtiError` | JVMTI function result code, `JVMTI_ERROR_NONE` means success |
| `jvmtiCapabilities` | Set of capabilities an agent can request to be granted |
| `jvmtiEventCallbacks` | Struct containing function pointers for JVMTI events |

Obtaining `jvmtiEnv*` from `JavaVM*` via `GetEnv`:

```c
// Fragment: inside Agent_OnLoad, with JavaVM *vm already provided.
jvmtiEnv *jvmti = NULL;
jint status = (*vm)->GetEnv(
        vm, (void **)&jvmti, JVMTI_VERSION_1_2);
if (status != JNI_OK || jvmti == NULL) {
    return JNI_ERR;
}
```

Obtaining the environment **does not grant every capability**. Many JVMTI events/functions depend on the **VM phase** (OnLoad, Start, Live, etc.) and `AddCapabilities` permissions. Native APIs have many error codes; ignoring a return code and dereferencing a pointer can crash the process.

### 3.2. Features at the JVMTI Layer

Examples:

- `VMInit`, `VMDeath`: notify when the JVM is ready or shutting down.
- `ClassFileLoadHook` and `ClassPrepare`: observe class-file bytes and class preparation.
- `ThreadStart`/`ThreadEnd`: thread events.
- `MethodEntry`/`MethodExit`, `Exception`: call-level and exception-level diagnostics.
- `GetLoadedClasses`/`GetClassSignature`: inspect runtime types.
- Certain heap/GC/object tagging and callbacks: require specific capabilities.

**Not all events are enabled by default** just because `Agent_OnLoad` ran. The agent must register callbacks and enable notification mode; many events also require requesting `jvmtiCapabilities`. Native callbacks on hot paths can significantly increase latency, so you must filter and select targets appropriately.

## 4. `-agentlib` and `-agentpath` Differ in How They Locate the File

Java launcher syntax:

```text
-agentlib:<libname>[=<options>]
-agentpath:<pathname>[=<options>]
```

**`-agentlib:foo`**: The JVM searches for the native library by short name and platform conventions. On Linux this is typically `libfoo.so`, on Windows `foo.dll`. The library search path/dependencies must allow loading, such as `LD_LIBRARY_PATH` on Linux or `PATH` on Windows. Java `-cp` specifies where to find Java classes/JARs; it does **not** resolve the native library search.

**`-agentpath:/full/path/libfoo.so`**: The JVM uses the absolute path to the exact binary file. This is useful for isolating search-path issues or using multiple library versions in different locations. However, the file must still match the architecture/ABI and have its dependencies satisfied.

| OS | Common native file | Build/inspection |
| --- | --- | --- |
| Linux | `libfoo.so` | GCC/Clang `-fPIC -shared`, `ldd`, `file` |
| macOS | `libfoo.dylib` or VM-convention name | Clang `-dynamiclib`, architecture/codesigning |
| Windows | `foo.dll` | MSVC/MinGW, `dumpbin /EXPORTS`, `PATH` |

**Important:** `-agentlib` and `-agentpath` **do not require different C source code**; both can load **the exact same native agent binary**. The difference is the library name/path and OS loader configuration.

## 5. Java 17+ Lab: Agent JAR Observing Class Loading

Structure:

```text
two-agent-types/
├── java-agent.mf
├── src/lab/
│   ├── JavaAgent.java
│   ├── App.java
│   └── Sample.java
├── nativeprobe.c
└── out/                (created on compile)
```

The Java lab uses no external dependencies; the agent only observes the `lab/Sample` class and **does not transform the class**.

### 5.1. `src/lab/JavaAgent.java`

```java
package lab;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class JavaAgent {
    private JavaAgent() {}

    public static void premain(String options, Instrumentation inst) {
        System.out.println("JAVA_PREMAIN=" + options);
        inst.addTransformer(new Observer());
    }

    private static final class Observer implements ClassFileTransformer {
        @Override
        public byte[] transform(
                ClassLoader loader,
                String className,
                Class<?> classBeingRedefined,
                ProtectionDomain domain,
                byte[] classfileBuffer) {

            if ("lab/Sample".equals(className)) {
                System.out.println("JAVA_SEES=lab/Sample");
            }
            return null;
        }
    }
}
```

Overriding the five-parameter `transform` method is valid in Java 17; since JDK 9+, there is also a six-parameter overload with `Module`. This Java agent only receives the callback and returns `null` so the JVM uses the unmodified bytes. Do not write to `classfileBuffer` and do not retain a reference to that array.

In production, calling `System.out.println` inside a transformer for every class is a bad idea because it can cause reentrant loading, I/O latency, and log storms. This lab intentionally filters for a single class name.

### 5.2. `src/lab/Sample.java`

```java
package lab;

public final class Sample {
    private Sample() {}

    public static String message() {
        return "ok";
    }
}
```

### 5.3. `src/lab/App.java`

```java
package lab;

public final class App {
    private App() {}

    public static void main(String[] args) throws Exception {
        System.out.println("APP_MAIN");
        Class<?> type = Class.forName(
                "lab.Sample", true, App.class.getClassLoader());
        Object result = type.getDeclaredMethod("message").invoke(null);
        System.out.println("SAMPLE=" + result);
    }
}
```

The class is referenced by the **string** `"lab.Sample"`, with no direct reference like `Sample.class` in `App`. Therefore, the `Class.forName` call after `APP_MAIN` creates an easily observable target load point.

### 5.4. `java-agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: lab.JavaAgent
```

Include a trailing newline at the end of the manifest file. The lab does not need `Agent-Class` because it does not use dynamic loading; nor does it need `Can-Redefine-Classes`/`Can-Retransform-Classes` because it does not modify loaded classes.

### 5.5. Build and Run

On Linux/macOS Bash:

```bash
mkdir -p out
javac --release 17 -d out \
    src/lab/JavaAgent.java src/lab/App.java src/lab/Sample.java
jar --create --file java-agent.jar --manifest java-agent.mf -C out .
java -javaagent:java-agent.jar=demo -cp out lab.App
```

On Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out
javac --release 17 -d out src/lab/JavaAgent.java src/lab/App.java src/lab/Sample.java
jar --create --file java-agent.jar --manifest java-agent.mf -C out .
java -javaagent:java-agent.jar=demo -cp out lab.App
```

**Expected application and agent stdout** on a clean JVM startup, with no other tool loading `lab.Sample` beforehand:

```text
JAVA_PREMAIN=demo
APP_MAIN
JAVA_SEES=lab/Sample
SAMPLE=ok
```

Breakdown: `JAVA_PREMAIN` comes from the JVM calling the Java entry point in the JAR; `JAVA_SEES` comes from the `ClassFileTransformer` callback; `APP_MAIN`/`SAMPLE` come from the application. The `Sample.message()` method still returns `ok`, so the agent **does not alter behavior**.

Running without the agent:

```bash
java -cp out lab.App
```

Stdout:

```text
APP_MAIN
SAMPLE=ok
```

This confirms that the Java application can run on its own, while the two extra lines come from the JVM starting the Java agent.

## 6. Native JVMTI C Lab: `Agent_OnLoad` and `VMInit`

Use the same `lab.App` and `lab.Sample` from Section 5, but replace `-javaagent` with a native shared library. We register a `VMInit` callback to prove that the **JVM TI agent** has been loaded; the example does not transform bytecode.

### 6.1. Create `nativeprobe.c`

```c
#include <jni.h>
#include <jvmti.h>
#include <stdio.h>
#include <string.h>

static void JNICALL on_vm_init(
        jvmtiEnv *jvmti,
        JNIEnv *jni,
        jthread thread) {

    (void)jvmti;
    (void)jni;
    (void)thread;

    puts("NATIVE_VM_INIT");
    fflush(stdout);
}

JNIEXPORT jint JNICALL Agent_OnLoad(
        JavaVM *vm, char *options, void *reserved) {

    (void)reserved;
    jvmtiEnv *jvmti = NULL;

    jint status = (*vm)->GetEnv(
            vm, (void **)&jvmti, JVMTI_VERSION_1_2);
    if (status != JNI_OK || jvmti == NULL) {
        fputs("JVMTI_GET_ENV_FAILED\n", stderr);
        return JNI_ERR;
    }

    jvmtiEventCallbacks callbacks;
    memset(&callbacks, 0, sizeof(callbacks));
    callbacks.VMInit = &on_vm_init;

    jvmtiError error = (*jvmti)->SetEventCallbacks(
            jvmti, &callbacks, (jint)sizeof(callbacks));
    if (error != JVMTI_ERROR_NONE) {
        fputs("SET_CALLBACKS_FAILED\n", stderr);
        return JNI_ERR;
    }

    error = (*jvmti)->SetEventNotificationMode(
            jvmti, JVMTI_ENABLE, JVMTI_EVENT_VM_INIT, NULL);
    if (error != JVMTI_ERROR_NONE) {
        fputs("ENABLE_VM_INIT_FAILED\n", stderr);
        return JNI_ERR;
    }

    printf("NATIVE_ON_LOAD=%s\n", options == NULL ? "" : options);
    fflush(stdout);
    return JNI_OK;
}

JNIEXPORT void JNICALL Agent_OnUnload(JavaVM *vm) {
    (void)vm;
    puts("NATIVE_ON_UNLOAD");
    fflush(stdout);
}
```

Details to understand:

- `jni.h` defines `JavaVM` and calling conventions; `jvmti.h` provides `jvmtiEnv`, `jvmtiError`, and event/capability definitions.
- The JVM invokes `Agent_OnLoad` when loading the library via an agent startup option.
- `GetEnv` requests a JVMTI version supported by the JVM; this example uses `JVMTI_VERSION_1_2`.
- `memset` clears the callbacks struct before assigning `VMInit`, avoiding garbage pointers.
- `SetEventCallbacks` registers the event handler function. `SetEventNotificationMode` **enables** the event. Registering alone is not enough.
- All three operations—`GetEnv`, `SetEventCallbacks`, and enabling the event—must be checked for errors.
- `NATIVE_ON_LOAD=demo` proves that options are passed from the native launcher; `NATIVE_VM_INIT` is the callback during VM initialization.
- `Agent_OnUnload` cleans up resources when the library is about to unload; the lab does not use custom heap allocations or native global references.

**This is complete C source code for a startup agent**, not a JNI library containing only `JNI_OnLoad`. Having `Agent_OnLoad` does not mean every JVMTI capability is automatically granted. Because it only enables `VMInit`, the lab does not need to request capabilities for `MethodEntry` or `ClassFileLoadHook`.

### 6.2. Build on Linux with GCC

`JAVA_HOME` must point to **JDK 17+** and GCC must be installed. Verify headers:

```bash
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
test -f "$JAVA_HOME/include/jvmti.h"
test -f "$JAVA_HOME/include/jni.h"
```

Compile:

```bash
gcc -std=c11 -Wall -Wextra -fPIC -shared \
    -I"$JAVA_HOME/include" \
    -I"$JAVA_HOME/include/linux" \
    -o libnativeprobe.so nativeprobe.c
```

`-fPIC -shared` creates a Linux shared library, and `-I` includes the JDK/JNI headers in the build. An invalid `JAVA_HOME` or a JDK without headers will cause compilation to fail; do not fix this by downloading a random `jni.h` file that does not match the JDK.

### 6.3. Run the Native Agent with `-agentpath`

```bash
java "-agentpath:$(pwd)/libnativeprobe.so=demo" -cp out lab.App
```

On HotSpot Linux with JVMTI and normal program termination, the **expected** stdout is:

```text
NATIVE_ON_LOAD=demo
NATIVE_VM_INIT
APP_MAIN
SAMPLE=ok
NATIVE_ON_UNLOAD
```

Execution order illustrated: native `Agent_OnLoad` runs when the agent is loaded; `VMInit` occurs when the JVM is ready to execute the Java application; `APP_MAIN`/`SAMPLE` are from the Java app; `Agent_OnUnload` serves shutdown/cleanup. If the process is killed, the JVM dies before cleanup, stdout is closed, or startup fails, the `NATIVE_ON_UNLOAD` line may be missing; do not treat the final log line as an absolute guarantee that resources were reclaimed.

### 6.4. Run with `-agentlib` Using the Same Binary

On Linux Bash, add the current directory to the native search path and invoke by short name:

```bash
LD_LIBRARY_PATH="$PWD:$LD_LIBRARY_PATH" \
    java -agentlib:nativeprobe=demo -cp out lab.App
```

Here, the JVM needs to find **`libnativeprobe.so`**; depending on the distro/VM configuration, search paths and library dependencies may differ. If the library is built but `-agentlib` reports it cannot be found, try an absolute `-agentpath`, check `ldd libnativeprobe.so` and architecture with `file libnativeprobe.so`, and then diagnose the search path.

With the same library and `options=demo`, the native code behaves identically to the `-agentpath` experiment. **There are not two separate `Agent_OnLoad` styles for the two options.**

### 6.5. macOS and Windows

On macOS with Clang and a JDK supporting JVMTI:

```bash
clang -std=c11 -Wall -Wextra -dynamiclib \
    -I"$JAVA_HOME/include" \
    -I"$JAVA_HOME/include/darwin" \
    -o libnativeprobe.dylib nativeprobe.c
java "-agentpath:$(pwd)/libnativeprobe.dylib=demo" -cp out lab.App
```

On Windows x64, run in a **Developer Command Prompt** with MSVC `cl` and a JDK of the same architecture:

```bat
cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" nativeprobe.c /link /OUT:nativeprobe.dll
java -agentpath:"%CD%\nativeprobe.dll"=demo -cp out lab.App
```

Native commands depend on the toolchain, architecture, and OS loader. A `.dll` file cannot run directly like a `.so` on Linux. When in doubt about how a native library is named on macOS, use **`-agentpath` pointing explicitly to the actual file** and read the OS loader error.

## 7. Why Are These Two Different Instrumentation Mechanisms?

Both Java Instrumentation and JVMTI can provide a path to modify classes, but their callback/output representations differ:

| Issue | Java agent | JVMTI native agent |
| --- | --- | --- |
| Callback receiving bytes | `ClassFileTransformer.transform(...)` | `ClassFileLoadHook` |
| Callback interface | Java, `byte[] classfileBuffer` array | Native C, byte pointers and output region |
| No class change | `return null` | Keep `new_class_data`/`len` per hook contract |
| Class change | Return a **new valid `byte[]` array**, do not mutate input | Allocate output buffer via JVMTI allocator and pointer contract |
| Loaded classes source | `Instrumentation.getAllLoadedClasses()` | JVMTI `GetLoadedClasses` |
| Changing definitions | `retransformClasses`/`redefineClasses` per VM capability | JVMTI `RetransformClasses`/`RedefineClasses` per capability/phase |
| Method entry/exit events | Typically injects the agent's own bytecode hooks | JVMTI `MethodEntry`/`MethodExit` events when enabled with capability |
| Runtime state manipulation | Java object references/reflection | JNI/JVMTI types, JNI refs, native memory rules |

Both paths can appear in the same class-load pipeline, but you should not infer that the log order of two agents is the transformation order specified by the JVM. When instrumenting together, you must track transformer groups, output format, and idempotency.

### 7.1. Ownership Violation Errors

Java `ClassFileTransformer` **must not modify `classfileBuffer` directly**. If unchanged, return `null`; if changed, return a new array containing a valid class file.

In native `ClassFileLoadHook`, when outputting a different class file, JVMTI requires following the output pointer/size rules and using the corresponding allocator. Do not point `new_class_data` to a local stack buffer whose lifetime has ended, do not `free` memory managed by JVMTI with the wrong allocator, and do not ignore `new_class_data_len`/class format constraints.

Do **not** use Java byte arrays or native pointers as storage for shared mutable state across callbacks without designing thread safety and ownership.

## 8. JVMTI Phases, Capabilities, and Event Lifecycle

A more complete native agent typically does:

```text
Agent_OnLoad
  -> GetEnv(JVMTI_VERSION_...)
  -> GetPotentialCapabilities / AddCapabilities if needed
  -> SetEventCallbacks
  -> SetEventNotificationMode
  -> return JNI_OK

JVM begins running:
  -> events arrive in the appropriate phase
  -> handle callbacks in a controlled manner (no heavy blocking)
  -> check return codes, synchronize state

Agent_OnUnload
  -> clean up native memory, monitors, references...
```

This is a **design diagram**, not a promise that every callback shares the same phase and capability. `VMInit` in the lab is much simpler than `ClassFileLoadHook` or `MethodEntry`. Profilers operating at every method entry/exit can consume significant resources and alter application latency.

### 8.1. `JNIEnv*` Is Thread-Bound

A `JNIEnv*` obtained in a callback cannot be stored globally and used across arbitrary native worker threads. Self-created worker threads must be attached to the JVM using the appropriate invocation APIs before calling JNI and detached according to lifecycle. Native code calling into the Java runtime when phases/threads are not ready can cause deadlocks/crashes; only call when the documented contract permits.

### 8.2. Allocate and Free Memory with the Right Allocator

JVMTI APIs may allocate buffers that must be freed via `jvmti->Deallocate`. Do not call `free` directly if the memory came from the JVMTI allocator. Similarly, do not retain callback-local references after their lifetime ends. If `jobject` global references are created, they must be cleaned up with the corresponding JNI calls at the appropriate lifecycle point.

### 8.3. Separating Java Errors from Native Errors

Java agent bugs can lead to `ClassFormatError`, `VerifyError`, exceptions in `premain`, or module/dependency issues. C bugs can cause segmentation faults, invalid pointers, corrupted heaps, or JVM crashes. A native shared library runs with **the same OS privileges as the Java process**, not in an independent sandbox.

## 9. Startup Agent vs. Dynamic Attach

| Stage | Java agent | JVMTI native agent |
| --- | --- | --- |
| JVM startup | `-javaagent:agent.jar` → `premain` | `-agentlib:name` / `-agentpath:path` → `Agent_OnLoad` |
| Post-startup (if supported) | JAR with `Agent-Class` → `agentmain` | Native library with `Agent_OnAttach` |
| Sample option from Attach API | `VirtualMachine.loadAgent(jar, opts)` | `loadAgentLibrary` / `loadAgentPath` |
| Restrictions | JDK/runtime policy, OS rights, attach availability | Same, plus native ABI |
| Does it auto-attach because a startup option was used? | No | No |

With the Java Attach API, a fragment:

```java
// Fragment: requires module jdk.attach, import VirtualMachine;
// targetPid and jarPath are validated Strings.
VirtualMachine vm = VirtualMachine.attach(targetPid);
try {
    vm.loadAgent(jarPath, "demo");
} finally {
    vm.detach();
}
```

This is not standalone source code. `loadAgent` is primarily for a **Java agent JAR**; native JVMTI libraries use `loadAgentPath`/`loadAgentLibrary` on supporting implementations. Passing a `.so` to `loadAgent` is not equivalent to `-agentpath`.

**JEP 451 since JDK 21:** dynamic agent loading emits a warning and moves toward stricter policies. For example, on HotSpot JDK 21, `-XX:+EnableDynamicAgentLoading` is opt-in and `-XX:-EnableDynamicAgentLoading` disallows dynamic loading; default behavior on newer versions/vendors should be verified in practice. A startup agent declared on the command line is not the same as attempting to attach to a running JVM.

## 10. `Agent_OnLoad` Is Not `JNI_OnLoad`

This is an important point of confusion.

```java
System.loadLibrary("nativeprobe");
```

The Java **fragment** above goes through **JNI library loading**, which may invoke `JNI_OnLoad` if the library provides it. It **does not automatically replace** JVMTI's `-agentlib:nativeprobe`.

- `Agent_OnLoad`: JVM native-agent startup entry point.
- `Agent_OnAttach`: native-agent dynamic attach entry point.
- `JNI_OnLoad`: JNI library load entry point.
- `premain`: Java-agent startup entry point.
- `agentmain`: Java-agent dynamic-load entry point.

A single binary can export multiple entry points if designed by the author, but that does not allow using the wrong loader and assuming every callback will be invoked.

## 11. Real-World Example: The JDWP Debugger Is a Native Agent

`-agentlib:jdwp` loads the Java Debug Wire Protocol (JDWP) implementation using JVMTI/JNI. JDK 17 example:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 \
    -cp out lab.App
```

- `dt_socket` is the TCP transport.
- `server=y` listens for a debugger.
- `suspend=n` does not pause before `main`.
- `127.0.0.1:5005` binds to loopback.

**Security:** A debugger has powerful access to JVM state. Do not bind `*:5005` to the internet without a firewall/network isolation and approval. `lab.App` finishes very quickly so a debugger may not have time to connect; this command is only meant to illustrate real-world usage of `-agentlib`.

## 12. Which Mechanism to Choose in a Project?

### Prefer a Java Agent When

- The goal is bytecode-level tracing, metrics, test instrumentation, or replacing method implementations within the Java API framework.
- You want to deploy a JAR across multiple OSes without building separate native binaries.
- You need `ClassFileTransformer`, `getAllLoadedClasses`, redefine/retransform, and Java tooling.
- You want to avoid directly handling ABI, pointers, native memory, and thread-local JNI.
- A suitable Java agent foundation is available and you do not need VM-level events only provided by JVMTI.

### Prefer JVMTI Native When

- The goal requires VM-level events/capabilities such as detailed class/method/thread/heap inspection.
- You need to integrate a C/C++ profiler/debugger or perform low-level VM interactions.
- You have expertise in JVMTI, phase/capability handling, and C/C++ concurrency.
- You have a native build/test matrix pipeline for Linux/macOS/Windows, architectures, libc/ABI, and JDK vendors.
- You accept the requirements of managing memory safety, native dependencies, crash dumps, and security.

### When Are Both Needed Together?

A Java transformer and a native JVMTI agent can be used in the same process, but you must consider **pipeline order, target scope, callback recursion, overhead**, and potential conflicts. If one agent inserts a hook and another inserts another, both outputs must produce a valid class file; do not use file hashes or console logs in place of a verifier and behavioral tests.

## 13. Operating in Containers and Production Environments

| Criterion | Java agent JAR | Native agent |
| --- | --- | --- |
| Artifact | `.jar` | `.so`/`.dylib`/`.dll` + dependencies |
| Search path | JAR file path | Native loader search path or `-agentpath` path |
| OS/CPU | JAR is usually portable across compatible JDKs | Exact OS, CPU, ABI, libc/glibc/musl |
| Startup | `-javaagent` | `-agentlib`/`-agentpath` |
| Class bytecode | `Instrumentation` | JVMTI hook/capability |
| Build errors | JAR manifest/source/Java bytecode | C ABI/toolchain/JDK headers/shared library |
| Memory safety | Managed by Java GC; still risks instrumentation errors | Native code can crash the process |
| Security | Has permission to observe/modify Java classes | Has process privileges and native memory access |
| Container | Copy/mount JAR + JDK runtime | Copy/mount native binary + matching dependencies/runtime |

A native agent built against a newer glibc version may not run on a distro with an older glibc; a file built for x86-64 will not run natively as x86-64 on ARM64. For Alpine/musl, verify the appropriate toolchain/loader; do not assume a `.so` built in any container is portable.

**Access control:** both agent types are trusted code running alongside the JVM. Verify origin, checksum/signature, access to artifact paths, and restrict who can replace agent files before startup. With a native agent, write access to a library on the startup path can turn into uncontrolled C code execution in the process.

### 13.1. Deployment Checklist

- [ ] Clearly specify whether it is an agent JAR or native library and the corresponding command-line option.
- [ ] Pin the artifact version and tested JDK/vendor version.
- [ ] Inspect native dependencies using `ldd`/`otool`/`dumpbin` or appropriate tools.
- [ ] Verify the startup entry point and error codes before enabling heavy tracing.
- [ ] Do not expose debug ports to untrusted networks.
- [ ] Have a rollback/restart path if agent startup fails.
- [ ] Limit logging and sampling to avoid creating bottlenecks.
- [ ] Native cleanup must use the proper allocator/phase; Java caches must not retain ClassLoaders indefinitely.
- [ ] JVM flags/Attach policies must be verified per version rather than blindly copying old configurations.

## 14. Common Errors Table

| Symptom | Cause | Diagnostic direction |
| --- | --- | --- |
| Missing `Premain-Class` | JAR lacks a valid agent manifest | `jar tf`, inspect `META-INF/MANIFEST.MF` |
| Java agent fails before `main` | `premain` throws, wrong class/dependency | Read JVM stderr, check JAR/classpath |
| `NoClassDefFoundError` when Java agent runs | Missing dependency or wrong module/class visibility | Check JAR dependencies, boot/system loader |
| `-agentlib:foo` cannot find library | Native search path lacks the binary | Check `libfoo.so`/`foo.dll` and `LD_LIBRARY_PATH`/`PATH` |
| `-agentpath` fails to load | Wrong path, file permissions, or incompatible binary | Check absolute path, `file`, `ldd`, OS errors |
| `Agent_OnLoad` not found | Library only has `JNI_OnLoad` or wrong exported symbol | `nm -D`/`dumpbin /EXPORTS` |
| `GetEnv` error | JVMTI unsupported by VM or version mismatch | Check `JVMTI_VERSION_1_2`, vendor, JDK |
| `SetEventCallbacks` error | Invalid callback table/phase | Check `jvmtiError`, struct size |
| `VMInit` not seen | Event not enabled, loaded too late, wrong callback | `SetEventNotificationMode` and phase |
| JVM crash with native agent | Invalid pointers/ABI/threads/allocator | Native debugger/core dump/JVMTI error logging |
| `System.loadLibrary` but no agent callback | Using JNI library loading, not agent startup | Distinguish `JNI_OnLoad`/`Agent_OnLoad` |
| `ClassFileTransformer` misses target | Target already loaded, wrong internal class name filter | Early `premain`, check `lab/Sample` |
| `VerifyError` after instrumentation | Invalid bytecode/frames/constant pool | Use parser/writer and test JVM verifier |
| JDK21+ prints dynamic-agent warning | Loading agent after startup | Check JEP451, explicit startup option, and policy |
| App slows down severely during profiling | Too many MethodEntry/Exit events, sync logging | Limit scope, sampling, measure overhead |
| Library has right name but wrong CPU | Architecture/libc mismatch | Check `file`, compiler target, and image |
| OS refuses to load binary | Security policy, signing/permissions, or container | Check system logs and deployment policy |

## 15. Self-Check

1. **What does `-javaagent:foo.jar` start?** A JAR with `Premain-Class`, calling Java `premain` and receiving `Instrumentation` according to the matching signature.
2. **Does `-agentlib:foo` differ from `-agentpath:/x/libfoo.so` in API?** No; they differ in how the native library is located.
3. **What function does a startup native library typically need to export?** `Agent_OnLoad`.
4. **Which entry point does native attach into a running JVM use?** `Agent_OnAttach` if supported by the implementation.
5. **What manifest entry does a dynamically attached Java agent need?** `Agent-Class` and `agentmain`.
6. **Does `System.loadLibrary` call `Agent_OnLoad`?** Not automatically; that is the JNI loading path, which has its own `JNI_OnLoad` entry point.
7. **Which API obtains `jvmtiEnv*`?** `JavaVM.GetEnv` with a supported JVMTI version.
8. **Does having `jvmtiEnv*` mean all events are sent automatically?** No; it requires event callbacks, notification mode, and the proper capability/phase.
9. **Is JVMTI `VMInit` the same as Java `premain`?** No; a native callback and a Java agent entry point are two different mechanisms.
10. **Can `JNIEnv*` be shared arbitrarily between threads?** No; it is thread-bound.
11. **Why won't a `libfoo.so` binary run on Windows?** Different ABI/OS loader; a matching DLL must be built.
12. **Why isn't `-agentlib:jdwp` an `Instrumentation` JAR?** It uses a native JVMTI/JNI debugger agent.
13. **In the Java lab, what does `return null` from the transformer mean?** The agent only observes and does not modify class bytes.
14. **Can both types of agents be used simultaneously?** Yes, but pipeline, performance, compatibility, and security must be checked.
15. **Which path does JEP 451 affect?** It prepares to restrict **dynamic agent loading** after startup, which is not the same as declaring a startup agent.
16. **Can a native agent crash the JVM?** Yes; invalid native memory, calling conventions, pointers, and threading can crash the process.
17. **When `-agentlib` cannot find the library, what is an easy isolation step?** Use `-agentpath` pointing to the exact absolute file, check OS dependencies/architecture, and verify exported symbols.

## 16. Official Sources

- Oracle JDK 17 **`java.lang.instrument`**: startup `-javaagent`, `premain`, dynamic `agentmain`, manifest — https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- Oracle JDK 17 **`Instrumentation`** and **`ClassFileTransformer`** — https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Oracle JDK 17 **`java` launcher**: `-agentlib` and `-agentpath` — https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle **JVMTI specification**: `Agent_OnLoad`, `Agent_OnAttach`, `GetEnv`, capabilities, callbacks — https://docs.oracle.com/en/java/javase/20/docs/specs/jvmti.html
- Oracle **Creating a Debugging and Profiling Agent with JVMTI**, C sample — https://www.oracle.com/technical-resources/articles/javase/jvmti.html
- Oracle **Attach API VirtualMachine**: Java/native dynamic load methods — https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html
- Oracle **JDWP agent invocation** — https://docs.oracle.com/en/java/javase/17/docs/specs/jpda/conninv.html
- OpenJDK **JEP 451**: dynamic agent loading warnings — https://openjdk.org/jeps/451
- Java SE 17 **JNI Specification** — https://docs.oracle.com/en/java/javase/17/docs/specs/jni/index.html

**In summary:** `-javaagent` loads a **Java agent JAR** via `Premain-Class`/`premain` and `Instrumentation`; `-agentlib`/`-agentpath` loads a **native JVMTI agent library** via `Agent_OnLoad` and `JavaVM.GetEnv`. The two native options differ in name/path. When deploying, consider the required API, lifecycle, JVM capabilities, OS/ABI, and security rather than just changing a launcher flag.
