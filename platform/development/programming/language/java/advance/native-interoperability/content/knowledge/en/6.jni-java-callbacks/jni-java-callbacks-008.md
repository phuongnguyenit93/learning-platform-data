# Calling Caller-Sensitive Methods and Handling the Absence of a Java Frame

In JNI (Java Native Interface), C/C++ code can invoke Java methods using **CallStaticObjectMethod**, **CallObjectMethod**, and related functions. However, some Java APIs determine their result or access permissions based on the **Java class that actually calls the method** (*caller-sensitive method*). On a native thread attached to the JVM without an appropriate Java call frame, a direct JNI call to such an API may fail or behave according to the API's own fallback rules.

This lesson focuses on **the caller sensitivity mechanism when calling Java from JNI**, how to recognize a context without a Java caller frame, and how to design a Java bridge to provide an explicit call context. Examples use Java 17+ and standard JNI; the native library build section is specifically illustrated on Linux/POSIX.

## 1. What does caller-sensitive method mean?

**Caller-sensitive** is a property of certain Java library methods: the result, access permissions, or class loader they use depends on the **identity of the Java class directly calling them**. "Caller" here is not the end user, not the thread ID, nor an arbitrary class passed in a parameter. It is determined according to the rules of the JVM and that API for the Java call flow.

Typical examples:

- **MethodHandles.lookup()** creates a **MethodHandles.Lookup** object with permissions corresponding to the calling class. Calling it inside class **A** creates a lookup bound to **A**; calling it in **B** creates a lookup bound to **B**. This is a sensitive access capability; a full-privilege lookup must not be arbitrarily granted to untrusted code.
- **Class.forName(String)** selects a class loader based on the calling class. If there is no Java caller frame, Java SE 21 specifies using the **system class loader**. It may return a different class or throw **ClassNotFoundException** depending on the class loader.
- **AccessibleObject.canAccess(Object)** requires a caller context to evaluate access via reflection. When JNI calls it in a context without a Java caller class and the access override flag has not been enabled, the check usually only accepts public members and declaring classes in unconditionally exported packages.
- **StackWalker.getCallerClass()** requires a class in an appropriate call frame. When there is no caller frame, the method may throw **IllegalCallerException**; additionally, **RETAIN_CLASS_REFERENCE** must be configured.

Note: **caller-sensitive does not mean all APIs will throw the same exception**. Each API has its own contract when a caller is missing. Read the Javadoc of the running JDK version before choosing a handling strategy.

### Distinguishing caller, callee, and Java frame

For a normal Java call:

~~~text
Java class A.method()
    |
    +--> MethodHandles.lookup()
              |
              +--> lookupClass() is A
~~~

For a native thread making a direct JNI call:

~~~text
POSIX/native thread
    |
    +--> AttachCurrentThread()
    |
    +--> JNI CallStaticObjectMethod(MethodHandles.lookup)
              |
              +--> no Java caller frame
              +--> IllegalCallerException
~~~

Creating a **Java bridge** changes the context:

~~~text
POSIX/native thread
    |
    +--> AttachCurrentThread()
    |
    +--> JNI CallStaticObjectMethod(CallerBridge.lookupFromJava)
              |
              +--> Java frame CallerBridge.lookupFromJava()
                         |
                         +--> MethodHandles.lookup()
                                   |
                                   +--> caller class = CallerBridge
~~~

Calling **AttachCurrentThread** enables the native thread to interact with the JVM, but **does not automatically create a Java caller frame for a direct caller-sensitive call**. The Java bridge actually calls the API at a bytecode location you control; the JVM can then determine the appropriate caller class.

## 2. When does JNI lack a caller Java frame?

Two operational scenarios should be distinguished:

**Scenario 1 – Java calls down into native and native calls back into Java.** A Java thread is executing a **native** method called from Java, so there may be Java frames lower down on the stack. However, the caller recognized by a sensitive API must follow that API's stack walk/access rules. Do not assume that JNI **CallStaticObjectMethod** always has the same meaning as a bytecode call placed directly in the desired Java class.

