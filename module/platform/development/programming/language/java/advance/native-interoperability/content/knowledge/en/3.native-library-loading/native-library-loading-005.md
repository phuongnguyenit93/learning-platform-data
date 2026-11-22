# Native Library Loading in Class Initialization and Handling Failures with UnsatisfiedLinkError

## Objectives

After this lesson, you can:

1. Explain when the JVM runs a **static initializer** and the difference between **loading**, **linking**, and **initialization**.
2. Correctly write a **System.loadLibrary** call inside a **static** block when a Java class requires a native library.
3. Explain why an **UnsatisfiedLinkError** during initialization can put a class into an erroneous state and why subsequent uses can throw **NoClassDefFoundError**.
4. Distinguish between **required** libraries and **optional** libraries, and choose fail-fast, controlled error handling, or a valid Java fallback accordingly.
5. Diagnose errors involving library names, search paths, native dependencies, architecture/ABI, JNI symbols, class loaders, and native access permissions.
6. Test both the successful loading path and the failure path without relying on the assumption that catching an exception is enough to recover a class.

## 1. Context: a Java class needs native code

In the Java Native Interface (JNI), a Java class can declare **native** methods; the body is implemented in a machine-code library for a specific OS/CPU. The JVM must locate and load the library containing the corresponding implementation before native calls can execute successfully.

A common way to write this is:

~~~java
public final class NativeCodec {
    static {
        System.loadLibrary("example_codec");
    }

    private NativeCodec() {
    }

    public static native int decode(byte[] input);
}
~~~

This is a **JNI structure illustration**, not a standalone runnable program: to call **decode**, you must provide a real native library with a compatible symbol/signature. The string **"example_codec"** is the **logical name** of the library, not a path or a full DLL/SO/dylib filename.

When the JVM **initializes NativeCodec**, it executes the **static** block, calling **System.loadLibrary("example_codec")**. If loading succeeds, the process has the library ready for the JVM to link native methods according to JNI rules. If it fails and the error is not handled inside the initializer block, **NativeCodec is not initialized successfully**.

Placing the library load call in a static initializer has advantages: it keeps the loading logic close to the class that needs native code and avoids repeated load calls before each operation. However, it also creates an important constraint: **a failure at initialization time can render the entire class unusable in the current class loader**.

## 2. When is a static block executed?

It is necessary to distinguish three steps in the class lifecycle:

| Step | Meaning | Does it mean running the static initializer? |
| --- | --- | --- |
| **Loading** | The class loader locates/defines the representation of the class | No |
| **Linking** | Verify, prepare, and possibly resolve references | No |
| **Initialization** | Runs static field initializers and static blocks in declaration order | **Yes** |

According to the Java Language Specification (JLS §12.4), initialization typically occurs immediately before the **first active use** of the class, such as creating an instance, invoking a static method declared by the class, writing a static field, or reading a static field that is not a compile-time constant. Some reflection operations also trigger initialization.

Example:

~~~java
final class Demo {
    static final String CONSTANT = "ready"; // compile-time constant
    static int counter = initCounter();

    private static int initCounter() {
        System.out.println("Demo initialized");
        return 1;
    }

    static void run() {
    }
}
~~~

The snippet above is an illustrative helper class that can be used from another main class. Referencing **Demo.CONSTANT** from normally compiled code **does not force the JVM to initialize Demo**, because this field is a compile-time constant. In contrast, calling **Demo.run()** or reading **Demo.counter** triggers initialization if it has not happened yet.

Operations such as **Demo.class** or **Class.forName("Demo", false, loader)** do not necessarily trigger initialization. **Class.forName("Demo")** requests initialization by default. Therefore, the statement "the library is loaded when the .class file is read into memory" is **incorrect**; the load call in a static initializer runs when the class **is initialized**.

### Ordering and synchronization

