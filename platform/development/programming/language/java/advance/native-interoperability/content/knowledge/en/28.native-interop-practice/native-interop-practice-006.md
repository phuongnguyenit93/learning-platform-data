# Embedding the JVM in a C Application and Calling a Java Service

**Topic:** Java Advance – Native Interoperability  
**Lesson Group:** Practice Exercise  
**Practice Environment:** JDK 17+, C11 compiler, Linux x86-64. The Java code uses Java 17 syntax; other operating systems need adjustments to the JVM library path and linker command.

## 1. Expected Outcomes

You have a standalone C program that needs to use business logic already written in Java. Instead of running an external Java program and communicating over stdin/HTTP, the C program can **load the JVM into its own process** using the **JNI Invocation API**, find the Java class, create a service object, call methods, receive results, and explicitly terminate the JVM lifecycle.

After this lesson you will:

1. Use **JNI_CreateJavaVM** to initialize the JVM from a C application and configure the classpath.
2. Understand the roles of **JavaVM*** (representing the JVM) and **JNIEnv*** (the JNI interface bound to the *current thread*).
3. Find a Java class, obtain constructor/method IDs, create a service using **NewObject**, and call an instance method using **CallObjectMethod**.
4. Pass **String** and **int** from C to Java, receive a returned **String**, and release JNI references/borrowed strings.
5. Detect and handle Java exceptions, call the service's **close()**, and then safely **DestroyJavaVM**.
6. Distinguish a single-threaded example from a multi-threaded C application, and understand attach/detach rules and practical limitations of an embedded JVM.

### How Does Embedding the JVM Work?

~~~text
┌───────────────────────────── C Process ────────────────────────────────┐
│ main()                                                                 │
│    │ JNI_CreateJavaVM, -Djava.class.path=classes                       │
│    ▼                                                                   │
│ JVM (libjvm.so) ── JNIEnv* of the calling thread itself                │
│    │                                                                   │
│    ├── FindClass("demo/PriceService")                                  │
│    ├── GetMethodID("<init>", "(J)V") + NewObject(...)                  │
│    ├── GetMethodID("quote", "(Ljava/lang/String;I)Ljava/lang/String;") │
│    ├── NewStringUTF("BOOK") → CallObjectMethod(...)                    │
│    ├── GetStringUTFChars(result) → print result → Release...           │
│    ├── CallVoidMethod(service.close) + DeleteLocalRef                  │
│    └── DestroyJavaVM                                                   │
└────────────────────────────────────────────────────────────────────────┘
~~~

**Embedding the JVM (C → Java)** is the reverse direction of the common JNI example **Java → C native function**. The JNI Invocation API provides the JVM and thread context; the regular JNI function set is still used to create/read objects and call methods. **Java does not need a main() method**: C is the entry point of the application.

This approach makes sense when the host application is C/C++, wants to leverage an existing Java library, and can tolerate the cost of the JVM residing in the same process. If you want to isolate native crashes, or deploy or scale Java independently, IPC/HTTP/gRPC is an alternative design direction; choosing an architecture depends on system requirements, not just the latency of a single call.

## 2. Designing the Java Service and Data Contract

The practice exercise uses **PriceService** to quote two SKUs, without needing a framework or web server:

- **BOOK**: 1,250 cents/item.
- **PEN**: 175 cents/item.
- Each call has a **service fee** of 250 cents, configured in the constructor.
- **quote(String sku, int quantity)** returns a receipt string: product, quantity, total amount.
- **close()** transitions the service to a closed state. Calling quote after close will throw **IllegalStateException**.

Money is represented as **integer cents (long)** so the example does not introduce floating-point representation errors of double. Multiplication/addition uses **Math.multiplyExact/Math.addExact**, throwing an error on overflow. The service synchronizes **quote()** and **close()** so that an operation checking state and calculating price does not race with the close operation. This is a simple business service sample; there is no database, I/O, or pool yet.