**Scenario 2 – A native thread is created from C/C++ and then attached to the JVM.** This thread initially has no Java call chain. After **AttachCurrentThread**, it has its own valid **JNIEnv** for the thread, but still **has no Java caller class** when directly calling a caller-sensitive method. This is the explicit case the JNI Specification warns about.

Scenario 2 commonly appears in:

- Callbacks from C/C++ libraries originating on worker threads managed by native code;
- Data processing engines, drivers, media/cryptography libraries, or native event loops that proactively call Java;
- Host code embedding the JVM via the Invocation API;
- Frameworks holding **JavaVM*** to attach native worker threads to the right JVM later.

What matters most is the **actual model of the call stack**, not whether the C code had been called by Java at some other time.

## 3. Behavior when there is no caller frame: different examples

| API/usage | Why it depends on caller | Notable behavior when JNI calls directly without a Java caller |
| --- | --- | --- |
| **MethodHandles.lookup()** | Lookup carries permissions of the calling class | Throws **IllegalCallerException** |
| **Class.forName(String)** | Selects class loader according to the calling class | Uses **system class loader** per Java SE 21 Javadoc |
| **AccessibleObject.canAccess(obj)** | Checks access permissions of the caller | With the access flag not overridden, access only succeeds under public + unconditionally exported package conditions |
| **AccessibleObject.trySetAccessible()** | Considers caller/module to allow bypassing access checks | When there is no Java caller, does not automatically have deep access; Javadoc restricts permitted cases |
| **StackWalker.getCallerClass()** | Retrieves the caller frame | Throws **IllegalCallerException** if there is no caller frame (and also requires **RETAIN_CLASS_REFERENCE**) |

This table is meant to compare **API contracts**, not to guarantee that every JNI invocation across all JDK versions will have the same stack or the same result. For **AccessibleObject.canAccess**, if the access override flag has been validly enabled, the method's rules must still be fully considered; the state of the **AccessibleObject** cannot be ignored. **Class.forName(String, boolean, ClassLoader)** allows providing an explicit loader, avoiding dependence on the implicit caller class loader in the single-parameter variant.

Security principle: a caller-sensitive API uses permissions based on the actual *call site*. **JNI does not provide a valid way to "spoof" the caller class by casting a pointer or passing an arbitrary class name**.

## 4. Designing a Java bridge with an explicit call context

When native code needs to call a caller-sensitive API without an appropriate Java frame, create a concrete Java method as an entry point. That method calls the API in its own Java body. If class loading is needed, it is better to pass an intentional **ClassLoader** or operate with a **Class<?>** already safely obtained from Java.

Example of a Java bridge:

~~~java
package demo;

import java.lang.invoke.MethodHandles;

public final class CallerBridge {
    private CallerBridge() {}

    // When this bytecode calls lookup(), lookupClass() is CallerBridge.
    public static String lookupOwner() {
        return MethodHandles.lookup().lookupClass().getName();
    }

    // Has an explicit caller frame; can choose an explicit loader.
    public static Class<?> loadWithoutInitializing(
            String binaryName, ClassLoader loader)
            throws ClassNotFoundException {
        return Class.forName(binaryName, false, loader);
    }
}
~~~

The **lookupOwner()** method does not hand out a **Lookup** object to native code; it only returns observational information, suitable for an experiment. In a real application, if lookup privileges are needed to invoke a member, the bridge should **perform the required operation in Java**, validate the class/member name and input request, and return only the minimal data/result. Returning a high-privilege **Lookup** to every native caller can inadvertently widen access boundaries.

Do not confuse **publicLookup()** and **lookup()**:
- **MethodHandles.lookup()** reflects the permissions of the actual calling class; it can access members that the class is permitted to access.
- **MethodHandles.publicLookup()** does not require a caller with a Java frame, but has minimal access permissions, suitable for public members in unconditionally exported packages. According to **MethodHandles.Lookup** rules, a lookup lacking appropriate privileges cannot be used to create handles for caller-sensitive methods.
- **lookup.in(Target.class)** or **privateLookupIn(...)** are not tricks to turn native code into an arbitrary caller. They obey rules on lookup privileges, accessibility, and module opens/exports; they do not create new privileges out of thin air.

