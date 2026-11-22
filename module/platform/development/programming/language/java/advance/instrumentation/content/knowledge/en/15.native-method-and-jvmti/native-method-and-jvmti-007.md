# JVM TI: Capabilities, Phases, and ClassFileLoadHook at an Overview Level

The Java Virtual Machine Tool Interface (**JVM TI**, often written `JVMTI`) is a native interface provided by the JVM for tools such as debuggers, profilers, tracing agents, and bytecode instrumentation. When you want to observe the JVM at a lower level than `java.lang.instrument`, a native agent can register a callback when the JVM receives class-file bytes, before building the internal class representation, or use the API to inspect threads, stacks, the heap, and runtime state — **if that feature is supported by the JVM, the agent possesses the appropriate capability, and it is in the right operating phase**.

Three concepts must always be considered together:

1. **Capability:** whether a JVM TI environment (`jvmtiEnv*`) is permitted to use an optional feature, such as `can_retransform_classes`.
2. **Phase:** what stage of startup or execution the JVM has reached; certain JVMTI functions/callbacks are invalid when the VM is too early or has already terminated.
3. **Event callback:** the native agent registers a function to receive events and then enables notification; `ClassFileLoadHook` allows viewing or replacing classfile bytes on the path where the JVM loads, redefines, or retransforms a class.

This lesson belongs to the **Native and JVM TI** group. The focus is on the big picture, the exact boundaries of the API, how to debug when events are missing, and a Java 17+ example paired with a small C native agent in **observe-only mode without modifying bytecode**. It does not assume you must write a complex bytecode rewriter before understanding the JVM lifecycle.

## 1. Where Does JVM TI Fit in the Java Ecosystem?

~~~text
Java application                       Native profiling / debugging tool
  |                                               |
  |           Java instrumentation agent          |
  |           premain/agentmain                    |
  |           Instrumentation                      |
  v                    |                          v
ClassLoader ---> Java ClassFileTransformer     JVM TI native agent
  |                                              Agent_OnLoad
  |                                              jvmtiEnv*
  |                                              ClassFileLoadHook
  +--------------------+---------------------------+
                       |
                       v
                       JVM
           class loading / verification
           linking / execution / GC / threads
~~~

Easily confused concepts:

| API or Component | Language / Entry Point | Primary Purpose |
| --- | --- | --- |
| **JNI** | C/C++ bridging with Java code and objects | Calling native code from Java or calling Java via `JNIEnv*`, managing JNI references |
| **JVM TI** | C/C++ agent with `Agent_OnLoad`, `jvmtiEnv*` | Interacting with the JVM for tooling: events, capabilities, threads, classes, bytecode |
| **Java Instrumentation** | Java agent with `premain`/`agentmain`, `Instrumentation` | Registering `ClassFileTransformer`, redefining/retransforming classes from Java |
| **JFR / JMX / logging** | Higher-level observability APIs | Recording and exporting operational data without necessarily manipulating classfile bytes directly |

JNI and JVM TI often appear together in the same native agent, but **they do not replace each other**. `JNIEnv*` serves JNI interaction with the Java world; `jvmtiEnv*` provides JVMTI functions and the tooling environment's own state. JVM TI is not a pure Java library where you just add a Maven dependency; it is a native interface supported by a JVM implementation.

A typical JVMTI agent is a dynamic library `.so` (Linux), `.dylib` (macOS), or `.dll` (Windows). The JVM loads the library via `-agentpath:/absolute/path/to/library` or `-agentlib:name` if the loader path is configured. **`-javaagent` is the mechanism for Java instrumentation JARs**, not an equivalent option for loading a C `.dll` file.

### 1.1. What Does the Term "Environment" Mean?

The JVM can create one or more `jvmtiEnv*` instances within the same process for native agents, each environment having its own capability set, callback table, and notification state. Therefore, do not assume that a capability granted to agent A will automatically appear in every other environment; nor should you rely on a single global callback for the entire JVM.

In C, `jvmtiEnv*` is obtained from `JavaVM*` via `GetEnv` with the requested JVMTI version. Every JVMTI call returns a `jvmtiError`; unlike Java calls which can throw exceptions. **Always check error codes** during setup rather than assuming a function returned successfully.

## 2. The JVM TI Lifecycle: Five Operating Phases

JVM TI defines the `jvmtiPhase` enum. The chronological order is:

~~~text
Agent_OnLoad
   |
   v
ONLOAD ---------------------- prepare agent, query/grant capabilities
   |
   v
PRIMORDIAL ------------------ VM is bootstrapping, JNI is not always ready
   |
   v
START ------ VMStart -------- part of VM/Java runtime is ready
   |
   v
LIVE ------- VMInit --------- application runs, most tooling APIs work
   |
   v
DEAD ------- VMDeath -------- VM shuts down or startup failed
~~~

| Phase | `jvmtiPhase` Constant | Semantics |
| --- | --- | --- |
| OnLoad | `JVMTI_PHASE_ONLOAD` | Inside `Agent_OnLoad`; usually the right time to negotiate optional capabilities and register callbacks |
| Primordial | `JVMTI_PHASE_PRIMORDIAL` | After `Agent_OnLoad`, before `VMStart`; the VM is still at a very early stage |
| Start | `JVMTI_PHASE_START` | After `VMStart` until `VMInit`; some JNI and JVMTI functions are now permitted |
| Live | `JVMTI_PHASE_LIVE` | From `VMInit` until `VMDeath` completes; most JVMTI operations are valid |
| Dead | `JVMTI_PHASE_DEAD` | After `VMDeath` or startup failure; normal Java runtime no longer exists |

**Do not directly compare numeric enum values to infer phase order.** According to the specification, for example, `JVMTI_PHASE_START` has numeric value 6 while `JVMTI_PHASE_LIVE` has value 4; they are enum codes, not sequential step numbers. When you need the actual phase, call:

~~~c
jvmtiPhase phase;
jvmtiError err = (*jvmti)->GetPhase(jvmti, &phase);
~~~

This is only a **native snippet**, assuming `jvmti` is a valid environment. `GetPhase` is an API allowed in any phase, but **that does not mean every other function is valid in any phase**.

### 2.1. Why Is Phase a Real Constraint?

Some JVMTI APIs may only be called in **Live**; some are used in OnLoad or Live; some like `GetPhase` can be called in multiple phases. If called in the wrong phase, JVM TI may return `JVMTI_ERROR_WRONG_PHASE`. For instance, you should not write a callback that runs in the Primordial phase and makes a series of JNI reflective calls as if the Java runtime were already initialized.

The documentation also states that normal JNI functions are only usable in **Start/Live**; therefore, **`JNIEnv*` in `ClassFileLoadHook` can be `NULL` if the hook occurs during Primordial**. Do not dereference or use `jni_env` without being certain of the phase and pointer. Many agent startup bugs are very hard to debug simply because `FindClass` was called too early or a Java logger was touched inside the hook.

**Distinguish the two milestones:** `VMStart` marks the transition into Start, whereas `VMInit` marks the transition into Live. Do not write "everything is Live from VMStart"; that is an inaccurate explanation.

### 2.2. Agent Startup and Attaching to a Running JVM

| Mechanism | Native Entry Point | Timing |
| --- | --- | --- |
| `-agentpath:/path/libobserve.so` at launcher startup | `Agent_OnLoad(JavaVM*, char*, void*)` | OnLoad, before most of the Java application |
| `-agentlib:observe` at launcher startup | `Agent_OnLoad(...)` | Similar, JVM searches for library along the search path |
| Native agent attached to a running JVM (if supported) | `Agent_OnAttach(...)` | Usually in Live; some OnLoad-only capabilities may no longer be addable |
| JVM shutdown | May call `Agent_OnUnload(JavaVM*)` | Clean up native resources per contract; do not arbitrarily call back into APIs when the JVM is dead |

Because **available capabilities also depend on the phase**, an agent that needs very early hooks has reason to be loaded at JVM startup. Late attach is still useful for diagnostics, but it cannot retroactively capture `ClassFileLoadHook` events that already passed during earlier class loading.

## 3. Capabilities: Three Questions When Using Optional Features

Not every JVMTI implementation supports every feature. Some operations require a specific capability, for example `can_retransform_classes` to use `RetransformClasses` or `can_generate_method_entry_events` to emit method entry events.

Separate three checks:

| Question | JVM TI Function | Meaning |
| --- | --- | --- |
| Which capabilities **can** the environment request in the current phase? | `GetPotentialCapabilities` | List of capabilities **achievable right now**, which may depend on JVM/phase and other agents |
| Which capabilities does the agent want **granted**? | `AddCapabilities` | Adds the bits set in `jvmtiCapabilities` |
| Which capabilities does the environment **currently possess**? | `GetCapabilities` | The values actually granted; does not imply all potential capabilities are possessed |

Visualizing this:

~~~text
GetPotentialCapabilities()
       |
       v
"What can the JVM grant RIGHT NOW?"
       |
       v
Select only the bits truly needed
       |
       v
AddCapabilities(request)
       |
       +-- JVMTI_ERROR_NONE -> granted as requested
       |
       +-- error           -> do not assume permission
       |
       v
GetCapabilities() -> verify currently possessed capabilities
       |
       v
SetEventCallbacks(...) and SetEventNotificationMode(...)
~~~

`AddCapabilities` is an **additive** operation, not a reset of the entire capability set. Some capabilities can only be requested during `OnLoad`; if requested only once in Live, `GetPotentialCapabilities` may no longer list them. Permissions may also be restricted by the JVM vendor, startup flags, or another JVMTI environment holding an exclusive capability.

**Do not pass the entire potential bitmask to `AddCapabilities` just "to be safe".** Requesting unnecessary permissions can increase overhead or alter VM optimization behavior; some capabilities consume resources or lock special JVM mechanisms. Request only what the agent actually uses and have a fallback when the JVM does not provide it.

### 3.1. Example of Checked Capability Configuration

In C, after obtaining `jvmtiEnv*`:

~~~c
jvmtiCapabilities potential;
jvmtiCapabilities wanted;
jvmtiCapabilities owned;

memset(&potential, 0, sizeof(potential));
memset(&wanted, 0, sizeof(wanted));
memset(&owned, 0, sizeof(owned));

jvmtiError error = (*jvmti)->GetPotentialCapabilities(jvmti, &potential);
if (error != JVMTI_ERROR_NONE) {
    return JNI_ERR;
}
if (potential.can_generate_all_class_hook_events) {
    wanted.can_generate_all_class_hook_events = 1;
    error = (*jvmti)->AddCapabilities(jvmti, &wanted);
    if (error != JVMTI_ERROR_NONE) {
        return JNI_ERR;
    }
}
error = (*jvmti)->GetCapabilities(jvmti, &owned);
if (error != JVMTI_ERROR_NONE) {
    return JNI_ERR;
}
~~~

This is a **native code fragment**, not a standalone program. `jvmti` must be a valid environment, `string.h` must be included, and `return JNI_ERR` belongs in a function returning `jint` such as `Agent_OnLoad`. `can_generate_all_class_hook_events` is an optional feature to receive `ClassFileLoadHook` for the full specified group of classes; if unavailable, the agent must accept lower coverage rather than faking a "permission granted" state.

In the runnable example in Section 7, we will use this checked capability request, **without requesting early hooks or retransformation**, because the goal is only to observe a normally loaded application class.

### 3.2. Capabilities Directly Related to `ClassFileLoadHook`