| Boundary | Java Input | C JNI Type | Notes |
| --- | --- | --- | --- |
| Constructor PriceService(long) | long feeCents | **jlong** | Signature **(J)V** |
| quote(String,int) | String sku, int quantity | **jstring**, **jint** | Signature **(Ljava/lang/String;I)Ljava/lang/String;** |
| Return value from quote | String | **jstring** | C must obtain and release the characters provided by JNI |
| close() | No arguments, void | CallVoidMethod | Signature **()V** |
| Java exception | Throwable | Pending state of JNIEnv | Must check after JNI operations that can throw |

**Remember:** Java package names use dots, for example **demo.PriceService**; the name used with **FindClass** changes to **demo/PriceService**. In JVM signatures: **I=int**, **J=long**, **V=void**, **Lpackage/Class;=reference**, and parentheses enclose the parameter types. If C calls with the wrong name/signature, it will not find the method, even if the Java source clearly has a method with a similar name.

## 3. Practice File Structure

Create the project with the exact names and locations:

~~~text
embed-jvm/
├── src/
│   └── demo/
│       └── PriceService.java
├── embed.c
└── classes/                     (javac generates .class files here)
~~~

Stand in the **embed-jvm/** directory when compiling and running. The **classes/** directory is the runtime classpath used in the C code. The C executable can be run from a different path, but if the working directory changes, the relative classpath **classes** also changes; in real deployments, pass a **reliable absolute path** for the classpath.

### File src/demo/PriceService.java

~~~java
package demo;

public final class PriceService implements AutoCloseable {
    private final long feeCents;
    private boolean closed;

    public PriceService(long feeCents) {
        if (feeCents < 0) {
            throw new IllegalArgumentException("feeCents must be nonnegative");
        }
        this.feeCents = feeCents;
    }

    public synchronized String quote(String sku, int quantity) {
        if (closed) {
            throw new IllegalStateException("service already closed");
        }
        if (sku == null || quantity <= 0) {
            throw new IllegalArgumentException("invalid sku or quantity");
        }
        long unitCents = switch (sku) {
            case "BOOK" -> 1250L;
            case "PEN" -> 175L;
            default -> throw new IllegalArgumentException("unknown sku: " + sku);
        };
        long total = Math.addExact(
                Math.multiplyExact(unitCents, quantity), feeCents);
        return sku + " x" + quantity + " => " + total + " cents";
    }

    @Override
    public synchronized void close() {
        closed = true;
    }
}
~~~

**Reading the code:** The constructor receives a fixed fee per quote request. Each quote call looks up the unit price, validates quantity, computes the price, and formats the string; for **BOOK x3**, the total is **1,250 × 3 + 250 = 4,000 cents**. Because the service is created and held by C, C must decide when to call close. In this example close only marks state; in a real service, close can also close connections and release resources owned by the service.

The Java service does not have main(), because main() is in C. It does not use Spring; in a system using Spring, the C program needs to call a Java facade responsible for starting and closing the **ApplicationContext** before/after business operations.

## 4. Complete C Program Using the JNI Invocation API

The C code below uses JNI in strict C syntax (calling through the function pointer table **(*env)->...** and **(*jvm)->...**). C++ has a different corresponding call syntax (**env->...**, **jvm->...**), so do not rename the .c file to .cpp while keeping the C-style API assumptions.

### File embed.c

~~~c
#include <jni.h>
#include <stdio.h>
#include <stdlib.h>

static int report_java_error(JNIEnv *env, const char *operation) {
    if (!(*env)->ExceptionCheck(env)) {
        return 0;
    }
    fprintf(stderr, "Java exception at %s:\n", operation);
    (*env)->ExceptionDescribe(env);
    (*env)->ExceptionClear(env);
    return 1;
}

static int print_quote(JNIEnv *env, jobject service,
                       jmethodID quote, const char *sku, jint quantity) {
    jstring javaSku = NULL;
    jstring result = NULL;
    const char *utf8 = NULL;
    int success = 0;

    javaSku = (*env)->NewStringUTF(env, sku);
    if (report_java_error(env, "NewStringUTF") || javaSku == NULL) {
        goto cleanup;
    }

    result = (jstring)(*env)->CallObjectMethod(
            env, service, quote, javaSku, quantity);
    if (report_java_error(env, "PriceService.quote") || result == NULL) {
        goto cleanup;
    }

    utf8 = (*env)->GetStringUTFChars(env, result, NULL);
    if (report_java_error(env, "GetStringUTFChars") || utf8 == NULL) {
        goto cleanup;
    }
    puts(utf8);
    success = 1;

cleanup:
    if (utf8 != NULL) {
        (*env)->ReleaseStringUTFChars(env, result, utf8);
    }
    if (result != NULL) {
        (*env)->DeleteLocalRef(env, result);
    }
    if (javaSku != NULL) {
        (*env)->DeleteLocalRef(env, javaSku);
    }
    return success ? 0 : 1;
}

int main(void) {
    JavaVM *jvm = NULL;
    JNIEnv *env = NULL;
    char classpath[] = "-Djava.class.path=classes";
    JavaVMOption options[] = {{classpath, NULL}};
    JavaVMInitArgs args = {0};
    args.version = JNI_VERSION_1_8;
    args.nOptions = 1;
    args.options = options;
    args.ignoreUnrecognized = JNI_FALSE;

    jint rc = JNI_CreateJavaVM(&jvm, (void **)&env, &args);
    if (rc != JNI_OK || jvm == NULL || env == NULL) {
        fprintf(stderr, "Cannot start JVM: code %d\n", (int)rc);
        return EXIT_FAILURE;
    }

    int status = EXIT_FAILURE;
    jclass serviceClass = NULL;
    jobject service = NULL;
    jmethodID closeMethod = NULL;

    serviceClass = (*env)->FindClass(env, "demo/PriceService");
    if (report_java_error(env, "FindClass") || serviceClass == NULL) {
        goto cleanup;
    }

    jmethodID constructor = (*env)->GetMethodID(
            env, serviceClass, "<init>", "(J)V");
    if (report_java_error(env, "GetMethodID(<init>)") || constructor == NULL) {
        goto cleanup;
    }

    jmethodID quoteMethod = (*env)->GetMethodID(
            env, serviceClass, "quote",
            "(Ljava/lang/String;I)Ljava/lang/String;");
    if (report_java_error(env, "GetMethodID(quote)") || quoteMethod == NULL) {
        goto cleanup;
    }

    closeMethod = (*env)->GetMethodID(env, serviceClass, "close", "()V");
    if (report_java_error(env, "GetMethodID(close)") || closeMethod == NULL) {
        goto cleanup;
    }

    service = (*env)->NewObject(env, serviceClass, constructor, (jlong)250);
    if (report_java_error(env, "NewObject") || service == NULL) {
        goto cleanup;
    }

    if (print_quote(env, service, quoteMethod, "BOOK", 3) != 0 ||
        print_quote(env, service, quoteMethod, "PEN", 2) != 0) {
        goto cleanup;
    }
    status = EXIT_SUCCESS;

cleanup:
    if (service != NULL && closeMethod != NULL) {
        (*env)->CallVoidMethod(env, service, closeMethod);
        if (report_java_error(env, "PriceService.close")) {
            status = EXIT_FAILURE;
        }
    }
    if (service != NULL) {
        (*env)->DeleteLocalRef(env, service);
    }
    if (serviceClass != NULL) {
        (*env)->DeleteLocalRef(env, serviceClass);
    }
    if ((*jvm)->DestroyJavaVM(jvm) != JNI_OK) {
        fprintf(stderr, "JVM shutdown failed\n");
        status = EXIT_FAILURE;
    }
    if (status == EXIT_SUCCESS) {
        puts("JVM stopped");
    }
    return status;
}
~~~

### Why Is C Split into Two Helper Functions?

**report_java_error** is the single place that records Java exceptions after JNI operations that can fail. **ExceptionCheck** indicates whether a pending exception exists; **ExceptionDescribe** prints the stack trace to the error stream, and **ExceptionClear** ensures the cleanup path continues in an exception-free state. ExceptionDescribe inherently also clears the pending exception according to the specification, so ExceptionClear afterward is a readable defensive step. In production, you should return an exception/error code according to the application's contract; printing the stack trace directly is a learning/debugging tool.

**print_quote** holds the JNI local references **javaSku** and **result**, as well as the character pointer **utf8** which lives only until **ReleaseStringUTFChars**. Every exit path goes through the **cleanup** branch, so an error midway does not leak resources. The two C calls use **the exact same service object** that was created, demonstrating object/method ID reuse.

**main** is the owner of the JVM. After JNI_CreateJavaVM returns **JNI_OK**, main uses the **JNIEnv*** belonging to the thread that just created the JVM, finds the service, constructs the object, and calls quote. Before DestroyJavaVM, main calls Java close, deletes local refs, and then checks the return code of DestroyJavaVM. **Do not call any JNI function through env after DestroyJavaVM has succeeded**.

Do not keep local references across a long session or pass local references to another thread. In particular, **JNIEnv*** is not a pointer that can be used from any thread: it is an interface bound to the **current thread**.

## 5. Compiling and Running

### Requirements

- Linux x86-64 with **JDK 17 or newer** and a C compiler supporting C11 (for example GCC).
- **JAVA_HOME** pointing to the JDK root directory, containing **include/jni.h**, **include/linux/jni_md.h**, **lib/server/libjvm.so**.
- Terminal positioned in the **embed-jvm/** directory. The C code uses classpath **classes**, meaning **./classes** relative to the C process's working directory.
- No Gradle, Maven, web server, JAR, or separate Java process is needed to run the example.

### Commands

~~~bash
# Stand in the embed-jvm/ directory and ensure JAVA_HOME is set.
mkdir -p classes
javac -d classes src/demo/PriceService.java

gcc -std=c11 -Wall -Wextra -Werror -O2 \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  embed.c -L"$JAVA_HOME/lib/server" \
  -Wl,-rpath,"$JAVA_HOME/lib/server" \
  -ljvm -o embed

./embed
~~~

**Expected stdout on successful run:**

~~~text
BOOK x3 => 4000 cents
PEN x2 => 600 cents
JVM stopped
~~~

Calculation explanation: BOOK = 1,250 × 3 + 250 = 4,000; PEN = 175 × 2 + 250 = 600 cents. The three lines above have a deterministic order because the two Java calls run sequentially from a single native thread. In case of an error, stderr will be printed and a non-zero exit code returned; the specific trace depends on the error.

The **javac** command generates **classes/demo/PriceService.class**. **gcc** uses **jni.h** and the Linux ABI header to compile, linking **libjvm.so** via **-L... -ljvm**. The **-Wl,-rpath,...** option embeds the search path for libjvm when the loader runs the executable, helping avoid missing libjvm.so errors on the lab machine. For a real release, the choice of rpath, runtime path, and JVM packaging must follow deployment policy; do not hardcode the JDK path of a development machine.

The usual **java** command does not appear in the run step because **./embed** itself loads the JVM and invokes the Java class via JNI. You still use **java -version** and **javac -version** to identify the JDK toolchain; **JNI_CreateJavaVM** replaces the JVM startup role of the Java launcher in this example.

**Practical verification:** The code above is compatible with Java 17 and C11 syntax. You can compile Java with **javac --release 17** if the machine uses a newer JDK and you want to verify the JDK 17 API/language level. Java bytecode still requires a JVM that supports the corresponding class version.

### OS Differences

| Operating System | OS-Dependent Header | JVM Library and Notes |
| --- | --- | --- |
| Linux | **$JAVA_HOME/include/linux** | **libjvm.so**, loader path via rpath or environment configuration. |
| macOS | **$JAVA_HOME/include/darwin** | **libjvm.dylib**, linker/loader path according to how the JDK is packaged on macOS. |
| Windows | **%JAVA_HOME%\\include\\win32** | **jvm.dll**, the linker usually needs the corresponding import library (e.g. jvm.lib) and an appropriate DLL path. |

Do not use the Linux gcc command verbatim on Windows and expect it to find jvm.dll properly. In addition, the native executable and JVM must match in **architecture/ABI (for example both x86-64 or both ARM64)**.

## 6. Deep Dive into Each JNI Call Step

### 6.1. Creating the JVM and Configuration

~~~c
JavaVM *jvm = NULL;
JNIEnv *env = NULL;
char classpath[] = "-Djava.class.path=classes";
JavaVMOption options[] = {{classpath, NULL}};
JavaVMInitArgs args = {0};

args.version = JNI_VERSION_1_8;
args.nOptions = 1;
args.options = options;
args.ignoreUnrecognized = JNI_FALSE;

jint rc = JNI_CreateJavaVM(&jvm, (void **)&env, &args);
~~~

This is an **excerpt from embed.c**, not a standalone C program. **JNI_VERSION_1_8** requests a compatible JNI version; it does not force the JVM runtime down to Java 8. Because the service uses Java 17 syntax, the actual runtime must still be JDK 17+. You can add startup options such as **-Xmx512m**, **-Dapp.env=test**, **-XX:NativeMemoryTracking=summary** using additional elements in the JavaVMOption array and updating nOptions to match. Necessary options must be supplied at JVM creation time; do not assume all startup flags can be modified after the VM is already running.

**The JVM resides in the same process**: the Java heap, GC, runtime threads, and JVM native memory all consume CPU/RAM/address space within the C process. A native crash or dangerous memory corruption can bring down the entire process. **Do not create/destroy a JVM for every request**; there should be a single JVM managed over the host's lifecycle.

### 6.2. Finding Classes, Constructors, and Methods

Calls from the example:

| JNI Call | What It Finds |
| --- | --- |
| **FindClass("demo/PriceService")** | Class must be visible from the appropriate class loader. |
| **GetMethodID("<init>", "(J)V")** | Instance constructor taking a long. |
| **NewObject(..., (jlong)250)** | Creates PriceService with feeCents = 250. |
| **GetMethodID("quote", "(Ljava/lang/String;I)Ljava/lang/String;")** | Instance method returning String from String and int. |
| **GetMethodID("close", "()V")** | close() returning void. |
| **CallObjectMethod** | Calls an instance method returning a reference. |
| **CallVoidMethod** | Calls close() with no return value. |

**GetMethodID** is used for instance methods; for **static methods**, use **GetStaticMethodID/CallStatic...Method** on the class. Overload signatures must be exact: calling a method with the same name but different types will fail if the descriptor is wrong. If you change the package, method, constructor, or return type in Java, you must update the descriptor in C.

In an application with custom class loaders (plugin loaders, containers, or frameworks), **FindClass** from a newly attached native thread might not find classes outside the system/application classpath. In that case, a Java facade or `ClassLoader.loadClass` of a managed loader is the clear boundary, rather than guessing class names randomly.

### 6.3. Strings and Local References

**NewStringUTF** creates a Java String from **Modified UTF-8**, not a general function for arbitrary UTF-8 strings. The example uses ASCII SKUs **BOOK/PEN**, so the input bytes are valid. For Unicode data from C (especially NUL and supplementary code points), you need to convert properly to **jchar/UTF-16** and use **NewString**, or a strictly tested encoding contract; do not assume standard UTF-8 bytes are always valid for NewStringUTF.

**GetStringUTFChars** returns a character pointer in Modified UTF-8, which may be a copy and may fail due to out-of-memory. **ReleaseStringUTFChars** is mandatory to return the JNI resource before deleting the local reference/result or finishing. Do not call free() on this pointer. **DeleteLocalRef** deletes the JNI reference (allowing GC to manage the Java object when no other references remain); it does not directly free the object with free().

In a loop handling tens of thousands of requests, always delete local refs after each iteration or use PushLocalFrame/PopLocalFrame; just because you are in C does not mean local refs automatically disappear after each JNI call from the host. A long-lived attached thread can accumulate many local refs if not released.

### 6.4. Java Exceptions and Error Results

Java exceptions are held as a **pending exception on the current JNIEnv**; a JNI function returning NULL after a failed operation is not C's exception model. The procedure must:

1. Check **ExceptionCheck** after calls like FindClass, GetMethodID, NewObject, and CallObjectMethod.
2. Log information/convert to an error code according to the contract. The lesson uses **ExceptionDescribe** to display the stack trace when debugging.
3. Clear the pending exception if C will continue making normal JNI/cleanup calls, or intentionally propagate the exception when in a native method called by Java.
4. Do not treat the return value from a failed call as a valid object.

Try changing one SKU in **embed.c** from **"BOOK"** to **"UNKNOWN"**, recompile C, and run. The Java method will throw **IllegalArgumentException: unknown sku: UNKNOWN**, the C side describes the exception, skips the success branch, cleans up local refs, closes the service, and destroys the JVM before returning an error exit code. Stack trace content may vary by runtime, so do not assert fixed stdout for the error case.

## 7. JVM Lifecycle When Embedded in a C Process

The practice exercise creates the JVM once, calls the service, and then destroys it. A real-world application should have the following lifecycle:

1. **Process initialization:** determine the JVM version, classpath, JVM options, allocated resources, and logging. If the C host has multiple threads, designate a thread dedicated to initializing the JVM and owning the lifecycle API.
2. **JVM startup:** call JNI_CreateJavaVM **once**; check **JNI_OK**, bring the Java service to a ready state, and cache valid class/method handles.
3. **Serving:** native threads that need to interact with Java must attach; call the synchronized service; report errors and metrics clearly.
4. **Quiesce:** stop accepting new requests, wait for in-flight work/Java callbacks to complete, and stop worker resources.
5. **Service shutdown:** call the service's close()/stop(); delete global refs while JNIEnv is still valid.
6. **JVM shutdown:** call DestroyJavaVM and check the result; terminate the process or continue C work that does not use JNI.

**DestroyJavaVM** may have to wait for non-daemon Java threads/attached native threads to finish; if a worker has not detached or is still working, the destroy operation can wait for a very long time. Do not use kill/force-free to "fix" shutdown scheduling; first establish the correct shutdown order and have timeouts/monitoring at the application layer.

**Major limitation:** The JNI Invocation API does not support creating multiple independent JVMs in the same process. Nor should you design destroying and recreating the JVM in the same process as a normal "service restart"; restarting after destroy is not a lifecycle you can rely on. If independent restarts are needed, separate processes. You must plan for JVM startup cost, class loading, JIT warm-up, and thread/heap footprint.

The Invocation API documentation also recommends **avoiding initializing the JVM on the primordial thread** on some operating systems due to stack/signal limitations. The short example uses main() for ease of learning, whereas a real C host should control the JVM creation thread and stack size, as well as evaluate signal handling on the deployment platform.

## 8. When C Has Multiple Native Threads

**JavaVM*** is the JVM handle that can be used to **attach appropriate threads**. **JNIEnv*** is only valid for *the thread that owns it*; you must not cache a shared JNIEnv* and distribute it to pthreads. An unattached native worker can do the following:

~~~c
/* Illustration inside a native worker function, not a standalone program. */
JNIEnv *workerEnv = NULL;
if ((*jvm)->AttachCurrentThread(jvm, (void **)&workerEnv, NULL)
        != JNI_OK) {
    /* Report attach error to the C system. */
    return;
}