## 5. End-to-end example: attached POSIX thread, direct JNI call, and Java bridge

The following example runs with **JDK 17+ on Linux** and a C compiler with **pthread** support. It demonstrates two ways of calling **MethodHandles.lookup()** from the same native-attached thread.

**File 1 — src/demo/CallerDemo.java**

~~~java
package demo;

import java.lang.invoke.MethodHandles;

public final class CallerDemo {
    static {
        System.loadLibrary("caller_demo");
    }

    private CallerDemo() {}

    // This is a regular Java method, calling the sensitive API via bytecode.
    public static String bridgeCaller() {
        return MethodHandles.lookup().lookupClass().getName();
    }

    // JNI creates a POSIX thread and attaches it to the JVM.
    private static native void runNativeThread();

    public static void main(String[] args) {
        String caller = MethodHandles.lookup()
                .lookupClass()
                .getName();
        System.out.println("Java main: " + caller);
        runNativeThread();
    }
}
~~~

**File 2 — native/caller_demo.c**

~~~c
#include <jni.h>
#include <pthread.h>
#include <stdio.h>

struct WorkerArgs {
    JavaVM *vm;
    jclass bridge_class;  /* Global reference, not a local ref */
};

/* Used only in the demo to print and handle unexpected Java errors. */
static void print_and_clear(JNIEnv *env, const char *where) {
    if ((*env)->ExceptionCheck(env)) {
        fprintf(stderr, "JNI error at %s:\n", where);
        (*env)->ExceptionDescribe(env);
        (*env)->ExceptionClear(env);
    }
}

static void *worker_main(void *opaque) {
    struct WorkerArgs *args = (struct WorkerArgs *)opaque;
    JNIEnv *env = NULL;

    if ((*args->vm)->AttachCurrentThread(
            args->vm, (void **)&env, NULL) != JNI_OK) {
        fputs("AttachCurrentThread failed\n", stderr);
        return NULL;
    }

    /* MethodHandles is a JDK class; FindClass does not need an app loader. */
    jclass methods = (*env)->FindClass(
            env, "java/lang/invoke/MethodHandles");
    if (methods == NULL) {
        print_and_clear(env, "FindClass MethodHandles");
        goto detach;
    }

    jmethodID direct = (*env)->GetStaticMethodID(
            env, methods, "lookup",
            "()Ljava/lang/invoke/MethodHandles$Lookup;");
    if (direct == NULL) {
        print_and_clear(env, "GetStaticMethodID lookup");
        (*env)->DeleteLocalRef(env, methods);
        goto detach;
    }

    /* There is no Java caller frame for this direct call. */
    jobject raw_lookup = (*env)->CallStaticObjectMethod(
            env, methods, direct);

    if ((*env)->ExceptionCheck(env)) {
        jthrowable thrown = (*env)->ExceptionOccurred(env);
        (*env)->ExceptionClear(env);  /* Intentional exception handling */

        jclass illegal_caller = (*env)->FindClass(
                env, "java/lang/IllegalCallerException");
        if (illegal_caller != NULL) {
            jboolean expected = (*env)->IsInstanceOf(
                    env, thrown, illegal_caller);
            puts(expected
                 ? "Direct JNI: IllegalCallerException"
                 : "Direct JNI: another exception");
            (*env)->DeleteLocalRef(env, illegal_caller);
        } else {
            print_and_clear(env, "FindClass IllegalCallerException");
        }
        (*env)->DeleteLocalRef(env, thrown);
    } else {
        puts("Direct JNI: no exception (inspect JDK/stack)");
        if (raw_lookup != NULL) {
            (*env)->DeleteLocalRef(env, raw_lookup);
        }
    }
    (*env)->DeleteLocalRef(env, methods);

    /*
     * Do not call lookup() directly anymore.
     * Call the Java bridge first to create a Java caller frame.
     * bridge_class is a GlobalRef created on the initial Java thread.
     */
    jmethodID bridge = (*env)->GetStaticMethodID(
            env, args->bridge_class, "bridgeCaller",
            "()Ljava/lang/String;");
    if (bridge == NULL) {
        print_and_clear(env, "GetStaticMethodID bridgeCaller");
        goto detach;
    }

    jstring name = (jstring)(*env)->CallStaticObjectMethod(
            env, args->bridge_class, bridge);
    if ((*env)->ExceptionCheck(env) || name == NULL) {
        print_and_clear(env, "CallStaticObjectMethod bridgeCaller");
        goto detach;
    }

    const char *utf = (*env)->GetStringUTFChars(env, name, NULL);
    if (utf != NULL) {
        printf("Via Java bridge: %s\n", utf);
        (*env)->ReleaseStringUTFChars(env, name, utf);
    } else {
        print_and_clear(env, "GetStringUTFChars");
    }
    (*env)->DeleteLocalRef(env, name);

detach:
    (*args->vm)->DetachCurrentThread(args->vm);
    return NULL;
}

