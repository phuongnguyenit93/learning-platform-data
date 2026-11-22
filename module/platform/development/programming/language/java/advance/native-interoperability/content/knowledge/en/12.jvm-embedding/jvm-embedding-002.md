# Preparing JavaVMInitArgs, JVM Options, and Linking Against the JVM Library

## 1. Why Does a Native Application Need JavaVMInitArgs?

In the standard model, the **java launcher** starts the JVM and then invokes the **main** method of a Java class. In the **JVM embedding** model (*embedding*), the C/C++ program is the host process: it loads the virtual machine library itself, configures the JVM, calls **JNI_CreateJavaVM**, and then uses **JNIEnv** to find classes and invoke Java methods. The API that performs this is the **JNI Invocation API**, declared in **jni.h**.

Typical flow:

~~~text
Native host (C/C++)
       |
       |  Select compatible JDK/runtime and ABI
       |  Prepare JavaVMOption[] and JavaVMInitArgs
       v
JNI_CreateJavaVM(...)
       |
       +----> JavaVM* : JVM handle, used for lifecycle/thread management
       |
       +----> JNIEnv* : JNI interface valid only for the current thread
       |
       v
FindClass -> GetStaticMethodID -> CallStatic...Method
       |
       |  Check Java exceptions, release JNI local refs
       v
DestroyJavaVM(...)
       |
       v
Native host completes
~~~

**JavaVMInitArgs** is the configuration at VM creation time. It is not a Java object, not Java heap memory, and not a mechanism to arbitrarily change all JVM flags after the VM is already running. **JNI_CreateJavaVM** is the initialization boundary; which library to select, which options to pass, and where to find classes must be resolved before or during that initialization.

**Clearly distinguish the two JNI directions:**

- **Java calling native**: The JVM is already running, Java calls **System.loadLibrary** and then calls a **native** method; the native library is loaded *into the existing JVM*.
- **Native embedding Java**: The C/C++ process is the host, linking/loading **libjvm.so**, **jvm.dll**, or an OS-specific variant and calling **JNI_CreateJavaVM**. A Java **native** method is not needed to initialize the VM.

Both models use the same **JNIEnv** interface when working with Java objects, but the initialization procedure, library paths, and shutdown responsibilities differ.

## 2. Structure of JavaVMInitArgs and JavaVMOption

Abbreviated declarations in the JNI Invocation API:

~~~c
typedef struct JavaVMOption {
    char *optionString;
    void *extraInfo;
} JavaVMOption;

typedef struct JavaVMInitArgs {
    jint version;
    jint nOptions;
    JavaVMOption *options;
    jboolean ignoreUnrecognized;
} JavaVMInitArgs;
~~~

| Field | Purpose | Usage |
| --- | --- | --- |
| **version** | JNI interface version requested by the host | For example **JNI_VERSION_1_8** for a host using APIs available since JNI 8; does **not** select the Java language level |
| **nOptions** | Number of valid elements in **options** | Must match the array length; not the total character count and does not count a null-terminating element |
| **options** | Pointer to the **JavaVMOption** array | Each element contains one complete option string |
| **ignoreUnrecognized** | How to handle unrecognized options | Usually set to **JNI_FALSE** when early detection of misconfiguration is needed |
| **optionString** | JVM option as a char string | For example **-Djava.class.path=out**, **-Xmx128m** |
| **extraInfo** | Special data for certain option hooks | Set to **NULL** for standard string options |

Basic conditions: all pointers must be valid at the time **JNI_CreateJavaVM** is called; **nOptions** and the option array must match; each **optionString** must be a NUL-terminated C string. JNI specifies that option strings use the **platform default encoding**; when paths/values contain special Unicode characters, check the runtime/OS encoding behavior rather than assuming all UTF-8 C strings work identically.

C17 configuration initialization example:

~~~c
#include <jni.h>
#include <stddef.h>

static char classpathOption[] = "-Djava.class.path=out";
static char modeOption[]      = "-Ddemo.mode=embedded";
static char heapOption[]      = "-Xmx128m";

static JavaVMOption options[] = {
    { classpathOption, NULL },
    { modeOption, NULL },
    { heapOption, NULL }
};

JavaVMInitArgs args = {0};
args.version = JNI_VERSION_1_8;
args.nOptions = (jint)(sizeof options / sizeof options[0]);
args.options = options;
args.ignoreUnrecognized = JNI_FALSE;
~~~