/* Call Java via workerEnv; check exceptions and clean up local refs.
   Do not use the env of the thread that initialized the JVM. */

jint detachResult = (*jvm)->DetachCurrentThread(jvm);
/* Record error if detachResult != JNI_OK. */
~~~

**AttachCurrentThread** does not create a new JVM; it attaches the current thread to the existing JVM. An already attached thread that attaches again receives its existing thread context. You must detach **before the native thread exits** and must not detach while Java frames are still running on the stack. If a thread invokes Java callbacks or holds monitors, it must complete the work and release resources before detaching.

If the **service** object is used after the initial local JNI frame ends, or passed to another worker thread, the owner needs **NewGlobalRef** (and eventually **DeleteGlobalRef**) instead of passing a local jobject directly. A global reference only keeps the object reachable; it does **not** make the service thread-safe on its own. Workers must use the Java service's proper synchronization mechanism, limit concurrency, and stop queuing new work before deleting the global ref or calling DestroyJavaVM.

**Daemon difference:** AttachCurrentThreadAsDaemon marks the newly attached native thread as a daemon Java thread; the difference affects shutdown. Do not choose daemon just so DestroyJavaVM does not wait if the worker might still use Java state/native memory after shutdown.

## 9. Calling a Framework Service (e.g., Spring) Through a Facade