/* JNI name maps package demo, class CallerDemo, native method. */
JNIEXPORT void JNICALL
Java_demo_CallerDemo_runNativeThread(JNIEnv *env, jclass clazz) {
    JavaVM *vm = NULL;
    if ((*env)->GetJavaVM(env, &vm) != JNI_OK) {
        return;
    }

    /*
     * clazz is a local reference of the thread running the native method.
     * Convert to a global ref before the native worker uses it.
     */
    jclass global_class = (jclass)(*env)->NewGlobalRef(env, clazz);
    if (global_class == NULL) {
        return; /* The JVM may have set a pending OutOfMemoryError */
    }

    struct WorkerArgs args = { vm, global_class };
    pthread_t thread;
    int status = pthread_create(&thread, NULL, worker_main, &args);

    if (status == 0) {
        /* Wait for the worker to finish using args and global_class before returning. */
        (void)pthread_join(thread, NULL);
    } else {
        fprintf(stderr, "pthread_create failed: %d\n", status);
    }

    (*env)->DeleteGlobalRef(env, global_class);
}
~~~

This is a complete program illustrating the path **Java → JNI creates native thread → AttachCurrentThread → JNI calls Java**, using **pthread**, so the C portion applies directly only to Linux/POSIX and is not pre-built code for Windows. **print_and_clear** is designed for the demo; in real production code there must be a policy to propagate errors to a monitor/caller and not automatically clear every exception.

### Compiling and running on Linux

Assuming **JDK 17 or 21**, **gcc/clang**, **pthread**, and the **JAVA_HOME** environment variable pointing to the JDK directory:

~~~bash
mkdir -p src/demo native out
# Save the two Java and C files according to the paths noted above.

javac -d out src/demo/CallerDemo.java

cc -std=c17 -Wall -Wextra -fPIC -shared -pthread \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  native/caller_demo.c -o libcaller_demo.so

java -Djava.library.path=. -cp out demo.CallerDemo
~~~

With **JDK 17/21 on Linux**, assuming the build and native library load succeed, the expected stdout is:

~~~text
Java main: demo.CallerDemo
Direct JNI: IllegalCallerException
Via Java bridge: demo.CallerDemo
~~~

Line-by-line explanation:

1. **Java main**: **MethodHandles.lookup()** runs directly in **CallerDemo.main**, so it receives **demo.CallerDemo** as the caller.
2. **Direct JNI**: the native worker is attached via **AttachCurrentThread** but has no Java caller frame. According to the **MethodHandles.lookup()** API, the direct call throws **IllegalCallerException**. C calls **ExceptionOccurred** and then **ExceptionClear** because the demo intentionally handles this exception.
3. **Via Java bridge**: native code calls **CallerDemo.bridgeCaller()** via JNI. Inside the Java method, **MethodHandles.lookup()** sees the actual calling class as **demo.CallerDemo**, so it succeeds.

**Note regarding stdout:** if the library is missing, architectures mismatch, the compiler does not support pthread, or another JNI call fails, the program may report an exception/stderr or terminate early. On Windows, native threads must be implemented with the appropriate API and the library compiled for the Windows ABI. The example is designed to illustrate the exact JDK 17/21 Linux case stated, and does not claim universal results across all JVMs.