- Static field initializers and static blocks run in the specified textual order; any required superclass is initialized before its subclass.
- The JVM coordinates concurrent threads requesting initialization of **the same class**, so two threads do not arbitrarily run a successful static initializer of the same class twice.
- The runtime identity of a class consists of **the class name and the defining class loader**. For a class that has already been initialized successfully, its static block does not run again within that same runtime identity.

These properties make static initializers suitable for small, deterministic initialization logic, but they also make initialization failures particularly severe.

## 3. System.loadLibrary and System.load

Both APIs are used to load native code into the JVM process, but they take different arguments:

| API | Input | Example | Notes |
| --- | --- | --- | --- |
| **System.loadLibrary(String libname)** | Logical library name, without path, platform prefix, or extension | **System.loadLibrary("codec")** | The JVM/loader maps the name and searches using the native library search mechanism |
| **System.load(String filename)** | Absolute path to the native library | **System.load(absolutePath)** | Suitable when the application manages the exact artifact/path; dependencies must still be handled |

On common platforms, **System.mapLibraryName("codec")** can produce names like **codec.dll**, **libcodec.so**, or **libcodec.dylib**. The actual result depends on the JVM and platform; do not hardcode a single filename for all operating systems.

**Example configuration when running the JVM:**

~~~bash
java -Djava.library.path=/opt/app/native MyApplication
~~~

This is how to configure the search path at startup in an appropriate environment; on Windows, use Windows paths. Modifying the **java.library.path** property after the JVM has started **is not considered a reliable way** to force the loader to re-search for libraries. In addition, the OS loader also needs to find **the dependencies of the native library itself**, which are not necessarily resolved by java.library.path alone.

**Do not pass a path to loadLibrary:** **System.loadLibrary("/opt/app/native/libcodec.so")** misuses the contract. If you already have a verified absolute path, use **System.load**.

## 4. Where does UnsatisfiedLinkError arise?

**UnsatisfiedLinkError** is a subclass of **LinkageError**, and **LinkageError** is a subclass of **Error**. It indicates that the JVM cannot satisfy a linking/native linkage requirement in the corresponding situation.

There are several groups of causes:

| Timing | Typical cause | Verification hint |
| --- | --- | --- |
| **When calling loadLibrary** | File not found, wrong logical name, wrong search path | Name passed to API, java.library.path value, binary location |
| **When the loader opens the binary** | Wrong OS/CPU/ABI, corrupted native file, or missing dependency | JVM and binary architecture, dependent library list, libc/runtime |
| **When the class loader manages the library** | The same JNI library is loaded into two incompatible class loaders under JNI rules | Class loader structure and where the JNI adapter is declared |
| **When the native method is linked/used** | No JNI implementation/symbol found matching the Java signature | Java native declaration, exported symbol, signature, build output |
| **During native initialization** | The library or JNI initialization function returns an error / fails to complete its contract | Native loader logs, JNI_OnLoad, dependencies, and crash reports |

**Successfully loading the file does not guarantee every native method can be called.** For example, **System.loadLibrary("codec")** may succeed, yet when calling **nativeDecode(...)** the JVM still throws **UnsatisfiedLinkError** because the implementation is missing or mismatched. Thus, **"load success" ≠ "native feature readiness"**: a controlled smoke test or real integration test is still necessary.

Conversely, not every failure is an UnsatisfiedLinkError. A null argument can cause **NullPointerException**; access control policies can produce **SecurityException** or **IllegalCallerException** depending on the JDK version/configuration; severely buggy native code can crash the entire process in ways Java cannot catch to recover.

## 5. What happens when loadLibrary fails directly in a static initializer?

Consider the minimal example:

~~~java
final class RequiredNative {
    static {
        System.loadLibrary("required_native");
    }

    static void use() {
        System.out.println("Ready");
    }
}
~~~

Suppose the **required_native** library does not exist or cannot be loaded successfully:

1. The first call to **RequiredNative.use()** requires the JVM to initialize RequiredNative.
2. The JVM runs the static block, and **System.loadLibrary** throws **UnsatisfiedLinkError**.
3. The error is not caught inside the static initializer, so initialization **completes abruptly**.
4. The JVM marks RequiredNative as **erroneous** in the current class loader.
5. The first call may propagate the original **UnsatisfiedLinkError**.
6. Subsequent active uses of **the same failed class** will not re-run the static initializer; the JVM throws **NoClassDefFoundError** for being unable to initialize that class.

Point 6 is a common source of misunderstanding. **NoClassDefFoundError does not always mean a missing .class file**. It can also be the consequence of **a previously failed class initialization**. You must find **the first root error**, which is usually earlier in the logs or in the cause chain.

### Distinguishing the three error types

| Observed error | Meaning in this case |
| --- | --- |
| **UnsatisfiedLinkError** | The JVM could not load/link the library or native method; may be the root error occurring in the static initializer |
| **ExceptionInInitializerError** | The JVM wraps a **non-Error** throwable escaping a static initializer, such as a RuntimeException; check **getCause()** |
| **NoClassDefFoundError** | On a subsequent use, the JVM detects that the class is in an erroneous state due to a prior initialization failure |

According to JLS §12.4.2, if the throwable from an initializer is already an **Error** or a subclass of Error, the JVM **does not wrap it in ExceptionInInitializerError**. Because **UnsatisfiedLinkError extends Error**, this error usually escapes directly on the first initialization attempt. An unhandled **IllegalCallerException** in a static initializer, on the other hand, can be wrapped in **ExceptionInInitializerError**. Do not assume all static errors share the same exception type.

### Why can't you "retry" by calling the class again?

Because the class has already been marked erroneous. Even if the native library is later copied into the right directory, **the failed class will not re-initialize itself in the same class loader**. In a typical application, the reliable way to recover is to fix the configuration/binary and **restart the process**. A mechanism that reloads via a new class loader should only be used when the system is properly designed for reloading and JNI library ownership rules.

## 6. Standalone runnable Java 17+ example: comparing fail-fast and fallback

This example **does not require a real C/JNI library** to inspect JVM behavior. The **demo.simulateMissing=true** property causes the helper method to throw the exact **UnsatisfiedLinkError** that a library load call can produce. When simulation is disabled, the helper calls the real **System.loadLibrary**.

Create **NativeInitLesson.java**:

~~~java
public final class NativeInitLesson {
    private NativeInitLesson() {
    }

    private static void attemptLoad() {
        if (Boolean.getBoolean("demo.simulateMissing")) {
            throw new UnsatisfiedLinkError("Simulated missing native library");
        }
        System.loadLibrary("lesson_native_42");
    }

    // Required library: loading error escapes from the static initializer.
    private static final class Required {
        static {
            attemptLoad();
        }

        static String state() {
            return "native loaded";
        }
    }

    // Optional library: catch only the expected loading error.
    private static final class Optional {
        static final boolean LOADED;
        static final String LOAD_STATUS;

        static {
            boolean loaded;
            String status;
            try {
                attemptLoad();
                loaded = true;
                status = "loaded";
            } catch (UnsatisfiedLinkError error) {
                loaded = false;
                status = error.getClass().getSimpleName();
            }
            LOADED = loaded;
            LOAD_STATUS = status;
        }

        static String mode() {
            return LOADED ? "native candidate" : "java fallback";
        }
    }

    public static void main(String[] args) {
        for (int i = 1; i <= 2; i++) {
            try {
                System.out.println("Required #" + i + ": " + Required.state());
            } catch (UnsatisfiedLinkError | NoClassDefFoundError error) {
                System.out.println(
                    "Required #" + i + ": "
                    + error.getClass().getSimpleName()
                );
            }
        }

        System.out.println("Optional: " + Optional.mode());
        System.out.println("Optional load status: " + Optional.LOAD_STATUS);
    }
}
~~~

Run with **JDK 17 or later**:

~~~bash
javac NativeInitLesson.java
java -Ddemo.simulateMissing=true NativeInitLesson
~~~

**Exact stdout in simulation mode:**