PriceService in the lesson is a plain Java class, so only a constructor is needed. If the business logic is a Spring bean with dependency injection, transactions, datasource, and configuration, calling **NewObject** on the bean class will bypass the Spring container; many annotations such as **@Transactional**, injection, and proxies may not work as designed.

Put framework boot/stop into a **Java facade** with a stable API, and let C call the facade methods via JNI. One design direction (this is just a Java sketch, **not a standalone runnable file**):

~~~java
// Illustrative Java facade; requires appropriate Spring dependencies and configuration.
// public static synchronized void start(String[] args) {
//     context = SpringApplication.run(MyApplication.class, args);
// }
// public static String quote(String sku, int count) {
//     return context.getBean(PriceService.class).quote(sku, count);
// }
// public static synchronized void stop() {
//     if (context != null) context.close();
// }
~~~

The facade layer converts data types, normalizes exceptions, retrieves beans, and manages the container. C only knows the facade's name/signatures without having to understand Spring's internal wiring. Starting a Spring context has overhead and often spawns background threads, so stop() + resource closing must complete before DestroyJavaVM. Do not create multiple uncontrolled contexts per request.

In a module/automatic modularity environment, **-Djava.class.path** only serves the traditional classpath. If the Java application requires module path/--module-path, native image, or a specialized class loader, you need to configure accordingly and verify package/reflective access permissions; do not assume you can move a fat JAR or production module to JNI embedding without handling runtime dependencies.