| Capability | Purpose | Rule to Remember |
| --- | --- | --- |
| `can_generate_all_class_hook_events` | Allows receiving ClassFileLoadHook for all classes within the spec scope supported by the JVM | Some special classes may not emit hooks depending on the JVM implementation |
| `can_generate_early_class_hook_events` | Allows hooks during the **Primordial** phase | To get early hooks, you need **both** `can_generate_early_class_hook_events` and `can_generate_all_class_hook_events` |
| `can_retransform_classes` | Allows calling `RetransformClasses` and having a retransform-capable environment | **Must be granted before `ClassFileLoadHook` is enabled for the first time** on that environment |
| `can_redefine_classes` | Allows using `RedefineClasses` | Must check both per-class and VM restrictions |
| `can_generate_method_entry_events` | Receive method entry events | Not required just to observe ClassFileLoadHook |

**This is not a table of mandatory capabilities for every hook:** `ClassFileLoadHook` itself is a core JVM TI event, and the capabilities above enable **extended coverage** or other operations. Do not claim that lacking `can_generate_all_class_hook_events` means no hooks can ever be received for a normal application class.

A major pitfall:

~~~text
Wrong order when retransform-capable is needed:
    SetEventNotificationMode(ENABLE, CLASS_FILE_LOAD_HOOK)
    AddCapabilities(can_retransform_classes)   <-- too late to change env type

Correct order:
    GetPotentialCapabilities
    AddCapabilities(can_retransform_classes)  <-- before first enable
    SetEventCallbacks
    SetEventNotificationMode(ENABLE, CLASS_FILE_LOAD_HOOK)
~~~

The documentation defines **whether an environment is retransformation-capable or incapable at the time `ClassFileLoadHook` is first enabled**. Adding a capability bit late is not a valid way to turn an environment already classified as non-capable into a capable one for the callback. If retransformation is needed from the start, configure the capability before enabling the event.

## 4. Event Callbacks: Registering the Function Is Not Enough; You Must Enable Notification

A JVMTI environment can register a callback table containing function pointers for `VMInit`, `VMDeath`, `ClassFileLoadHook`, and many other events.

Three basic setup steps:

~~~text
Agent_OnLoad
    |
    v
GetEnv -> jvmtiEnv*
    |
    v
(Negotiate required capabilities)
    |
    v
SetEventCallbacks(callback table, sizeof(table))
    |
    v
SetEventNotificationMode(JVMTI_ENABLE,
                         JVMTI_EVENT_CLASS_FILE_LOAD_HOOK,
                         NULL)
    |
    v
JVM emits event -> ClassFileLoadHook function pointer
~~~

- `SetEventCallbacks` registers function pointers; it **does not mean** the event is automatically enabled.
- `SetEventNotificationMode` controls enabling/disabling notifications for an event. For the demo's ClassFileLoadHook, pass `NULL` for the thread argument to enable it across the valid event scope.
- Both functions have phase rules; they can be called in `OnLoad` to start tracking early, or in `Live` under appropriate conditions.
- If the agent registers/enables too late, classes that have already gone through class loading **do not automatically replay the hook** just because a new callback was added.
- If multiple environments register the hook, the JVM has a pipeline/chaining mechanism; each callback does not necessarily see the exact bytes from disk.

### 4.1. What Is the `ClassFileLoadHook` Event?

**ClassFileLoadHook** is emitted when the JVM has the class-file bytes and **before constructing the class representation in memory**. It can also be emitted when `RetransformClasses` or `RedefineClasses` processes a class. This is the right point for a bytecode instrumentation tool to modify bytes **before the VM verifies/links/defines the new version**.

Do not think of "ClassFileLoadHook" as an event that only appears when a class load succeeds. The event allows intervention during the definition process; if the class file is invalid or a transformer returns broken bytes, the JVM may fail to install the final class definition.

When you only need to know which preparation/definition step a class has passed, you can additionally observe `ClassLoad`/`ClassPrepare` or other observation sources depending on your goal. **`ClassFileLoadHook`, `ClassLoad`, and `ClassPrepare` are not the same milestone:**

| Event | Timing / Meaning | What Information Is Available? |
| --- | --- | --- |
| `ClassFileLoadHook` | JVM has raw class bytes before building the class (also used for redefine/retransform) | `name`, `loader`, `class_data`, output buffer |
| `ClassLoad` | A class has been loaded; this step is still very early | `jclass` may not yet have full methods/fields metadata |
| `ClassPrepare` | Class has passed the preparation step | Methods/fields and interfaces information are more ready; the class does not need to be initialized yet |
| `VMInit` | JVM enters Live | Not an event meaning "all application classes have finished loading" |

If you need to analyze method signatures, do not assume `ClassFileLoadHook` immediately provides a defined `jclass` during **an initial load**. `class_being_redefined` is normally `NULL` on initial load, and field/method reflections are not yet available as on a prepared object.

## 5. `ClassFileLoadHook` Signature and How to Read Its Data

According to the JVM TI specification:

~~~c
void JNICALL ClassFileLoadHook(
    jvmtiEnv* jvmti_env,
    JNIEnv* jni_env,
    jclass class_being_redefined,
    jobject loader,
    const char* name,
    jobject protection_domain,
    jint class_data_len,
    const unsigned char* class_data,
    jint* new_class_data_len,
    unsigned char** new_class_data);
~~~

Meaning of the parameters:

| Parameter | Meaning | Safety Notes |
| --- | --- | --- |
| `jvmti_env` | Native tooling environment receiving the hook | Has its own capability/event state; must be valid |
| `jni_env` | JNI environment of the current thread | **Can be NULL in primordial**; do not call JNI when not permitted |
| `class_being_redefined` | `jclass` when redefining or retransforming; null on new load | Does not mean every hook already has a complete `Class<?>` |
| `loader` | Defining class loader object | Null for the bootstrap loader; do not hold unbounded strong refs |
| `name` | Internal class name such as `demo/Target` | **Modified UTF-8** string, can be `NULL` |
| `protection_domain` | ProtectionDomain associated with the class | Do not serialize the entire object on a hot path |
| `class_data_len` | Number of bytes in the input classfile | Not the number of methods or version |
| `class_data` | Pointer to the current classfile bytes in the pipeline | Valid only for the callback lifetime; do not modify input directly |
| `new_class_data_len` | Pointer receiving the new output length | Set only when there is valid new bytecode |
| `new_class_data` | Pointer receiving the new classfile buffer | Buffer must be allocated via `jvmtiEnv::Allocate` |