~~~text
Required #1: UnsatisfiedLinkError
Required #2: NoClassDefFoundError
Optional: java fallback
Optional load status: UnsatisfiedLinkError
~~~

### Result analysis

- **Required #1**: the statement calling the static method of class Required triggers initialization; UnsatisfiedLinkError escapes, leaving Required in the erroneous state.
- **Required #2**: the JVM does not re-run the static initializer. It returns NoClassDefFoundError for using the Required class whose initialization failed.
- **Optional**: the static block **specifically catches UnsatisfiedLinkError**, populates the two static fields, and completes normally. Therefore, the Optional class **initialized successfully** and can return the fallback state.
- **Optional.LOAD_STATUS** indicates the error classification, without hardcoding a platform-dependent stack trace or message string.

The line **Optional: java fallback** only describes **the routing decision**. The example does not implement a specific native algorithm; in a real system, only use a fallback when the alternative Java algorithm has **verified equivalent semantics**, including error codes, precision, encoding, side effects, and security requirements.

**Why use simulation?** It produces the same output on Windows, Linux, and macOS, even when the machine already has various libraries installed. Running without the **demo.simulateMissing** property will try to find the real **lesson_native_42** library; the result then depends on the environment and the JDK's native access state.

**Important:** The **catch (UnsatisfiedLinkError | NoClassDefFoundError)** branches in **main** are only for observing the difference in errors. When writing real applications, do not broadly catch NoClassDefFoundError to mask Java deployment errors or classpath issues.

## 7. Choosing a strategy: required or optional library?

You should not use a single error-catching strategy for every native module. Define product expectations clearly before writing a static initializer.

### 7.1. Required library: informative fail-fast

If a core feature depends entirely on native code, do not pretend the application is ready when the library fails to load.

~~~java
final class MandatoryEngine {
    static {
        System.loadLibrary("mandatory_engine");
    }

    static void checkAvailable() {
        // Call during bootstrap to force early class initialization.
    }
}
~~~

This is an **illustrative snippet** that requires a real **mandatory_engine** binary. If the library is absent, the error from the static initializer prevents the class from being used in an invalid state.

However, a static initializer only runs on the **first active use**, which might happen late during a production request. For a required library, you should **invoke a health check or intentional initialization operation at startup**, before reporting the service as READY. On failure, log sufficient diagnostic details and halt startup, rather than letting the first request discover the error.

If a clear business/operational message is needed, handle and enrich the information **at the bootstrap boundary**, while preserving the original error in the logs/cause. Avoid turning every error into a generic "JNI failed" message that loses the root cause.

### 7.2. Optional library: catch in the initializer and record status

If native code only accelerates a capability that already has an equivalent Java implementation, you can catch **UnsatisfiedLinkError** right inside initialization. When the catch succeeds and the static initializer completes normally, the class is not marked erroneous.

To make this pattern safe:

1. Catch only the expected error within **the scope of the load call**; do not place too much unrelated initialization logic inside the same try block.
2. Store the **available / unavailable** status and reason for telemetry; do not repeat the load call indefinitely as each request arrives.
3. Ensure external APIs **do not call native methods** when on the unavailable branch.
4. If loading succeeds but native methods need to be called, **verify symbols and behavior separately**. A LOADED flag only proves the library-loading step, not that the entire feature is ready.
5. Fall back only when the Java/native contract is equivalent; if the feature is required or lacks equivalence, return a clear error status.

A library loading failure due to production misconfiguration may still need to report **UNHEALTHY** even when a Java fallback exists, depending on SLO and correctness requirements. Avoid swallowing the error and silently running slower or changing results without observability.

### 7.3. Deferring loading with a Holder class

When only a secondary feature needs native code, keep the rest of the application independent of the library-loading class. You can place the loading mechanism inside a **nested static holder**, and access the holder **only when** the feature is enabled.