The snippet above is a **data preparation fragment**, not yet a program with **main**. The value **-Djava.class.path=out** assumes the host runs from the project directory where **out/** contains the **.class** files. In a real distributed application, paths should be constructed from a controlled installation location; do not depend on an arbitrary working directory.

Why use **JavaVMInitArgs args = {0}**? This initializes unassigned fields to 0/null, avoiding garbage data. However, you must still assign **version**, **nOptions**, **options**, and the **ignoreUnrecognized** policy according to the contract. In larger codebases, prefer keeping those option strings and arrays alive until **JNI_CreateJavaVM** completes, rather than pointing to buffers whose lifetime has expired.

## 3. Choosing the JNI Version: Do Not Confuse with the JDK Version

**JNI_VERSION_1_8**, **JNI_VERSION_1_6**, or newer JNI version constants are **native interface version codes**. They do not require the JVM to run Java 8 bytecode, nor do they turn JDK 21 into JDK 8. For example, a Java program compiled with JDK 21 can still be hosted using **JNI_VERSION_1_8** if the required JNI APIs are compatible.

~~~c
args.version = JNI_VERSION_1_8;
jint code = JNI_CreateJavaVM(&vm, (void **)&env, &args);
~~~

If the JDK in use does not support the requested version, initialization may fail with an appropriate JNI error code. Do not guess the version code based on **java -version** and assign an arbitrary number; use the constant provided by **jni.h** from the JDK being built against and check the result from the runtime.

**JNI_GetDefaultJavaVMInitArgs** is an optional function when you need to query a default configuration and check version support. Usage:

~~~c
JavaVMInitArgs defaults = {0};
defaults.version = JNI_VERSION_1_8;

jint rc = JNI_GetDefaultJavaVMInitArgs(&defaults);
if (rc != JNI_OK) {
    /* The requested JNI version may not be supported. */
}
~~~

This is also a **fragment**; the complete example in section 6 uses **JavaVMInitArgs** directly, in accordance with modern JNI guidance: it is not mandatory to call **JNI_GetDefaultJavaVMInitArgs** before **JNI_CreateJavaVM**. Do not mix fields from a previously retrieved default configuration with another options array while forgetting to update **nOptions**.

## 4. Passing JVM Options via JavaVMOption

**JavaVMOption.optionString** holds one option per element. It is neither a full shell command line nor a space-separated list.

| Passed Option | Practical Meaning | Notes |
| --- | --- | --- |
| **-Djava.class.path=out** | Class path for loading the application's Java classes | Useful for **FindClass** from the host with classpath application classes |
| **-Ddemo.mode=embedded** | Custom application system property | Can be read with **System.getProperty("demo.mode")** |
| **-Djava.library.path=/opt/app/native** | Search path for native libraries for Java operations such as **System.loadLibrary** | **Not** the OS loader's search path for **libjvm.so** itself |
| **-Xms32m** | Initial heap size, JVM-dependent | Commonly used on HotSpot; verify support and environment limits |
| **-Xmx128m** | Maximum heap size, JVM-dependent | Heap does not equal total process memory: there is also native memory, stacks, code cache, etc. |
| **-verbose:jni** | Prints JNI information according to runtime capabilities | Used for diagnostics; increases log volume |
| **--module-path=/opt/app/mods** | Module path in a supported module environment | Requires a single option string with **=** |
| **--add-modules=my.module** | Selects root modules if needed | Verify that the module actually exists |
| **--add-opens=java.base/java.lang=ALL-UNNAMED** | Opens a specific package for deep reflection within the stated scope | Grant only when justified; affects module boundaries |

**“Standard” JNI Invocation API options** include **-D...**, **-verbose...**, and the special hooks **vfprintf**, **exit**, **abort**. Many **-X...** and **-XX:...** flags are implementation-specific; do not treat them as a portable contract across all JVMs. Module options in JNI must have the form **--option=value**, such as **--module-path=mods**; do not pass a pair of strings **"--module-path"**, **"mods"** as two command-line arguments.

### Important Differences Between the Launcher and the Invocation API

The shell command:

~~~bash
java -cp out -Xmx128m demo.EmbeddedGreeting
~~~

is parsed by the **java launcher**: **-cp** takes an argument; the launcher knows which Java class to run. When using **JNI_CreateJavaVM**, there is no launcher parsing commands and automatically finding **main**. The host must pass VM options via **JavaVMOption**, for example:

~~~c
options[0].optionString = "-Djava.class.path=out";
options[1].optionString = "-Xmx128m";
~~~

After initialization succeeds, the host **calls JNI FindClass/GetStaticMethodID/Call...Method itself**. Do not pass the entire **"java -cp out demo.EmbeddedGreeting"** as a single **optionString**; this is not a shell command execution interface.

### ignoreUnrecognized: JNI_TRUE Does Not Mean “Ignore Everything”

According to the JNI Invocation API, when **ignoreUnrecognized == JNI_TRUE**, the JVM is asked to ignore unrecognized options **starting with -X or an underscore _**. This does **not** mean every invalid string is accepted; initialization errors, path issues, and implementation restrictions still have to be handled.

When **ignoreUnrecognized == JNI_FALSE**, an unrecognized option causes initialization to fail (usually **JNI_ERR**). Prefer **JNI_FALSE** for systems that need to fail fast: a typo in JVM configuration should not silently turn into running with defaults.

**Do not skip verification even when CreateJavaVM returns JNI_OK.** Read back the required system properties, runtime version, actual class loader/modules, and run a small smoke test to confirm the values the application depends on.

## 5. Linking Against the JVM Library: Three Distinct Stages

A C/C++ host that wants to call **JNI_CreateJavaVM** must have the JNI headers, function declarations, and a way to locate the JVM implementation. Three layers of responsibility:

~~~text
Compile time:
    jni.h + jni_md.h
         |
         v
    Compiler knows JavaVMInitArgs, JNI types, JNI_CreateJavaVM

Link time:
    -ljvm / jvm.lib or dlsym/GetProcAddress
         |
         v
    Linker resolves the JNI_CreateJavaVM symbol

Runtime:
    OS loader locates libjvm.so / jvm.dll / libjvm.dylib
         |
         v
    JVM is loaded; JNI_CreateJavaVM can then initialize the runtime
~~~

**Headers are distinct from libraries:**

- **$JAVA_HOME/include/jni.h**: declares common JNI types and functions.
- **$JAVA_HOME/include/linux/jni_md.h**, **include/win32/jni_md.h**, or **include/darwin/jni_md.h**: ABI/OS-dependent definitions.
- **$JAVA_HOME/lib/server/libjvm.so**: JVM runtime on many Linux HotSpot JDK distributions.
- **$JAVA_HOME/lib/server/libjvm.dylib**: common path on macOS HotSpot.
- **%JAVA_HOME%\lib\jvm.lib**: import library used when linking with MSVC on Windows; **%JAVA_HOME%\bin\server\jvm.dll**: DLL loaded by the OS loader at runtime. Actual layout must be verified per JDK distribution.

Library paths **depend on the JDK vendor, version, architecture, and packaging**. Do not hardcode a system-wide JDK path for a distributed application. **JAVA_HOME** is an environment convention that helps scripts locate the JDK; it does not automatically ensure the OS dynamic loader knows the location of libjvm.

### 5.1. Build-Time Linking with a Dynamic Library

On Linux, the compiler uses **-I** to find headers, **-L** to find libraries at link time, and **-ljvm** to resolve symbols from the JVM. At runtime, the Linux loader still needs to find **libjvm.so** via **RPATH/RUNPATH**, loader configuration, or an appropriate runtime path.

A common option for demos is **-Wl,-rpath,...**; for official distributions, consider relative paths from the application location or a managed library configuration mechanism. To inspect binaries, **ldd** and **readelf -d** can be used in a trusted environment.

### 5.2. Loading the Library at Runtime Using OS APIs

If an application allows selecting among multiple installed JVMs, the host can use **dlopen + dlsym** (POSIX/Linux) or **LoadLibrary + GetProcAddress** (Windows) to locate **JNI_CreateJavaVM**. In that case, linking directly against **-ljvm** at build time is not strictly necessary, but you must:

1. Open the correct JVM library compatible with the architecture/ABI;
2. Look up the required JNI symbols, ensuring the exact function type and calling convention;
3. Keep the library alive for the entire JVM lifecycle;
4. Thoroughly handle DLL/dependency load errors and clean up resources once the VM has finished.

The complete example code below uses **direct linking with the dynamic library** to focus on **JavaVMInitArgs**; it does not implement a custom JDK locator.

### 5.3. Do Not Confuse the Three Paths