## 6. Why must JavaVM*, JNIEnv*, and global references be used properly?

The example above intentionally demonstrates three essential rules for native callbacks:

**JavaVM*** is the VM handle, which can be stored and shared across native threads. Each thread that wants to use JNI must obtain *its own* **JNIEnv*** via **AttachCurrentThread** or an appropriate API. **JNIEnv*** is a per-thread interface; never pass a **JNIEnv*** pointer received in a native method on a Java thread to a new pthread.

**jclass clazz** passed into **runNativeThread** is a JNI local reference. A local reference is scoped to a thread/local reference frame, so it cannot be arbitrarily stored for another worker to use. **NewGlobalRef** keeps the class object alive and valid across threads; **DeleteGlobalRef** is needed when it is no longer used. The example waits for the worker to finish with **pthread_join** before freeing the global ref; the **args** object on the stack remains alive until the join completes.

**AttachCurrentThread** attaches the native thread to the JVM; when the work finishes, **DetachCurrentThread** detaches it. A thread must not detach while Java method frames are running on its stack. The example detaches only **after** the bridge call finishes. On long-running threads, local reference limits must be considered and used refs freed; an attached thread does not have the same local ref cleanup lifecycle as a single ordinary native method call until it detaches.

Practical rule:

~~~text
Native worker is created
    → AttachCurrentThread gets its own JNIEnv*
    → use lifecycle-managed global refs / JavaVM*
    → look up method with exact JNI signature
    → Call...Method and check for exception
    → process/record result and release local refs
    → DetachCurrentThread
    → owning side deletes global refs when safe
~~~

## 7. Exceptions thrown by caller-sensitive methods

A JNI **Call...Method** may leave a **pending Java exception** instead of returning a usable result. Check **ExceptionCheck()** or **ExceptionOccurred()** immediately after call sites that can throw, before using the returned object.

~~~c
/* Standalone illustrative snippet in a native method that already has env, owner, mid. */
jobject result = (*env)->CallStaticObjectMethod(env, owner, mid);

if ((*env)->ExceptionCheck(env)) {
    /* Pending Java exception present: do not use result. */
    /* Option A: return to Java so the JVM throws the exception. */
    return;
}

/* Only use result if the method contract allows and after checking. */
~~~

The snippet above is a **fragment** for a JNI function with a **void** return type; in a function returning another type, an appropriate return value must be used. Do not apply this fragment verbatim inside a **pthread worker** that has no Java caller to receive the exception: the worker must have a clear policy to handle, log, forward via an appropriate Java callback, or report the error to the work owner.

Two different handling options:

- **Leave the exception pending and return from the Java-called native method**: the JVM can propagate the exception to the Java caller. Do not call further JNI APIs that are disallowed while an exception is pending.
- **Handle the exception in native code**: read the exception with **ExceptionOccurred**, clear it with **ExceptionClear**, log/package the error result, and continue once state is valid. Do not silently clear all exceptions; **OutOfMemoryError**, linkage errors, and other data errors must be handled appropriately.

In the demo, clearing **IllegalCallerException** after classifying it is intentional so execution can continue to the bridge path. **ExceptionDescribe** can also print a stack trace for diagnostics, but should not be treated as complete production handling.

When using **MethodHandles.lookup()**, check the actual error type; do not catch every **RuntimeException** and assume "missing caller". Errors from packages/modules, member signatures, null inputs, or ClassLoaders can have independent causes.

## 8. Interaction with class loaders and module access permissions

A common point of confusion: a native worker calls **FindClass("com/example/Plugin")** and cannot find it even though the class exists in the application.

According to the JNI Specification, **FindClass** from a normal native method usually uses the class loader of the class declaring the native method. When called in an Invocation Interface context without a native method/class loader associated with the Java stack, it uses the **system class loader**. Classes loaded by plugin loaders/custom loaders may not be visible to the system loader.

This is a related issue, but **not identical** to caller sensitivity:

- **Caller-sensitive** is a property of the Java method being called, such as **Class.forName(String)** using the caller's class loader.
- **JNI FindClass** is a JNI function that uses its own loader-selection rules depending on the native method / Invocation Interface context.
- **Thread.currentThread().getContextClassLoader()** is a configurable thread property; it is **not automatically synonymous** with the caller class loader and does not turn a native call into a bytecode call from an arbitrary Java class.

Intentional ways to resolve this:

1. Pass a **Class<?>** already resolved by Java into native code, create a **global ref** when it must be held across threads, and invoke methods on that class itself;
2. Pass an allowed **ClassLoader** and then call **Class.forName(name, false, loader)** through a Java bridge;
3. Place the loader-selection operation in a Java bridge belonging to the proper responsible module/class;
4. Check **module exports/opens**, access levels, and **MethodHandles.Lookup** permissions instead of using reflection to bypass valid checks.

For example, **Class.forName(String)** may not throw solely because a caller is missing; it uses the system loader and can *load the wrong version of a class* when the application has multiple class loaders. If the same binary name exists in multiple loaders, their **Class<?>** objects have different identities; the consequences can be **ClassCastException**, **LinkageError**, or class-not-found errors. This is why the loader must be defined as part of the native ↔ Java contract.

## 9. Do not turn the Java bridge into an arbitrary privilege-escalation point

A bridge creates a valid caller, but **that caller is the Java class containing the bridge itself**, not an arbitrary identity requested by native code. Which package/module the bridge is placed in determines its access permissions.

A safe design typically does the following:

~~~java
package demo;

import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class SafeBridge {
    private SafeBridge() {}

    /*
     * Example of controlling a specific operation: only calls a pre-selected
     * public method, without accepting arbitrary member names from native/untrusted code.
     */
    public static int twice(int value) {
        return Math.multiplyExact(value, 2);
    }

    // For illustration only: lookup bound to SafeBridge.
    public static Class<?> lookupIdentity() {
        return MethodHandles.lookup().lookupClass();
    }
}
~~~

This is a **Java-only fragment** that does not load a native library itself. **twice** illustrates a narrow boundary with an explicit contract, while **lookupIdentity** shows the actual Java caller. **Math.multiplyExact** throws **ArithmeticException** on overflow, reflecting error-checking rules rather than silently wrapping the result.

Avoid anti-patterns:
- A public bridge accepting a class/member name and using a full-privilege **Lookup** to read/write any private member without policy checks;
- Native code storing a high-privilege **Lookup** and distributing it to untrusted plugins;
- Calling **setAccessible(true)** or **privateLookupIn** as a default way to bypass module encapsulation;
- Using **publicLookup()** and assuming it can call every caller-sensitive API or every non-public member;
- Treating the presence of any Java frame as proof of the privileges of the *expected Java class*. The actual caller must be checked at the site where the API executes.

Caller sensitivity is part of **Java's access permission rules**. A valid Java bridge can solve the absence of a caller frame, but it is not a tool to grant privileges beyond the application's contract and policy.

## 10. Debugging workflow when native-to-Java calls do not behave as expected

When a method works from Java but breaks when called from JNI, check in order:

| Symptom | Question to verify | Action |
| --- | --- | --- |
| **IllegalCallerException** when calling **MethodHandles.lookup()** | Is the thread attached from native and lacking a Java caller frame? | Call through a Java bridge or use **publicLookup()** if only public access is needed |
| **ClassNotFoundException** or **NoClassDefFoundError** | Which loader is being used? Is there a custom module/class loader? | Pass **Class<?>/ClassLoader** from the right source; avoid inferring from class name |
| **NoSuchMethodError** from **GetMethodID/GetStaticMethodID** | Does the JNI descriptor have the exact package, name, static/instance, and return type? | Use exact binary name and signature; check pending exceptions |
| **IllegalAccessException** or access denied | What are the caller lookup class, module export/open, and access modifier? | Adjust the contract/bridge/module config intentionally |
| **canAccess** returns false | Under which caller is it running; what are the access flag and module exports? | Check Javadoc; do not treat false as missing JNI attachment |
| Native crash or random errors | Is **JNIEnv*** used on the wrong thread? Is a local ref used across threads? | Use **AttachCurrentThread**, **NewGlobalRef**, and proper lifecycle |
| JNI Call returns null or no result | Is there a pending Java exception? | Call **ExceptionCheck/ExceptionOccurred** before using the result |