Benefit: avoids an early-initialized class from introducing native requirements into every bootstrap path. However, **lazy loading does not solve retryability**: if the holder's own static initializer fails, the holder also becomes erroneous. Combine the holder with status reporting and error-catching classification according to your chosen strategy.

### 7.4. Why shouldn't you catch Error or Throwable unconditionally?

**Error** also includes critical conditions such as **OutOfMemoryError** and other linkage errors. Catching broadly and pretending to continue often masks process corruption. You should catch **only the specific error the adapter can handle**; in the scope of loading an optional library, that may be UnsatisfiedLinkError. Another error such as **IllegalCallerException** caused by native access policy must be evaluated separately, not assumed equivalent to "library missing".

## 8. Diagnosing native loading failures in order

When encountering a failure at startup or during feature use, identify **when the error first occurred**, record the cause chain, and pinpoint the failing step.

### Step 1 — Verify the API, name, and timing

- Is **System.loadLibrary** or **System.load** being called?
- If using loadLibrary, is the name a **logical name without path/extension**?
- If using load, is the path **absolute**, does the file actually exist, and does the process have access permissions?
- Did the error happen immediately in the static initializer, or after loading succeeded when **calling a native method**?
- Was the first log an UnsatisfiedLinkError, while the current logs only show NoClassDefFoundError? Look for the root cause **before the class became erroneous**.

### Step 2 — Check the JVM and binary platform

Record the OS, **os.arch**, Java version, Java vendor/runtime, CPU, and the selected native artifact. A 64-bit JVM does not directly load an incompatible 32-bit binary; a Windows binary cannot be loaded as a Linux shared object.

Note that **os.arch** is a helpful diagnostic property, not a substitute for checking the actual binary/ABI format. On Linux, glibc/musl differences or dependency versions also matter.

### Step 3 — Check secondary dependencies

The referenced library may exist, yet it may itself require another library that is absent from the runtime. Depending on the platform, use appropriate OS tools:

| Operating System | Common checks |
| --- | --- |
| Linux | **file**, **readelf**, **ldd** in a trusted environment |
| macOS | **file**, **otool -L** |
| Windows | Corresponding DLL/dependency inspection tools and PE architecture checks |

Do not run **ldd** on untrusted binaries; use appropriate static inspection tools instead. Perform checks on **the exact container/server image** experiencing the error, not only on the developer's machine.

### Step 4 — Check symbols and the JNI contract

If loading the library succeeds but the native call still fails to link, check:

- Is the native method declared with the exact name, parameter types, return type, and static/instance modifier expected by JNI?
- Is the corresponding symbol exported? Is there any mismatch in name mangling, overloads, package, or class name?
- Was the JNI header generated from the right version of the Java source? Is an older version of the class being deployed?
- Does it require registering native methods via **RegisterNatives**, and did the registration path fail to run or have a mismatched signature?

A "method not found" message must be distinguished from "file not found"; changing java.library.path cannot fix a missing JNI symbol.

### Step 5 — Check class loaders

In application servers, plugin systems, or hot reload setups, the same JNI library may be attempted to be loaded by two separate class loaders. The JNI specification states that each class loader manages its own set of native libraries; **the same JNI native library cannot be loaded into two independent class loaders**, and attempting to do so causes UnsatisfiedLinkError.

The solution is to design where adapters/libraries live and keep class loader lifecycles consistent. Do not create copies of the same binary at different paths as a way to "bypass" this restriction without understanding the risks of the library's global state.

### Step 6 — Check JDK native access

Starting in **JDK 24**, JNI loading/linking operations are governed by restricted native access. Depending on the JDK configuration, unauthorized operations may emit warnings or throw **IllegalCallerException**. Depending on the environment:

~~~bash
java --enable-native-access=ALL-UNNAMED MyApplication
~~~

Use **ALL-UNNAMED** when the adapter is on the classpath; if the application is modularized, prefer granting access to **the specific module**. On JDKs supporting **--illegal-native-access=deny**, you can use it in test environments to detect where permissions have not been declared. Do not blindly enable permissions to "fix every UnsatisfiedLinkError": missing binaries or wrong ABIs still need to be fixed separately.