**Important about ownership:** If only observing, the agent **does not assign `new_class_data`** and **does not need to allocate an output buffer**. If modifying classfile bytes, it must allocate the buffer via `(*jvmti)->Allocate(...)`; the JVM is responsible for freeing that output using `Deallocate`. Do not return a pointer to the stack, a static array, a `malloc` buffer, or `class_data` itself; do not `free` the output after the JVM has taken ownership.

If multiple agents receive the hook and agent A returns new bytes, agent B downstream may receive **the bytes produced by A**, not necessarily the original file. Therefore, a callback must treat `class_data` as **the input at the current point in the pipeline**, not as an always-intact copy of the `.class` read from a JAR.

### 5.1. Why Can `name` Be NULL?

When the JVM defines a class without a conventionally specified name, the `name` parameter may be unavailable. If a callback writes:

~~~c
// DANGEROUS: does not check the pointer.
if (strcmp(name, "demo/Target") == 0) {
    /* ... */
}
~~~

then `strcmp(NULL, ...)` is undefined behavior and can crash **the entire JVM process**. Use:

~~~c
if (name != NULL && strcmp(name, "demo/Target") == 0) {
    /* handle event for target class */
}
~~~

Internal names use `/`, unlike `demo.Target` in Java source. Do not try calling JNI `FindClass` inside the hook to construct the name for the class being defined: in some phases `JNIEnv` is not yet valid, and even in Live, that operation can trigger nested class loading.

### 5.2. Can `class_data` Be Used After the Callback?

You should not retain the `class_data` pointer for a native thread to process later. That data belongs to the VM and its lifetime is tied to the current hook invocation. If asynchronous analysis is needed, you must **copy** the needed portion into an agent-managed buffer, bound total memory/retention, and clearly define ownership. Storing raw class bytes for tens of thousands of classes can consume gigabytes and expose sensitive constants/strings.

For high-level diagnostics, usually only **the class name, event type, a counter, and the byte size** are needed, without copying the entire class data. If bytes must be modified, use a parser/bytecode toolkit that checks classfile versions, constant pools, frames, and exception tables.

## 6. JVM TI Phases and When ClassFileLoadHook Fires

The specification states that `ClassFileLoadHook` can occur in **Primordial, Start, or Live** — but **not every environment receives primordial events**.

- If the agent has **both** `can_generate_early_class_hook_events` and `can_generate_all_class_hook_events`, the JVM may send ClassFileLoadHook as early as **Primordial**.
- Without that combination, the event may appear starting in **Start** before the VM is fully initialized; afterward it can appear in Live.
- The event is not guaranteed for certain special classes (e.g., ROMized or implementation-defined classes), depending on the JVM.
- The hook can also be emitted due to **redefine/retransform** when the agent/VM is already in Live, not only during initial load.

Thus, a native agent cannot rely on the assumption "the callback always has a `JNIEnv` and all Java services are ready" to freely initialize loggers or class loaders. In early callbacks, minimize work and use only functions permitted in the corresponding phase.

### 6.1. Phases Are Not a Monotonic "Privilege Hierarchy"

A function usable in `OnLoad` is not automatically usable in `Start`; a Live-only function cannot be used in Primordial; an Any-phase function can be called in multiple stages. Check the **Phase** column for **the specific function/event** rather than guessing intuitively.

Errors you may encounter:

- `JVMTI_ERROR_WRONG_PHASE`: the operation is invalid in the current phase.
- `JVMTI_ERROR_MUST_POSSESS_CAPABILITY`: missing a capability required by the operation.
- `JVMTI_ERROR_NOT_AVAILABLE`: a feature is unavailable under current VM conditions.
- `JVMTI_ERROR_INVALID_EVENT_TYPE` / `JVMTI_ERROR_ILLEGAL_ARGUMENT`: invalid event or configuration argument depending on the case.

A controlled way to investigate is to call `GetPhase` and `GetCapabilities` where permitted and log them **outside the hot callback**, cross-referencing with the spec and JVM version.

## 7. Java 17+ Demo and C Native JVMTI Agent Observing a Class

Goal: when the JVM loads `demo.Target`, the C agent prints a line `JVMTI_HOOK=demo/Target`, while the Java application prints `APP=hello`. The agent **does not modify bytes** and does not require a bytecode library.

### 7.1. Project Structure

~~~text
jvmti-demo/
  observe.c
  demo/
    Target.java
    Main.java
  out/
    ... (generated after javac)
  libobserve.so   (Linux, after build)
  libobserve.dylib (macOS, after build)
  observe.dll     (Windows, after build)
~~~

The three native library names are **OS-specific alternative outputs**, not a requirement to build all three on one machine. `out/` is the class files directory, not a source folder.

### 7.2. File `demo/Target.java`

~~~java
package demo;

public final class Target {
    public static String greeting() {
        return "hello";
    }
}
~~~

### 7.3. File `demo/Main.java`

~~~java
package demo;

public final class Main {
    public static void main(String[] args) {
        System.out.println("APP=" + Target.greeting());
    }
}
~~~

`Main` simply calls `Target.greeting()` at runtime; `demo/Target` must be loaded before the method can execute. Do not use reflection or a `javaagent` to trigger the event in this lesson. The Java source was **compiled with `javac --release 17` and run with `APP=hello` on OpenJDK 24**.