| Path | Used By Which Component? | Example |
| --- | --- | --- |
| Java classpath | Java class loader | **-Djava.class.path=out** |
| Java native library path | JVM locating native libraries for **System.loadLibrary** | **-Djava.library.path=/opt/app/native** |
| OS loader path for the JVM | OS locating **libjvm.so/jvm.dll** so the C host can initialize the VM | RPATH/RUNPATH, PATH, or dynamic loading mechanism |

When encountering a class-not-found error, check **classpath/module path**; when encountering **UnsatisfiedLinkError** from Java, check the native library path, dependencies, and ABI; when the C executable fails to start due to missing **libjvm.so**, check the **OS loader path**. Fixing one path usually **does not automatically fix** an issue belonging to another path.

## 6. Complete Example: C Initializes the JVM, Calls Java, and Destroys the JVM

The following example targets JDK 17+ and a HotSpot-compatible distribution with the paths shown in section 5. It passes **three VM options**, checks the **JNI_CreateJavaVM** return code, calls a Java method via JNI, and then calls **DestroyJavaVM**. The Java class does not need a **main** method because the C process explicitly chooses the method to invoke.

### 6.1. Java File: src/demo/EmbeddedGreeting.java

~~~java
package demo;

public final class EmbeddedGreeting {
    private EmbeddedGreeting() {
    }

    public static int compute(int input) {
        String mode = System.getProperty("demo.mode", "missing");
        System.out.println("Java mode: " + mode);
        return Math.addExact(Math.multiplyExact(input, 2), 1);
    }
}
~~~

**Math.multiplyExact** and **Math.addExact** check for overflow; with input **21**, the exact result is **43**. Printing **Java mode: embedded** proves that the **-Ddemo.mode=embedded** option actually reached the JVM.

### 6.2. C File: host/embed_jvm.c

~~~c
#include <jni.h>
#include <stdio.h>
#include <stdlib.h>

/* Each option is a NUL-terminated C string and persists during VM initialization. */
static char classpath_option[] = "-Djava.class.path=out";
static char mode_option[] = "-Ddemo.mode=embedded";
static char heap_option[] = "-Xmx128m";

int main(void) {
    JavaVMOption options[] = {
        { classpath_option, NULL },
        { mode_option, NULL },
        { heap_option, NULL }
    };

    JavaVMInitArgs args = {0};
    args.version = JNI_VERSION_1_8;
    args.nOptions = (jint)(sizeof options / sizeof options[0]);
    args.options = options;
    args.ignoreUnrecognized = JNI_FALSE;

    JavaVM *vm = NULL;
    JNIEnv *env = NULL;

    jint created = JNI_CreateJavaVM(&vm, (void **)&env, &args);
    if (created != JNI_OK || vm == NULL || env == NULL) {
        fprintf(stderr, "JNI_CreateJavaVM failed: %d\n", (int)created);
        return EXIT_FAILURE;
    }

    int exit_code = EXIT_FAILURE;
    jclass cls = (*env)->FindClass(env, "demo/EmbeddedGreeting");

    if (cls == NULL) {
        goto cleanup;
    }

    jmethodID compute = (*env)->GetStaticMethodID(
            env, cls, "compute", "(I)I");
    if (compute == NULL) {
        goto cleanup;
    }

    jint answer = (*env)->CallStaticIntMethod(
            env, cls, compute, (jint)21);
    if ((*env)->ExceptionCheck(env)) {
        goto cleanup;
    }

    printf("C result: %d\n", (int)answer);
    exit_code = EXIT_SUCCESS;

cleanup:
    if ((*env)->ExceptionCheck(env)) {
        (*env)->ExceptionDescribe(env);
        (*env)->ExceptionClear(env);
        exit_code = EXIT_FAILURE;
    }

    if (cls != NULL) {
        (*env)->DeleteLocalRef(env, cls);
    }

    jint destroyed = (*vm)->DestroyJavaVM(vm);
    if (destroyed != JNI_OK) {
        fprintf(stderr, "DestroyJavaVM failed: %d\n", (int)destroyed);
        exit_code = EXIT_FAILURE;
    }

    return exit_code;
}
~~~

This is a **standalone C17 program with main**, not a JNI native method called by Java. **JNI_CreateJavaVM** and **DestroyJavaVM** belong to the Invocation API; C uses **(*env)->...** because in C **JNIEnv** is based on a pointer to a function table. In C++, the corresponding syntax is typically **env->FindClass(...)** and **vm->DestroyJavaVM()**.