### Step 7 — Distinguish catchable Java errors from native crashes

Native code can corrupt memory or crash the process, beyond the reach of Java try/catch. If there is a JVM crash or off-heap error, collect crash logs, native stacks, and matching symbol files, and diagnose using native profilers/sanitizers. Catching UnsatisfiedLinkError only handles a class of load/link errors; **it does not create a memory-safety barrier** for C/C++ libraries.

## 9. Real-world scenarios and handling decisions

### Scenario A — Production is missing a required library

The service can only perform its core function when **libcriticalcodec** is present. JVM startup succeeds, but the first request calling the JNI class throws UnsatisfiedLinkError, and subsequent requests see NoClassDefFoundError.

**Approach:** force an adapter check at bootstrap; verify the file and dependencies inside the image; fail startup with the original error details if the check fails. Do not retry by calling the same erroneous class again.

### Scenario B — Native accelerator only available on Linux

A pure Java computation works correctly on Windows. Linux has a native version for acceleration.

**Approach:** place the native adapter behind conditional access, catch the expected loading error in the initializer, record the status, and use the tested equivalent Java path. Control with feature flags and metrics to know how many requests use each branch. If loading succeeds, run a smoke test to confirm the native symbols actually work.

### Scenario C — Hot reload creates a new class loader

After redeploying a plugin, a new class loader attempts to call System.loadLibrary for a JNI library already owned by the old loader.

**Approach:** review class loader boundaries and native library lifecycles; it may be necessary to place the adapter in a shared class loader or require a service restart instead of hot reload. Do not assume changing the file path solves JNI ownership issues.

### Scenario D — CI passes, production container fails

CI runs on x86-64 glibc, while the production image uses a different libc variant or ARM64. The library file appears at the right path, but the loader reports it cannot be loaded.

**Approach:** build and smoke test per **OS × architecture × ABI/libc**; check secondary dependencies on the actual image, not just the file path. Keep artifact versions/checksums so you know which native build ships with which JAR.

## 10. Meaningful testing approaches

A test that only calls **System.mapLibraryName** does not verify that the library loads successfully. For systems with real JNI, you should have the following test layers:

1. **Java unit test:** simulate the loader throwing UnsatisfiedLinkError to verify state transitions; the runnable example in section 6 tests the first/second use behavior of a static initializer.
2. **Required-library bootstrap test:** configure a missing library, assert the service does not report READY, and verify logs preserve the root cause.
3. **Optional-fallback test:** when the library is missing, the optional class still initializes normally and the API returns results matching the Java contract; no NoClassDefFoundError occurs on subsequent calls.
4. **Real native smoke test:** with a platform-matching binary, call a small native method and verify symbols, results, and ownership rules.
5. **Packaging test:** run on every supported image/CPU/ABI, including secondary dependencies; not just on a developer's machine.
6. **Concurrency test:** have multiple threads trigger the first active use simultaneously; ensure there is no false success state or hard-to-diagnose error.
7. **Upgrade test:** swap native and Java adapter versions, verify ABI, native access flags, and rollback/restart capability.

An error from a static initializer can affect the entire lifecycle of the class; when running different tests in **the same JVM and the same class loader**, do not expect that "re-staging the DLL/SO file" will cause an erroneous class to re-initialize. Isolate tests using separate processes or appropriate class loaders for each scenario.