## 10. Common Errors and Diagnostics

| Symptom | Common Cause | How to Check/Fix |
| --- | --- | --- |
| **Cannot start JVM: code ...** | Wrong libjvm, JVM option, architecture, or incompatible runtime | Cross-check JAVA_HOME, bitness, linker/loader, startup options, and exit code. |
| **libjvm.so: cannot open shared object file** | Loader cannot find the shared library even before JNI_CreateJavaVM | Check rpath, JDK runtime path, and library distribution policy. |
| **NoClassDefFoundError: demo/PriceService** | Classpath does not point to classes or Java class/module dependencies are missing | Stand in the right working directory; check classes/demo/PriceService.class and -Djava.class.path. |
| **NoSuchMethodError** | Wrong name, signature, static/instance, overload, or Java class version | Cross-check descriptor with bytecode via javap -s. |
| **JVM crash after freeing string** | Using pointer returned from GetStringUTFChars after Release or freeing with wrong function | Only use within the borrowed scope, call ReleaseStringUTFChars exactly once. |
| **JNI calls fail for unclear reasons** | Pending exception remains or invalid jobject/JNIEnv used | ExceptionCheck/Describe/Clear, check local/global reference scope and thread. |
| **Calling Java from pthread fails/crashes** | Native thread has not called AttachCurrentThread or used another thread's JNIEnv | Attach each native worker, use its own JNIEnv, detach before thread exits. |
| **DestroyJavaVM hangs for a long time** | Non-daemon thread or callback/worker still alive | Quiesce requests, close service/context, join/detach threads, then destroy. |
| **Service runs but Spring behavior is wrong** | NewObject bypassed dependency injection/proxies | Call through a Java facade that boots the container and retrieves the bean properly. |
| **Corrupted Unicode output** | Treating standard UTF-8 as Modified UTF-8, wrong converter | Design a specific encoding; use NewString/UTF-16 for arbitrary Unicode strings. |