### 7.4. File `observe.c` — Minimal Native JVMTI Agent

~~~c
#include <jni.h>
#include <jvmti.h>
#include <stdio.h>
#include <string.h>

static void JNICALL on_class_file_load(
        jvmtiEnv* jvmti,
        JNIEnv* jni,
        jclass being_redefined,
        jobject loader,
        const char* name,
        jobject protection_domain,
        jint class_data_len,
        const unsigned char* class_data,
        jint* new_class_data_len,
        unsigned char** new_class_data) {

    (void)jvmti;
    (void)jni;
    (void)being_redefined;
    (void)loader;
    (void)protection_domain;
    (void)class_data_len;
    (void)class_data;
    (void)new_class_data_len;
    (void)new_class_data;

    if (name != NULL && strcmp(name, "demo/Target") == 0) {
        puts("JVMTI_HOOK=demo/Target");
        fflush(stdout);
    }
    /* Do not set new_class_data: no bytecode transformation. */
}

JNIEXPORT jint JNICALL Agent_OnLoad(
        JavaVM* vm, char* options, void* reserved) {
    (void)options;
    (void)reserved;

    jvmtiEnv* jvmti = NULL;
    jint rc = (*vm)->GetEnv(
            vm, (void**)&jvmti, JVMTI_VERSION_1_2);
    if (rc != JNI_OK || jvmti == NULL) {
        return JNI_ERR;
    }

    jvmtiCapabilities potential;
    jvmtiCapabilities wanted;
    memset(&potential, 0, sizeof(potential));
    memset(&wanted, 0, sizeof(wanted));

    jvmtiError error = (*jvmti)->GetPotentialCapabilities(
            jvmti, &potential);
    if (error != JVMTI_ERROR_NONE) {
        return JNI_ERR;
    }

    if (potential.can_generate_all_class_hook_events) {
        wanted.can_generate_all_class_hook_events = 1;
        error = (*jvmti)->AddCapabilities(jvmti, &wanted);
        if (error != JVMTI_ERROR_NONE) {
            return JNI_ERR;
        }
    }

    jvmtiEventCallbacks callbacks;
    memset(&callbacks, 0, sizeof(callbacks));
    callbacks.ClassFileLoadHook = &on_class_file_load;

    error = (*jvmti)->SetEventCallbacks(
            jvmti, &callbacks, (jint)sizeof(callbacks));
    if (error != JVMTI_ERROR_NONE) {
        return JNI_ERR;
    }

    error = (*jvmti)->SetEventNotificationMode(
            jvmti, JVMTI_ENABLE,
            JVMTI_EVENT_CLASS_FILE_LOAD_HOOK, NULL);
    if (error != JVMTI_ERROR_NONE) {
        return JNI_ERR;
    }

    puts("JVMTI_ONLOAD=OK");
    fflush(stdout);
    return JNI_OK;
}
~~~

**Explanation:**

1. `Agent_OnLoad` is the native entry point the JVM calls for a library loaded via `-agentpath` at startup; it is not a C program's `main`. `JNIEXPORT` and `JNICALL` ensure linkage/ABI compatibility with the JDK's JNI headers and platform.
2. `GetEnv(..., JVMTI_VERSION_1_2)` obtains the appropriate environment; if the JVM cannot provide it, return `JNI_ERR` so execution does not continue with a null pointer.
3. `GetPotentialCapabilities` checks whether `can_generate_all_class_hook_events` is available to request. The demo **does not request** `can_retransform_classes` or early hooks because it does not call retransform and does not need primordial.
4. `SetEventCallbacks` registers the `on_class_file_load` function; `SetEventNotificationMode` **enables** notification once the callback pointer is ready.
5. The callback only checks `name != NULL` and compares against the internal name `demo/Target`. It does not call JNI, does not read Java objects, does not parse the classfile, and does not retain the bytes pointer.
6. Currently unused parameters are cast to `(void)` to avoid compiler warnings. They are **real parameters per the spec**, not omitted because the callback lacks them.
7. `new_class_data` is not assigned, so the bytecode runs identically to the input at this layer. The only side effect is a console line printed by the native agent for demonstration.
8. `puts`/`fflush` inside a class-loading hook is **not a production pattern**: I/O has overhead, may acquire libc locks, and can distort performance. In the example, the filter is very narrow to avoid printing for thousands of classes.

**Testing limitation:** the Java part of the example was actually run. The machine used to author this lesson has a JDK but **does not have a common C compiler in PATH**, so the native C code was not built/run here. The signatures and JVMTI calls were verified against the official specification; the two lines of native output below are **the expected result once a supported toolchain + JVM builds/runs successfully**, not a log executed on this machine.

### 7.5. Compiling the Java Part

From the `jvmti-demo/` directory:

~~~bash
javac --release 17 -d out demo/Target.java demo/Main.java
~~~

Verify without the agent:

~~~bash
java -cp out demo.Main
~~~

**Actual standard output observed for the Java part:**

~~~text
APP=hello
~~~

The files `out/demo/Main.class` and `out/demo/Target.class` were generated by javac; there is no JVM TI logging when the native agent is not enabled.

### 7.6. Compiling Native Code on Linux

Requires JDK headers in `$JAVA_HOME/include` and `$JAVA_HOME/include/linux`; requires GCC or a compatible C compiler:

~~~bash
gcc -std=c11 -O2 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libobserve.so observe.c
~~~

After building, run with the **absolute path** to the library:

~~~bash
java -agentpath:"$(pwd)/libobserve.so" -cp out demo.Main
~~~

If `JAVA_HOME` is not configured, determine the actual JDK directory before compiling. Use the same 64-bit architecture as the running JDK. Do not assume the library name `libobserve.so` is valid on Windows/macOS.

### 7.7. Compiling Native Code on macOS

Requires Xcode Command Line Tools/Clang and JDK headers:

~~~bash
clang -std=c11 -O2 -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -o libobserve.dylib observe.c
~~~

Run:

~~~bash
java -agentpath:"$(pwd)/libobserve.dylib" -cp out demo.Main
~~~

Must match the JVM architecture (e.g., arm64 or x86_64). You cannot load a dylib built only for a different CPU architecture into the current JVM.

### 7.8. Compiling Native Code on Windows with MSVC

Open a Visual Studio **Developer Command Prompt** with MSVC and JDK headers configured; this command is for `cmd.exe`, not PowerShell syntax:

~~~bat
cl /LD /O2 /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" observe.c /link /OUT:observe.dll
~~~

Run with the **absolute path** to the DLL. For example, in Windows PowerShell inside the demo directory after building:

~~~powershell
java "-agentpath:$((Resolve-Path .\observe.dll).Path)" -cp out demo.Main
~~~

`Get-Command cl`/`where cl` must find the MSVC compiler in the current terminal. If not, open the proper Developer Command Prompt or install the toolchain; having a JDK does not mean the machine has a C compiler.

### 7.9. Expected Output When the Native Agent Runs Successfully

With OpenJDK HotSpot/Zulu running normally, `demo.Target` is loaded after the native agent has enabled the hook; **expected standard output**:

~~~text
JVMTI_ONLOAD=OK
JVMTI_HOOK=demo/Target
APP=hello
~~~

- `JVMTI_ONLOAD=OK`: `GetEnv`, capability negotiation, and event setup all succeeded without error.
- `JVMTI_HOOK=demo/Target`: the callback received the event for `demo.Target` before the JVM used the complete classfile bytes.
- `APP=hello`: Java logic behaves the same as without the agent, because the callback did not modify the classfile.

**No absolute output guarantee across every JVM implementation**: a JVM may emit additional diagnostics; some classes/platforms are not hooked with the same coverage, or the native library may fail to load due to wrong ABI/headers. The lesson uses a normal application class to avoid depending on special events.

### 7.10. Why Not Modify Bytes in the Demo?

The current goal is to understand **capability, phase, and hook lifecycle**. Modifying a classfile correctly requires a parser, verifier, constant pool, code attributes, stack maps, exception handlers, and helper visibility. If you randomly copy a few bytes in `class_data` and return them, the JVM may throw `ClassFormatError`, `VerifyError`, or crash due to a native bug.

When actually transforming, only set `*new_class_data_len` and `*new_class_data` after constructing **a valid new classfile** in a buffer allocated by `jvmti->Allocate`. The JVM owns freeing the output buffer. Do not pick an arbitrary byte offset and overwrite the magic number just to "test if the hook works".

## 8. Retransformation and ClassFileLoadHook: Two Groups of Environments

The ordering when multiple native agents use JVMTI ClassFileLoadHook differs from many other events:

1. **Retransformation-incapable environments** are called first, in environment creation order.
2. **Retransformation-capable environments** are called afterward, also in environment creation order.
3. If a hook returns new bytes, those bytes are passed forward as input to the next hook in the chain.
4. During `RetransformClasses`, the event is sent **only to capable environments**. Modifications from the incapable group at the most recent load/redefine are still reused per the contract; they do not receive a new callback.

Logical example:

~~~text
LOAD pass:
class bytes D0
  -> native agent A (incapable): produces output A0
  -> native agent B (capable):   produces output B0
  -> JVM defines class

RETRANSFORM pass:
baseline from most recent define/redefine
  -> JVM reapplies output A0, does not call callback A
  -> calls capable callback B again
  -> JVM installs new definition if valid
~~~

Do not attach **`can_retransform_classes`** to an environment after ClassFileLoadHook has already been enabled and expect the JVM to automatically move it to the capable group. The specification determines capability classification at **the first time the hook is enabled**. If retransformation is needed, that capability must be negotiated before enabling the event.

**Caution:** the Java `ClassFileTransformer` API also has a `canRetransform` classification; the concept is similar, but it is **a different Java API**. Do not copy-paste Java + native ordering assumptions just from two registration lines in a library: the spec also defines **environment groups**, and a single JVM can host multiple Java/native agents. To diagnose exact ordering, explicitly log the group and registration time.

### 8.1. Does Retransform Always Start from the Previously Instrumented Bytes?

No. The retransformation pipeline starts from **the initial classfile bytes of the most recent define or redefine**, the JVM reuses the non-capable results, and then calls the capable group again. Furthermore, the initial classfile bytes on a subsequent pass may **not be bit-identical** to the original file because the JVM is allowed to reorder the constant pool or strip certain attributes. Therefore, you should not detect an already-transformed class solely by taking the SHA-256 of the bytes received by the callback.

To avoid inserting duplicate helpers, build transformations that are **idempotent** based on method name/descriptor/instruction patterns and test repeated retransformations on a real JVM.

## 9. `ClassFileLoadHook` Is Not a Harmless Callback

A native callback sits directly on the class-definition path; C/C++ mistakes can have much larger consequences than an ordinary Java exception:

- `strcmp(NULL, "...")` can crash the JVM.
- Reading past `class_data_len` or dereferencing an invalid `class_data` pointer can lead to native memory corruption.
- Holding `jobject`/`jclass` references beyond the lifetime of a JNI local reference without managing a global reference can cause unpredictable failures.
- Logging/serializing/reading files inside the callback can create lock contention, I/O latency, and even trigger Java class loading under sensitive conditions.
- Failing to synchronize data across multithreaded callbacks can create data races. Do not assume the JVM only invokes ClassFileLoadHook on a single global thread.
- A JNI call in primordial may be invalid because `JNIEnv` is null or the VM is not ready.
- Returning invalid classfile bytes causes load/redefine/retransform to fail even though the application algorithm did not change.
- Storing too many raw class bytes can bloat memory and leak sensitive data in the constant pool.