**Step-by-step verification:**

1. **options[]** contains the classpath, custom property, and heap limit.
2. **args** is zero-initialized and assigned the required fields; **ignoreUnrecognized=JNI_FALSE** helps catch option errors.
3. **JNI_CreateJavaVM** returns **JavaVM*** and the calling thread's **JNIEnv***. If creation fails, do not use these two pointers as if the VM existed.
4. **FindClass("demo/EmbeddedGreeting")** uses the **JVM internal class name** with **/**. The class file must be at **out/demo/EmbeddedGreeting.class**.
5. **GetStaticMethodID** with descriptor **(I)I**: takes one **int**, returns one **int**. The Java method is **static**; do not use **CallIntMethod**, which is for object instances.
6. **CallStaticIntMethod** invokes Java, then **ExceptionCheck** determines whether a Java exception occurred. The return value must not be trusted if there is a pending exception.
7. The cleanup branch prints the exception via **ExceptionDescribe**, intentionally clears the pending exception, calls **DeleteLocalRef** to release the class reference, and calls **DestroyJavaVM**.
8. The code calls **DestroyJavaVM** even if finding the class or method fails after the VM was successfully created. If VM creation failed earlier, the code does not call Destroy.

The code makes a single short Java call without spawning worker threads or long-running shutdown hooks. For real applications, ownership and shutdown must be designed when multiple Java/native threads use the VM concurrently.

### 6.3. Building on Linux: Compile Java, Link C with libjvm.so

From the project directory containing **src/demo/EmbeddedGreeting.java** and **host/embed_jvm.c**:

~~~bash
# JAVA_HOME points to the JDK 17+ directory (same architecture as the C compiler).
mkdir -p out

javac -d out src/demo/EmbeddedGreeting.java

cc -std=c17 -Wall -Wextra -Wpedantic \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  host/embed_jvm.c \
  -L"$JAVA_HOME/lib/server" \
  -Wl,-rpath,"$JAVA_HOME/lib/server" \
  -ljvm -o embed_jvm

./embed_jvm
~~~

Note: **-ljvm** appears after the object/source files that need its symbols to satisfy linker ordering policies. The **-Wl,-rpath,...** flag embeds the JVM search path into the executable in the Linux example; using an absolute path from the build environment may not be suitable when moving the executable to another machine. For distributed systems, choose a managed path and verify it with loader tools.

A **valid and predictable** stdout on a successful build/run, with no additional runtime logs:

~~~text
Java mode: embedded
C result: 43
~~~

If the environment defines **JAVA_TOOL_OPTIONS** or JVM logging is enabled, additional messages may appear on stderr/stdout. The two lines above are the program's primary output, not necessarily the entire output in every environment.

### 6.4. Equivalent Guidance on Windows (MSVC)

With a Windows x64 HotSpot JDK and an MSVC Developer Command Prompt of the same architecture, link against **jvm.lib** and ensure **jvm.dll** along with JDK dependencies can be found by the loader:

~~~bat
mkdir out
javac -d out src\demo\EmbeddedGreeting.java

cl /nologo /W4 ^
  /I"%JAVA_HOME%\include" ^
  /I"%JAVA_HOME%\include\win32" ^
  host\embed_jvm.c ^
  /link /LIBPATH:"%JAVA_HOME%\lib" jvm.lib /OUT:embed_jvm.exe

set "PATH=%JAVA_HOME%\bin\server;%JAVA_HOME%\bin;%PATH%"
embed_jvm.exe
~~~

Lines with **^** are for **cmd.exe**, not PowerShell. If the JDK distribution places **jvm.lib/jvm.dll** at different paths than shown above, locate the exact positions before building/running. The runtime **jvm.dll** must not be substituted with an arbitrary DLL of the same name; the ABI/architecture and runtime dependencies must match. On macOS, platform-dependent headers are typically in **include/darwin**, the JVM library is typically at **lib/server/libjvm.dylib**, and the linker and loader follow **dyld** rules, requiring distribution-specific configuration.

**Distinction:** the C host embedding the JVM links against **jvm.lib/libjvm.so**; there is no need to build a **libEmbeddedGreeting.so**. The **EmbeddedGreeting** class in the example is ordinary Java and declares no **native** methods.

## 7. JNI_GetCreatedJavaVMs, the Single-VM Limit, and Lifecycle

The Invocation API provides:

~~~c
jint JNI_GetCreatedJavaVMs(
        JavaVM **vmBuf, jsize bufLen, jsize *nVMs);
~~~

It reports the Java VMs currently being created or already created in the process, but the JNI specification **does not support creating multiple independent JVMs within the same process**. Calling **JNI_CreateJavaVM** again while a VM is already running is not a way to open a new “Java instance” to isolate tenants or configurations. When multiple independent JVM configurations are needed, using **separate OS processes** is a cleaner design direction.

**DestroyJavaVM** does not necessarily return immediately: it may wait for **non-daemon threads** to terminate, including native threads attached as non-daemon. Do not call destroy while unmanaged Java workers or attached native workers are still running. Shutting down the JVM does not guarantee that the JVM can be successfully re-initialized in the same process; many implementations do not support the expected create–destroy–create cycle.

Invocation API documentation also advises against creating the VM directly on the **primordial process thread** on some OSes due to stack and thread-handling issues; for a production host, a **dedicated native thread** with sufficient stack can be created to initialize and coordinate the VM. The example in section 6 chooses **main** for ease of practice, not to prescribe threading structure for production hosts.

## 8. JavaVM* vs. JNIEnv*: Common Threading Mistakes

Once the JVM is created:

- **JavaVM*** is the VM handle that can be stored according to the application's management scope; it is used for **AttachCurrentThread**, **GetEnv**, **DetachCurrentThread**, and **DestroyJavaVM**.
- **JNIEnv*** is valid only in the **thread that owns it**. Do not save **JNIEnv*** from the VM-creating thread and pass it directly to another native worker.
- A native worker wanting to call Java must obtain its own **JNIEnv*** via **AttachCurrentThread**, and call **DetachCurrentThread** before the thread exits if it was attached by native code.
- **AttachCurrentThreadAsDaemon** attaches in daemon state, which affects shutdown waiting. If a thread is already attached, calling attach again does not automatically change its daemon status.

Illustration:

~~~text
Thread A: JNI_CreateJavaVM -> (vm, envA)
             |
             | vm can be passed according to host policy
             v
Thread B: AttachCurrentThread(vm, &envB)
             |
             +--> use envB to make JNI calls in Thread B
             |
             +--> DetachCurrentThread(vm)
~~~

**Do not** use **envA** in Thread B. Likewise, do not use a **jclass/jobject local reference** created in Thread A inside Thread B without creating a reference with an appropriate lifetime, typically via **NewGlobalRef**. This is a JNI management rule independent of having classpath and JavaVMInitArgs configured correctly.

## 9. Practical Options: Classpath, Module Path, Native Library Path

### 9.1. Java Class Not Found

The host calls:

~~~c
jclass cls = (*env)->FindClass(env, "demo/EmbeddedGreeting");
~~~

If the class is compiled into **out/demo/EmbeddedGreeting.class** but the host runs from a different directory, the option **-Djava.class.path=out** points to a different relative location. In that case, **FindClass** may return **NULL** and leave a pending **NoClassDefFoundError**. To avoid this:

1. Verify that the Java class output actually exists;
2. Use an absolute classpath or one anchored to the installation location;
3. Verify that the internal name **demo/EmbeddedGreeting** matches **package demo**;
4. Check **ExceptionDescribe** on actual errors; do not attempt to cast **NULL** into a valid reference.

On Linux, the separator for multiple classpath entries is typically **:**; on Windows, it is typically **;**. **-Djava.class.path=out:lib/a.jar** cannot be used verbatim on Windows. The java launcher and module system have their own additional rules; do not infer the classpath from the OS **PATH**.

### 9.2. Module Options and Access Permissions

In a modular Java application, you may need **--module-path=mods** together with **--add-modules=...** to resolve target modules, or **--add-opens/--add-exports** options when genuinely required. With the JNI Invocation API, each module option must be **a single optionString containing =**, for example:

~~~c
static char module_path[] = "--module-path=/opt/app/mods";
static char add_module[] = "--add-modules=example.module";
static char opens[] = "--add-opens=java.base/java.lang=ALL-UNNAMED";
~~~

These are **illustrative option strings**, not part of the simple Java program in section 6. Do not copy **--add-opens** into every application to “fix all IllegalAccessException”: you must understand which module, which package, and which target receives the permission. Opening a package does not solve an incorrect **FindClass** or an unloaded JVM library.

### 9.3. Native Path Differs from JVM Path

**-Djava.library.path** affects how Java locates native libraries via **System.loadLibrary**, but it does not solve the error where the native executable cannot find **libjvm.so/jvm.dll** before entering **main**. On Linux, use **ldd ./embed_jvm** or **readelf -d ./embed_jvm** to inspect dependencies/RUNPATH. On Windows, use a DLL dependency analysis tool and check **PATH**. Only inspect trusted binaries when using loader tools.

## 10. Detecting and Handling Initialization Errors

**JNI_CreateJavaVM** returns **jint**: **JNI_OK** on success, an appropriate negative code on failure. Several common JNI error constants are declared in **jni.h**:

| Code | Meaning |
| --- | --- |
| **JNI_OK** | Success |
| **JNI_ERR** | General error |
| **JNI_EDETACHED** | Current thread is not attached when calling an API that requires attachment, commonly seen with **GetEnv** |
| **JNI_EVERSION** | Requested JNI version is not supported |
| **JNI_ENOMEM** | Not enough memory |
| **JNI_EEXIST** | VM already exists in a context that returns the appropriate error |
| **JNI_EINVAL** | Invalid arguments |

Do not rely on a single specific code as the sole diagnostic across all JVMs. Log the error code, options, and runtime messages; when initialization fails, there is no valid **JNIEnv** yet to call **ExceptionDescribe**. A JVM initialization error may appear on stderr, in VM logs, or through implementation-specific diagnostics.

Once the VM is created and a call to **FindClass/GetStaticMethodID/CallStatic...Method** fails, there may be a **pending Java exception**. The sample code in section 6 uses **ExceptionCheck/ExceptionDescribe/ExceptionClear** to print the error and clean up. **ExceptionClear** in the example is a decision of the native host; in an application with a Java caller, there are cases where the exception should be kept pending so the JVM throws it back to Java rather than silently clearing it.

### Symptoms and Checks Table

| Symptom | Common Cause | Verification Step |
| --- | --- | --- |
| Compiler reports **jni.h** not found | Missing **-I** path or using a JRE without headers | Check JDK, **JAVA_HOME/include**, OS-specific headers |
| Linker **undefined reference to JNI_CreateJavaVM** | Missing **-ljvm**, wrong position or link argument order | Check **-L**, **-ljvm**, symbols, and architecture |
| Linux: **libjvm.so: cannot open shared object file** | Runtime linker cannot find the JVM | Check RUNPATH/RPATH, JDK distribution, and dependencies |
| Windows: **jvm.dll was not found** | DLL or dependency is not on the loader search path | Check **PATH**, JDK bitness, DLL dependencies |
| **JNI_CreateJavaVM** returns an error | Invalid option, unsupported version, out of memory, VM conflict | Log options, return code, verify on target runtime |
| **NoClassDefFoundError** on **FindClass** | Wrong classpath/module path or invalid class | Check package, paths, **-Djava.class.path** |
| **NoSuchMethodError** on **GetStaticMethodID** | Wrong method name/static modifier/descriptor | Check descriptor, **javap -s** if needed |
| Java exception after **CallStaticIntMethod** | Java logic threw an error (e.g., overflow) | **ExceptionCheck/ExceptionDescribe** and propagate/log error appropriately |
| **DestroyJavaVM** hangs for a long time | Non-daemon threads still active | Analyze thread lifecycle, ensure workers finish/detach |
| Fails to load JVM when running on another machine | Hardcoded RPATH, wrong architecture, missing dependency, or different JDK | Package/select compatible runtime, run integration smoke test |

## 11. Limitations and Architectural Decisions Before Embedding the JVM

### 11.1. One Process Is Not a Multi-JVM Sandbox

The JNI specification does not support creating multiple independent VMs in one process. If you want to isolate tenants, classpaths, heap limits, and completely different JDK versions, spawning separate processes and communicating over IPC/RPC may be easier to manage. **ClassLoader** creates class namespaces inside one VM, but does not turn them into multiple independent JVMs.

### 11.2. Max Heap Differs from Total Native Host Memory

**-Xmx128m** limits the Java heap on HotSpot, not the entire process. You must account for the host's native allocations, JNI global refs, direct buffers, thread stacks, metaspace, JIT code cache, and other runtime components. Sizing the heap based solely on total machine RAM while ignoring the native host can lead to memory pressure or initialization failures.

### 11.3. Startup Options Have Security/Operational Impact

If the host accepts options from configuration files or user input, you must control flags that can load agents, open packages, alter the classpath, or load native code. These options can change the code executed inside the native process. Do not treat **ignoreUnrecognized=JNI_TRUE** as option validation.

With HotSpot, **JAVA_TOOL_OPTIONS** can affect options when **JNI_CreateJavaVM** runs, especially for agents/diagnostics; under certain conditions the runtime restricts this variable. Unlike **JDK_JAVA_OPTIONS**, which is primarily parsed by the **java launcher**, an embedded application's environment can still be influenced by JVM configuration variables. When debugging “why unexpected options were received”, inspect the process launch environment rather than looking only at the **options[]** array.

### 11.4. Version/ABI of Headers, libjvm, and Host

Use headers from a JDK compatible with the runtime being linked/loaded. A 64-bit JVM library cannot be loaded into a 32-bit native process. Compiler/ABI, OS, calling convention, and dependencies must match. Do not select a JDK based purely on version string while ignoring the platform.

### 11.5. Shutdown Is a Lifecycle Contract

Only call **DestroyJavaVM** when it is clearly defined who owns the VM, who stops Java workers, when native threads detach, and which callbacks/shutdown hooks are still active. If the host must run for weeks, keeping the JVM lifecycle tied to the process is sometimes the right design; it is not necessary to create/destroy per request. In production code, check the destroy return code and have a resource cleanup path even when Java code throws an exception.

## 12. Self-Check Questions

**Question 1.** If you use **args.version=JNI_VERSION_1_8** and compile classes with JDK 21, will the host automatically use Java 8 semantics?

**Answer:** No. The version in **JavaVMInitArgs** is a JNI interface request. The Java class file, Java language level, and JVM runtime version are separate concerns. The VM must still be capable of loading the compiled bytecode.

**Question 2.** You passed **-Djava.library.path=/opt/native**, yet the native executable reports **libjvm.so** is missing before running. Why?

**Answer:** This is an OS loader error locating the JVM library, occurring before JavaVMInitArgs is processed. **java.library.path** belongs to Java's mechanism for loading native libraries; you need to fix RPATH/RUNPATH, the library search path, or the host's JVM loading mechanism.

**Question 3.** Why shouldn't **-cp** and **out** be passed as two JavaVMOptions and expect the host to find Java classes?

**Answer:** That is how the java launcher accepts command-line arguments, not the Invocation API option contract. To pass a classpath to the VM from native code, for example use **-Djava.class.path=out** as a single option string and call **FindClass** after startup.

**Question 4.** Does **ignoreUnrecognized=JNI_TRUE** guarantee that all misspelled options are ignored?

**Answer:** No. JNI defines ignoring unknown options prefixed with **-X** or **_**; other errors and implementation policies still apply. Prefer **JNI_FALSE** when you want to fail fast.

**Question 5.** Having created the VM in Thread A, can you pass **JNIEnv*** from A to Thread B to call Java?

**Answer:** No. **JNIEnv*** is valid only in its corresponding thread. B uses **JavaVM*** to attach and obtain its own **JNIEnv***, then detaches before exiting.

**Question 6.** **DestroyJavaVM** has been called but has not returned yet; what might this be related to?

**Answer:** The JVM may be waiting for non-daemon threads to terminate; native threads attached as non-daemon can also keep the VM alive. You must design ordered shutdown and detachment rather than forcing destruction regardless of active threads.

## Standard Reference Documentation

- Oracle JNI Specification (Java SE 21), **The Invocation API**: https://docs.oracle.com/en/java/javase/21/docs/specs/jni/invocation.html
- Oracle JNI Specification, **JNI Types and Data Structures**: https://docs.oracle.com/en/java/javase/21/docs/specs/jni/types.html
- Oracle JNI Specification, **JNI Functions**: https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html
- Oracle JNI Specification, **Design Overview: Compiling, Loading and Linking Native Methods**: https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html
- Oracle Java 21 **java launcher**: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Oracle Java 22 Troubleshooting, **JAVA_TOOL_OPTIONS**: https://docs.oracle.com/en/java/javase/22/troubleshoot/environment-variables-and-system-properties.html

**Remember:** A host embedding the JVM must solve **three distinct layers**: preparing **JavaVMInitArgs/options** correctly, linking and loading the **JVM library** correctly, and using the **JNIEnv/JavaVM lifecycle** properly to call Java and shut down. Misconfiguring the classpath, VM options, and loader paths often manifests as different errors; verifying each layer helps pinpoint the root cause.