**Inspection tips:**

- **javap -classpath classes -s demo.PriceService** shows the JVM descriptors of constructors and methods; always trust the descriptor from bytecode over guessing.
- **java -version**, **javac -version** verify the JDK version; **ldd ./embed** (Linux) helps inspect libjvm dependencies; **file ./embed** can confirm the executable's architecture.
- Try **-Xcheck:jni** in the JVM options array to catch many invalid JNI usages, but do not treat a clean result as proof that there are no memory race/lifetime bugs.
- When debugging JVM startup errors, log the **exit code**, stdout/stderr, and chosen JVM options, instead of just printing "service failed".
- If the C host runs for a long time, add metrics for the number of attached native threads, global reference ownership, JVM/heap/direct/native memory, JNI call latency, and Java→C translation error rate. Also observe GC and synchronized lock wait times.

## 11. Extension Exercises and Passing Criteria

1. **Success path:** compile both files, verify the exact three lines of stdout; try changing the constructor fee to 0 and calculate the new result yourself.
2. **Exception path:** change **"BOOK" → "UNKNOWN"** in C, rebuild, verify the Java exception is reported and the application still goes through cleanup/DestroyJavaVM; do not treat the error result as a valid String.
3. **Signature part:** run **javap -s**, match **(J)V**, **(Ljava/lang/String;I)Ljava/lang/String;**, **()V** with C; try changing a parameter type in Java to see that JNI needs updating.
4. **Lifecycle:** after **close()**, try calling **quote()** again to verify IllegalStateException; after **DestroyJavaVM**, do not reuse the old JNIEnv*.
5. **Classpath:** run the program from a different working directory to reproduce the error, then fix the classpath to a host-configured absolute path.
6. **Multi-threading (advanced):** have a native worker thread attach, call the Java service using a reference with proper ownership, clean up local refs, detach, join; only destroy after the worker finishes. Add a race test between quote and close per contract.
7. **Benchmarking:** measure JVM cold startup separately from quote time after warm-up; compare end-to-end JNI call time against business logic time, collecting p95/p99 statistics in a loop. Do not conflate JVM initialization latency with per-call latency.
8. **Real-world integration:** if replacing PriceService with a Spring bean, add a Java facade to boot ApplicationContext once, call the bean, and stop() before destroying the VM.

**Lesson is complete when:** a **C** executable creates the JVM itself, finds **demo.PriceService** properly, invokes at least two Java operations with results, handles exceptions per contract, returns all borrowed JNI resources, closes the service, checks DestroyJavaVM, and can explain why JNIEnv* is per-thread.

## Official References

- [JNI Specification, Chapter 5 – Invocation API (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): JNI_CreateJavaVM, JavaVMInitArgs, AttachCurrentThread, DetachCurrentThread, DestroyJavaVM, and lifecycle limitations.
- [JNI Functions (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): FindClass, GetMethodID, NewObject, CallObjectMethod, exceptions, strings, and local/global references.
- [Java Virtual Machine Specification §4.3 – Descriptors (Java 17)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3): JVM type/method signature descriptor rules.
- [javap command (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): print method signatures from compiled classes.