**Production design** should filter very early by `name`, use only small metadata, avoid I/O on the hot path, bound buffers/sampling, handle error codes from every JVMTI operation, and decouple the exporter from the callback. If the agent needs detailed data, analyze only target classes and test on actual JDK/VM versions.

### 9.1. When Should You Not Use JVMTI Directly?

Not every telemetry problem needs a native agent. If you only need Java method tracing in an application you control, consider logging, metrics, JFR, or `java.lang.instrument` first. JVM TI is worth considering when you need native/tooling-level events and hooks, deep debugging, or JVM features that have no direct Java API equivalent. The closer you get to the VM, the greater the responsibility for portability, memory management, and phase correctness.

## 10. Troubleshooting Table

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| JVM reports failure to load agent library | Wrong absolute path, missing DLL/SO, wrong bitness/ABI, missing dependencies | Check `-agentpath`, architecture, OS loader |
| `Agent_OnLoad` returns `JNI_ERR` | `GetEnv`, capability negotiation, or callback setup failed | Print numeric `jvmtiError` during setup; check API version |
| `JVMTI_HOOK=demo/Target` not seen | Hook not enabled, late registration, wrong name filter, class already loaded earlier, VM-specific coverage | Check `SetEventCallbacks`, `SetEventNotificationMode`, spelling `demo/Target` |
| `JVMTI_ERROR_WRONG_PHASE` | Function called in the wrong phase | Use `GetPhase`; cross-check the phase table in the spec |
| `JVMTI_ERROR_MUST_POSSESS_CAPABILITY` | Capability not requested before the operation | `GetPotentialCapabilities` + `AddCapabilities` + `GetCapabilities` |
| Event missing in Primordial | Did not request both early and all capabilities | Consider requesting early in OnLoad if VM supports it; handle `JNIEnv == NULL` |
| Retransform does not call agent A's hook | A is retransformation-incapable | Must request `can_retransform_classes` before first enable if capable is needed |
| Callback `name == NULL` | Name not specified in conventional form | Always null-check before `strcmp` |
| Bytecode patch causes `VerifyError` | Output has wrong descriptor/stack/frame | Use a bytecode toolkit and verifier, do not patch bytes manually |
| JVM crash in callback | Native pointer/buffer/ref race or wrong C ABI | Native debugger, hs_err log, bounds checks, reduce work in hook |
| Too much logging at startup | Callback receives very many class events | Filter by package/name, sampling, bounded counters |
| Same class hooked multiple times | Redefine/retransform or definitions by different loaders | Distinguish source, loader, phase, sequence; do not equate callback = unique class |
| Configured `-javaagent` but C callback does not run | Java agent JAR differs from native JVMTI library | Use `-agentpath`/`-agentlib` for C libraries |

Do not swallow every error and treat instrumentation as having succeeded. **Receiving no event** differs from **receiving an event and returning a no-op**, and both differ from **receiving an event while class definition fails at a later step**.

## 11. Advanced Practice and Exact Boundaries

### 11.1. Observing the Phase with `GetPhase`

You can add inside the callback (still within the allowed JVMTI functions):

~~~c
jvmtiPhase phase;
if ((*jvmti)->GetPhase(jvmti, &phase) == JVMTI_ERROR_NONE) {
    /* Record phase code into a bounded native counter/buffer. */
}
~~~

This snippet is not a standalone C program. You should not `printf` on every callback; a lock-free counter/buffer or bounded-cost synchronization is more appropriate for real applications. Phase information helps explain why a given JNI operation is not yet available.

### 11.2. Testing the `name == NULL` Case

Do not try to craft a null-named class just to prove the hook can receive null if the demo does not need it. A separate unit test for the C filter function can call the predicate with `NULL`, `"demo/Target"`, and other names. The goal is to test native code safety even when the JVM does not provide a name.

### 11.3. Testing Capabilities by Phase

A controlled test can record `GetPotentialCapabilities` at OnLoad and compare it again in Live. Do not assume the two sets are always identical. Do not request excessive capabilities to "cover all cases": request only the needed feature and verify `AddCapabilities` succeeds before enabling the corresponding event.

### 11.4. Testing with Multiple Agents

If deploying an additional capable environment for retransformation, check the hook count and bytes received by each environment. Record environment creation order, callback order, and check whether the output has duplicate helper insertions. An event in environment B may be the output from environment A, not just baseline bytes.

## 12. Common Misconceptions

1. **"JVM TI is the same as JNI."** No: JNI bridges across the Java/native boundary; JVM TI provides APIs/events for tooling.
2. **"Having `jvmtiEnv*` means every operation is allowed."** No: many features require an optional capability and the right phase.
3. **"GetPotentialCapabilities returns currently owned capabilities."** No: you must use `GetCapabilities` to see what was actually granted.
4. **"AddCapabilities can be called anytime to get any capability."** False: some can only be requested in OnLoad or are restricted by the VM/other agents.
5. **"Calling SetEventCallbacks automatically delivers events."** No: `SetEventNotificationMode` is required to enable them.
6. **"ClassFileLoadHook only runs once when loading a class."** No: it can run during redefine/retransform as well.
7. **"Hooks are always in Live."** No: they can be delivered starting in Start, and in Primordial with appropriate capabilities.
8. **"Hooks always have a valid JNIEnv."** False in Primordial: it can be NULL.
9. **"name is always a string."** No: `name` can be null; check before comparing.
10. **"You can freely `free` new_class_data."** No: output must go through `Allocate` and the JVM manages deallocation.
11. **"Every class loaded by the JVM emits the hook identically."** No: the spec allows special-class/optional coverage and timing differences.
12. **"A capable environment can change type after the hook is enabled."** No: `can_retransform_classes` must be granted before the first enable.
13. **"Raw bytes received are always the .class on disk."** No: they may have passed through another agent or been regenerated by the JVM on retransform.
14. **"A callback means the class loaded successfully."** No: the callback runs before the classfile becomes a complete definition.
15. **"Printing from a hook has no overhead."** False: synchronous I/O/locks can slow down class loading.
16. **"A native agent bug just turns into a Java exception."** False: memory/ABI errors can crash the entire JVM.
17. **"Java 17 cannot use JVMTI."** False: JDK 17 has JVMTI headers and the native agent mechanism; you just need an appropriate C compiler.
18. **"You must modify bytecode to prove the hook runs."** No: simply observing `name` is enough to prove the callback was triggered.