## 11. Common design mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling **System.loadLibrary("libfoo.so")** | Confuses logical name with platform filename | Pass **"foo"** if the file/loader follows that mapping |
| Placing load in static and assuming startup always detects failures | The class may only be initialized on the first request | Call an intentional bootstrap check for required libraries |
| Catching UnsatisfiedLinkError **only at the caller** and retrying the same class | Subsequent calls hit **NoClassDefFoundError** because the class is erroneous | Handle inside the initializer for optional libraries or restart for required libraries |
| Catching **Throwable** and ignoring it | Hides critical errors and lacks controlled state | Catch specific errors and classify fail-fast/fallback |
| Marking READY solely because **loadLibrary** succeeded | JNI symbols or native methods can still be wrong | Add a native integration smoke test |
| "Fixing" by changing **java.library.path** at runtime | The loader does not necessarily update its search state | Configure properly before startup; use an absolute path when truly needed |
| Checking only that the main file exists | libc/C++ runtime or other dependencies may be missing | Inspect the dependency chain and ABI |
| Renaming the same JNI library file and loading via multiple loaders | JNI lifecycle conflicts, dangerous global state | Design proper class-loader ownership |
| Treating every native error as UnsatisfiedLinkError | Could be SecurityException, IllegalCallerException, crash, or business error | Diagnose based on error type and execution phase |

## 12. Implementer's checklist

- [ ] Determined whether the native library is **required** or **optional**.
- [ ] Chosen the active use timing and understood when the **static initializer** runs.
- [ ] Distinguished **System.loadLibrary** (logical name) from **System.load** (absolute path).
- [ ] Verified the binary and all dependencies on every supported OS/CPU/ABI/container.
- [ ] Designed **UnsatisfiedLinkError** handling in the right place; without accidentally leaving an optional class erroneous.
- [ ] Understood the first-time error and subsequent **NoClassDefFoundError**; logs preserve the root error.
- [ ] Separated **load success** from **native method/link success** using a smoke test.
- [ ] Checked native access permissions when using JDKs with restricted native access.
- [ ] Clearly decided between failing startup or a fallback with equivalent semantics.
- [ ] Tested failures in a production-like environment and planned restart/rollback procedures.
- [ ] Recorded Java version, native artifact, and error context for operations.

## 13. Knowledge check

**Question 1.** A class has a static block calling System.loadLibrary. When only **SomeNativeClass.class** is referenced, has the load call necessarily run yet?

**Answer:** No. Referencing a class literal does not force initialization on its own. Because the load call is inside the static initializer, it runs when initialization actually occurs.

**Question 2.** The first call to a class fails with UnsatisfiedLinkError; the next call receives NoClassDefFoundError. Was the class file deleted between the two requests?

**Answer:** You cannot conclude that. A very likely possibility is that the class was marked erroneous because the first initialization failed; the JVM does not attempt to re-run that class's static block.

**Question 3.** Why doesn't an UnsatisfiedLinkError in a static initializer usually become an ExceptionInInitializerError?

**Answer:** It is an **Error**. The JLS only wraps non-Error throwables into ExceptionInInitializerError during initializer failure handling.

**Question 4.** Does catching UnsatisfiedLinkError in a static initializer guarantee that the native feature is usable?

**Answer:** No. It only allows an optional class to complete initialization when a fallback has been chosen. If loading succeeds, symbol linking/native calls still need verification; if falling back, business/semantic equivalence must be ensured.

**Question 5.** Can you fix the native file and then call the erroneous class again to retry loading?

**Answer:** Not within the same class loader identity that failed. You must fix the environment and use a fresh loading lifecycle, typically a restart; reloading via a new class loader must comply with JNI rules.

## Official documentation

- [Java Language Specification §12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se26/html/jls-12.html#jls-12.4).
- [Java SE 21 System.loadLibrary and System.load](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#loadLibrary(java.lang.String)).
- [Java Native Interface — Library and Version Management](https://docs.oracle.com/en/java/javase/26/docs/specs/jni/invocation.html).
- [JEP 472 — Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472).

**Key takeaway:** Placing **System.loadLibrary** in a static initializer is a common and sensible pattern when a class requires JNI, but **unhandled errors cause initialization to fail**. For required libraries, fail-fast at startup and preserve the root error. For optional libraries, handle UnsatisfiedLinkError inside the initializer, complete the class state, and fall back only when equivalence is guaranteed. Always distinguish **the first-time load error** from **NoClassDefFoundError when reusing an erroneous class**.