Use **javap -s** or **javac -h** to verify descriptors and JNI names at build time. For the bridge method **public static String bridgeCaller()**, the descriptor is **()Ljava/lang/String;**; for **MethodHandles.lookup()**, the descriptor is **()Ljava/lang/invoke/MethodHandles$Lookup;**. In JNI, class names use **/** instead of **.**, and nested classes use **$** in descriptors. A wrong descriptor is completely different from an error caused by a missing caller frame, even though both occur at a JNI call.

You can test a simple Java bridge without native code:

~~~java
import java.lang.invoke.MethodHandles;

public class CallerIdentity {
    static final class One {
        static String inspect() {
            return MethodHandles.lookup().lookupClass().getSimpleName();
        }
    }
    static final class Two {
        static String inspect() {
            return MethodHandles.lookup().lookupClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        System.out.println(One.inspect());
        System.out.println(Two.inspect());
    }
}
~~~

Save as **CallerIdentity.java**, run:

~~~bash
javac CallerIdentity.java
java CallerIdentity
~~~

Stdout:

~~~text
One
Two
~~~

Both branches call **MethodHandles.lookup()**, but each call is written in the **bytecode of a different class**, so the result depends on the exact calling class. This is Java-only evidence of the caller-sensitive mechanism; it does **not** replace the native-attached thread experiment in section 5.

## 11. Self-check questions

**1.** A native worker has called **AttachCurrentThread** successfully. Can it be treated as a Java caller for **MethodHandles.lookup()** yet?

**Answer:** Not yet. Attach provides a **JNIEnv*** and associates the thread with the VM; it does not automatically create a Java frame calling **lookup()**. Calling directly from a JNI attached thread lacking a frame will throw **IllegalCallerException** per the Javadoc.

**2.** Why does going through **CallerDemo.bridgeCaller()** work?

**Answer:** **bridgeCaller** is an actual Java method being executed. The **MethodHandles.lookup()** call resides in the bytecode of class **CallerDemo**, so the JVM knows the corresponding caller class. The **Lookup** result or operation depends on **CallerDemo**'s permissions, not the native thread.

**3.** If a caller class is missing, do all caller-sensitive APIs throw **IllegalCallerException**?

**Answer:** No. **Class.forName(String)** has a rule to use the system class loader when there is no caller frame. **AccessibleObject.canAccess** has its own access rules. Always check each method's Javadoc.

**4.** Why can't you pass **JNIEnv*** from a Java thread to a pthread and call **CallStaticObjectMethod**?

**Answer:** **JNIEnv*** is only valid for the thread that owns it. A native worker needs to call **AttachCurrentThread** to obtain its own **JNIEnv***; Java objects intended for cross-thread use must have an appropriate reference, usually a global reference.

**5.** Can a Java bridge located in module A automatically gain private permissions of module B using **MethodHandles.lookup()**?

**Answer:** No. Lookup reflects the permissions of the bridge class and module rules; **privateLookupIn**, if used, also checks access/module opens conditions. Bridge design must validate operations and not distribute sensitive capabilities.

## Official references

- JNI Design Overview — **Calling Caller-Sensitive Methods**: https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html
- JNI Invocation API — **AttachCurrentThread**, **DetachCurrentThread**: https://docs.oracle.com/en/java/javase/21/docs/specs/jni/invocation.html
- JNI Functions — **FindClass**, **Call...Method**, **ExceptionCheck**, **NewGlobalRef**: https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html
- **MethodHandles.lookup()** — behavior when there is no caller frame: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.html
- **Class.forName(String)** and class loader when there is no Java caller: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html
- **AccessibleObject.canAccess** and module access: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html
- **StackWalker.getCallerClass**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StackWalker.html

**Remember:** Native code can call Java via JNI, but **caller-sensitive permissions and semantics depend on a real Java call frame**. When a caller frame is absent, each API decides its own handling. A responsible Java bridge with an explicit caller class and reasonable permission boundaries is an easily verifiable design for native callbacks.