## 13. Controlled Native Agent Checklist

1. Choose the matching JVM vendor/version/OS/CPU architecture and corresponding headers.
2. Use `-agentpath` with an **absolute** path if the library search path is not configured.
3. Implement `Agent_OnLoad` to obtain `jvmtiEnv*` via `JavaVM::GetEnv`; check return codes.
4. Call `GetPotentialCapabilities` and request only the needed bits via `AddCapabilities`.
5. If retransform-capable is needed, grant `can_retransform_classes` **before enabling the hook for the first time**.
6. If primordial hooks are needed, consider both `can_generate_early_class_hook_events` and `can_generate_all_class_hook_events` together.
7. Zero-initialize the callback table, call `SetEventCallbacks`, then `SetEventNotificationMode` for the right event.
8. Inside the callback, check `name != NULL`, filter by internal name, and do not retain raw pointers/objects long-term.
9. Do not call JNI when `jni_env` is unavailable or the phase does not permit it.
10. When returning a modified classfile, allocate the buffer with JVMTI `Allocate` and return only valid bytes; do not mutate the input buffer.
11. Avoid class-loader recursion, blocking I/O, large allocations, and global locks inside the hook.
12. Test normal startup, class loads before/after the hook, redefine/retransform if used, multiple agents, custom loaders, and failure paths.
13. Observe setup errors separately from bytecode/linking/runtime errors, avoiding a generic "agent failed" status.
14. Measure startup time, CPU, heap/native memory, GC, event throughput, and class-loading latency.
15. Bound collected data, do not export bytecode containing secrets, and have a way to detach the agent/roll back configuration.

## 14. Self-Check Questions

1. In a JVMTI agent, how does `jvmtiEnv*` differ from `JNIEnv*` in purpose?
2. What are the five phases, and why should you not compare enum values numerically for ordering?
3. Which phase does `VMStart` mark the transition into? Which phase does `VMInit` mark the transition into?
4. How does `GetPotentialCapabilities` differ from `GetCapabilities`?
5. If an agent needs `RetransformClasses`, before which milestone must `can_retransform_classes` be granted?
6. To receive `ClassFileLoadHook` in Primordial, which two capabilities must be combined?
7. After `SetEventCallbacks` registers the function, why might the JVM still not send the hook?
8. In `ClassFileLoadHook`, does `name` use `demo.Target` or `demo/Target`? Can it be null?
9. What is the value of `class_being_redefined` during a new load vs. during redefine/retransform?
10. Why can you not keep the `class_data` pointer across threads for later processing?
11. Which API must the agent use to allocate `new_class_data`, and who frees it?
12. Why can the output of one agent in the pipeline become the input to a subsequent agent?
13. Does a hook invocation prove that the JVM successfully installed the class definition?
14. Why does the demo not request `can_generate_early_class_hook_events`?
15. What output does running `java -cp out demo.Main` without an agent produce, and why is there no JVMTI event log?
16. What errors can stem from wrong native library bitness or ABI?
17. If a C compiler is missing but a JDK is installed, which part of the demo can still be verified?
18. When should you choose `java.lang.instrument` or JFR instead of writing JVMTI native code?

## 15. Conclusion and Official References

**JVM TI = a native tooling API with explicit capabilities and phases.** A native agent must obtain an environment, request permissions at the right time, and register and enable events before expecting callbacks. `ClassFileLoadHook` is the point where the JVM has classfile bytes before building the class representation; it can occur across multiple JVM phases and during redefine/retransform operations, not only at Java application startup.

Three most important rules:

- **Capabilities are not granted by default:** query `GetPotentialCapabilities`, request `AddCapabilities`, verify with `GetCapabilities` when needed; specifically, `can_retransform_classes` must be present before the first hook enable if a capable environment is desired.
- **Phases restrict what can be done:** OnLoad, Primordial, Start, Live, and Dead do not allow the same set of functions; early callbacks may not have a valid `JNIEnv`.
- **Callbacks have ownership boundaries:** check nullable `name`, keep logic short, do not mutate raw input, and if returning new class bytes, allocate via JVMTI `Allocate` for the JVM to manage.

When you only need to see when a class is loaded by the JVM, a native agent filtering a single name like `demo/Target` without modifying bytes is sufficient to understand the mechanism. When production instrumentation is needed, add parser/verification, an idempotence strategy, native memory management, event volume limits, error observability, and cross-JVM/OS testing.

### Official References

- [Oracle JDK 21 — JVM Tool Interface](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html): JVMTI specification, phases, capabilities, events, and lifecycle.
- [Oracle JDK 21 — Class File Load Hook](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html#ClassFileLoadHook): callback signature, timing, buffers, input/output, and ordering.
- [Oracle JDK 21 — Capability Management](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html#GetPotentialCapabilities): `GetPotentialCapabilities`, `AddCapabilities`, `GetCapabilities`.
- [Oracle JDK 21 — Get Phase](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html#GetPhase): `jvmtiPhase` enum and phase-corresponding functions.
- [Oracle — The JVM Tool Interface: How VM Agents Work](https://www.oracle.com/technical-resources/articles/javase/jvm-tool-interface.html): architectural examples of native tooling agents and event callbacks.
- [Oracle JDK 17 — Java Instrumentation package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): comparing Java agents with native JVMTI agents.
